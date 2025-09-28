"""
AI驱动的核心引擎 - 让AI决定一切

设计理念：
1. AI 完全主导业务逻辑，工程层只提供基础设施
2. 通过统一的契约结构让 AI 自主处理所有对话复杂度
3. 数据结构开放，AI 可以自由决定存储内容
4. 工具调用完全通用化，不含业务逻辑

核心流程：
用户输入 → 统一AI理解（含上下文） → 工具计划 → 执行 → 回复
"""
import json
import re  # 用于占位符解析
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
import uuid
import time
from pydantic import BaseModel, Field, ValidationError
import openai
import structlog
import httpx
import os

from .core.config import settings
from .core.prompt_manager import prompt_manager
from .core.llm_client import LLMClient
from .services.media_service import make_signed_url
from .services.household_service import household_service

logger = structlog.get_logger(__name__)


class ContextRequestModel(BaseModel):
    """AI 请求的上下文数据模型"""
    name: str  # 上下文名称，用于后续引用
    kind: str  # 类型：recent_memories/semantic_search/direct_search/thread_summaries
    limit: Optional[int] = None  # 返回数量限制
    query: Optional[str] = None  # 查询条件或语义搜索内容
    filters: Optional[Dict[str, Any]] = None  # 精确过滤条件
    notes: Optional[str] = None  # 额外说明


class ToolStepModel(BaseModel):
    """工具执行步骤模型"""
    tool: str  # 工具名称（如 store/search/aggregate）
    args: Dict[str, Any] = Field(default_factory=dict)  # 工具参数


class ToolPlanModel(BaseModel):
    """工具执行计划模型"""
    requires_context: List[str] = Field(default_factory=list)  # 需要的上下文依赖
    steps: List[ToolStepModel] = Field(default_factory=list)  # 执行步骤列表


class UnderstandingModel(BaseModel):
    """AI 理解结果模型 - 核心契约结构"""
    intent: Optional[str] = None  # 识别的用户意图
    entities: Dict[str, Any] = Field(default_factory=dict)  # 提取的实体信息
    need_action: bool = False  # 是否需要执行操作
    need_clarification: bool = False  # 是否需要澄清信息
    missing_fields: List[str] = Field(default_factory=list)  # 缺失的必要字段
    clarification_questions: List[str] = Field(default_factory=list)  # 澄清问题列表
    suggested_reply: Optional[str] = None  # AI 建议的回复
    context_link: Optional[Dict[str, Any]] = None  # 上下文关联（如作用范围）
    occurred_at: Optional[str] = None  # 事件发生时间
    update_existing: Optional[bool] = None  # 是否更新已有记录
    metadata: Dict[str, Any] = Field(default_factory=dict)  # 其他元数据


class AnalysisModel(BaseModel):
    """AI 分析结果完整模型 - 统一契约"""
    understanding: UnderstandingModel  # 理解结果
    context_requests: List[ContextRequestModel] = Field(default_factory=list)  # 需要的上下文
    tool_plan: ToolPlanModel = Field(default_factory=ToolPlanModel)  # 工具执行计划
    response_directives: Dict[str, Any] = Field(default_factory=dict)  # 响应指令（如风格）

def _looks_like_uuid(value: Optional[str]) -> bool:
    """检查字符串是否为有效的 UUID 格式
    
    用于验证 user_id、trace_id 等标识符
    """
    if not value or not isinstance(value, str):
        return False
    try:
        uuid.UUID(value)
        return True
    except Exception:
        return False

# 统一改为从 YAML 读取 prompts（见 prompt_manager）


class AIEngine:
    """AI 引擎核心类 - 处理所有消息理解、工具调用和回复生成
    
    设计原则：
    - 让 AI 决定一切业务逻辑
    - 工程层只提供基础能力（LLM调用、工具执行、数据存储）
    - 通过 Prompt 和数据驱动系统演进
    """
    
    def __init__(self):
        # 统一 LLM 客户端（可按配置切换 OpenAI 兼容/Anthropic 等）
        self.llm = LLMClient()
        
        # MCP 服务连接配置
        self.mcp_client = None
        self.mcp_url = os.getenv('MCP_SERVER_URL', 'http://faa-mcp:8000')
        # MCP 严格模式：生产环境下禁用模拟返回，确保真实工具调用
        self._mcp_strict_mode: bool = str(os.getenv('MCP_STRICT_MODE', 'true')).lower() in {'1', 'true', 'yes'}
        
        # 工具调用记录：按 trace_id 聚合，用于交互持久化与问题排查
        self._tool_calls_by_trace: Dict[str, List[Dict[str, Any]]] = {}
        
        # HTTP 客户端复用（避免频繁创建连接）
        self._http_client: Optional[httpx.AsyncClient] = None
        
        # 工具规格缓存：减少对 MCP 服务的频繁调用
        # data: 工具列表数据, ts: 缓存时间戳, ttl: 缓存有效期（默认20分钟）
        self._tool_specs_cache: Dict[str, Any] = {"data": None, "ts": 0.0, "ttl": float(os.getenv('MCP_TOOLS_CACHE_TTL', '1200'))}
        
        # 向量嵌入缓存机制（两级缓存，优化性能和成本）
        # 1. trace 级缓存：每次请求独立，避免重复生成相同文本的向量
        self._emb_cache_by_trace: Dict[str, Dict[str, List[float]]] = {}
        # 2. 全局 LRU 缓存：跨请求复用，减少 API 调用成本
        self._emb_cache_global: Dict[str, Tuple[List[float], float]] = {}
        self._emb_cache_global_max_items: int = int(os.getenv('EMB_CACHE_MAX_ITEMS', '1000'))
        self._emb_cache_global_ttl: float = float(os.getenv('EMB_CACHE_TTL_SECONDS', '3600'))
        
        # 家庭服务：提供家庭成员和关系上下文
        self._household_service = household_service

    @staticmethod
    def _profile_for_context(context: Optional[Dict[str, Any]], response_directives: Optional[Dict[str, Any]] = None) -> Optional[str]:
        if response_directives:
            profile = response_directives.get('profile')
            if isinstance(profile, str) and profile.strip():
                return profile.strip()
        if not context:
            return None
        channel = context.get('channel')
        if channel == 'threema':
            return 'threema'
        return None

    @staticmethod
    def _safe_json_dumps(payload: Dict[str, Any]) -> str:
        try:
            return json.dumps(payload, ensure_ascii=False, default=str)
        except TypeError:
            return json.dumps(json.loads(json.dumps(payload, default=str)), ensure_ascii=False)
        
    async def initialize_mcp(self):
        """初始化MCP客户端连接"""
        try:
            # 暂时使用HTTP调用方式，而不是stdio
            # 这样更简单且适合容器化部署
            logger.info(f"Connecting to MCP server at {self.mcp_url}")
            
            # 测试连接（复用 HTTP 客户端）
            if self._http_client is None:
                self._http_client = httpx.AsyncClient()
            response = await self._http_client.get(f"{self.mcp_url}/health", timeout=5.0)
            if response.status_code == 200:
                logger.info("MCP server is healthy")
                self.mcp_client = True  # 标记为可用
            else:
                logger.warning(f"MCP server health check failed: {response.status_code}")
            
        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {e}")
            logger.warning("Falling back to mock MCP mode")
            self.mcp_client = None

    async def initialize_embedding_warmup(self):
        """预热embedding模型，避免首次请求时的延迟"""
        try:
            # 检查模型是否已经预加载
            if hasattr(self.llm, '_fastembed_model') and self.llm._fastembed_model is not None:
                logger.info("Embedding model already loaded, skipping warmup")
                return
                
            logger.info("Warming up embedding model...")
            success = await self.llm.warmup_embedding_model()
            if success:
                logger.info("Embedding model preloaded successfully")
            else:
                logger.warning("Failed to preload embedding model, will load on demand")
        except Exception as e:
            logger.warning(f"Embedding warmup failed: {e}, will load on demand")
    
    async def close(self):
        """关闭MCP客户端连接"""
        try:
            if self._http_client is not None:
                await self._http_client.aclose()
        except Exception:
            pass

    async def _get_tool_specs(self) -> Dict[str, Any]:
        """获取 MCP 工具规格并缓存，用于动态工具发现与超时预算。"""
        now = time.time()
        cache = self._tool_specs_cache
        ttl = float(cache.get('ttl') or 1200)
        if cache.get('data') and now - float(cache.get('ts', 0)) < ttl:
            return cache['data']
        if self._http_client is None:
            self._http_client = httpx.AsyncClient()
        try:
            resp = await self._http_client.get(f"{self.mcp_url}/tools", timeout=3.0)
            resp.raise_for_status()
            data = resp.json()
            self._tool_specs_cache = {"data": data, "ts": now, "ttl": ttl}
            return data
        except Exception:
            # 返回旧缓存或空结构
            return cache.get('data') or {"tools": []}

    async def _get_tool_names(self) -> List[str]:
        specs = await self._get_tool_specs()
        tools = specs.get('tools') or []
        names = []
        for t in tools:
            n = (t or {}).get('name')
            if isinstance(n, str):
                names.append(n)
        return names
    
    async def _fetch_mcp_tools_meta(self) -> List[Dict[str, Any]]:
        """获取MCP工具元数据，用于智能判断工具复杂度"""
        specs = await self._get_tool_specs()
        return specs.get('tools') or []
    
    async def _get_tool_capabilities(self, tool_name: str) -> Dict[str, Any]:
        """获取工具的能力标识"""
        try:
            tools_meta = await self._fetch_mcp_tools_meta()
            for tool in tools_meta:
                if tool.get('name') == tool_name:
                    return tool.get('x_capabilities', {})
        except Exception:
            pass
        return {}
    
    async def _tool_requires_user_id(self, tool_name: str) -> bool:
        """智能判断工具是否需要user_id参数"""
        try:
            tools_meta = await self._fetch_mcp_tools_meta()
            for tool in tools_meta:
                if tool.get('name') == tool_name:
                    # 检查输入schema中是否有user_id
                    input_schema = tool.get('x_input_schema', {})
                    if isinstance(input_schema, dict):
                        properties = input_schema.get('properties', {})
                        if 'user_id' in properties:
                            return True
                    
                    # 检查能力标识
                    capabilities = tool.get('x_capabilities', {})
                    # 数据库操作通常需要user_id
                    if capabilities.get('uses_database') or capabilities.get('user_scoped'):
                        return True
                    
                    return False
        except Exception:
            pass
        
        # 回退到已知需要user_id的工具（保留最小必要的硬编码）
        return tool_name in {"store", "search", "aggregate", "get_pending_reminders", "batch_store", "batch_search"}
    



    async def _resolve_user_id(self, user_id: str, context: Optional[Dict[str, Any]] = None) -> str:
        """智能解析用户ID：字符串ID到UUID的映射"""
        if not user_id:
            return user_id
            
        # 如果已经是UUID格式，直接返回
        if _looks_like_uuid(user_id):
            return user_id
            
        try:
            # 尝试通过thread_id查找真实用户ID
            thread_id = user_id
            if context and context.get('thread_id'):
                thread_id = context.get('thread_id')
            
            logger.info("user_id_resolution_start", original=user_id, thread_id=thread_id)
            
            # 直接调用MCP HTTP接口，避免递归调用_call_mcp_tool
            if self._http_client is None:
                self._http_client = httpx.AsyncClient()
            
            response = await self._http_client.post(
                f"{self.mcp_url}/tool/search",
                json={
                    'query': '',
                    'filters': {'limit': 1, 'thread_id': thread_id},
                    'user_id': user_id  # 让MCP直接处理，跳过递归解析
                },
                timeout=3.0
            )
            
            logger.info("user_id_resolution_response", status_code=response.status_code)
            
            if response.status_code == 200:
                search_result = response.json()
                logger.info("user_id_resolution_data", data_type=type(search_result).__name__, data_length=len(search_result) if isinstance(search_result, list) else 0)
                
                if isinstance(search_result, list) and search_result:
                    record = search_result[0]
                    if isinstance(record, dict):
                        # 从记录中提取真实的user_id
                        db_user_id = record.get('user_id')
                        logger.info("user_id_resolution_extract", db_user_id=str(db_user_id), is_uuid=_looks_like_uuid(str(db_user_id)) if db_user_id else False)
                        
                        if db_user_id and _looks_like_uuid(str(db_user_id)):
                            logger.info("user_id_resolved", original=user_id, resolved=str(db_user_id), thread_id=thread_id)
                            return str(db_user_id)
                else:
                    logger.warning("user_id_resolution_no_results", thread_id=thread_id)
            else:
                logger.warning("user_id_resolution_http_error", status_code=response.status_code)
        except Exception as e:
            logger.warning("user_id_resolution_failed", original=user_id, error=str(e))
        
        # 回退：返回原始user_id
        return user_id
    
    async def _tool_supports_embedding(self, tool_name: str) -> bool:
        """智能判断工具是否支持向量嵌入"""
        try:
            capabilities = await self._get_tool_capabilities(tool_name)
            return capabilities.get('uses_vector', False) or capabilities.get('supports_embedding', False)
        except Exception:
            pass
        
        # 回退到已知支持嵌入的工具
        return tool_name in {"store", "search"}
    
    async def _get_tool_output_type(self, tool_name: str) -> str:
        """智能判断工具的输出类型"""
        try:
            tools_meta = await self._fetch_mcp_tools_meta()
            for tool in tools_meta:
                if tool.get('name') == tool_name:
                    output_schema = tool.get('x_output_schema', {})
                    if isinstance(output_schema, dict):
                        # 检查输出schema的特征
                        properties = output_schema.get('properties', {})
                        if 'id' in properties:
                            return 'entity_with_id'  # store类型
                        elif 'result' in properties or 'groups' in properties:
                            return 'aggregation'     # aggregate类型
                        elif 'total_amount' in properties or 'category_breakdown' in properties:
                            return 'summary'         # 优化工具类型
                        elif isinstance(properties, dict) and len(properties) > 3:
                            return 'complex'         # 复杂输出
                        else:
                            return 'simple'          # 简单输出
        except Exception:
            pass
        
        # 回退到基于工具名的判断
        if tool_name == 'store':
            return 'entity_with_id'
        elif tool_name == 'aggregate':
            return 'aggregation' 
        elif tool_name in ['get_expense_summary_optimized', 'get_health_summary_optimized', 'get_learning_progress_optimized', 'get_data_type_summary_optimized']:
            return 'summary'
        else:
            return 'simple'
    
    def _convert_summary_to_aggregation(self, tool_name: str, summary_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """将摘要工具结果转换为聚合格式，供图表使用"""
        try:
            # 基于工具类型智能转换
            if 'expense' in tool_name.lower():
                category_breakdown = summary_result.get('category_breakdown', {})
                if category_breakdown:
                    groups = []
                    for category, amount in category_breakdown.items():
                        groups.append({
                            'group': {'ai_group': category},
                            'result': float(amount)
                        })
                    return {
                        'operation': 'sum',
                        'field': 'amount',
                        'result': summary_result.get('total_amount', 0),
                        'groups': groups
                    }
            elif 'health' in tool_name.lower():
                # 健康数据的转换逻辑
                timeline_data = summary_result.get('timeline_data', [])
                if timeline_data:
                    groups = []
                    for record in timeline_data:
                        groups.append({
                            'group': {'period': record.get('date', 'Unknown')},
                            'result': float(record.get('value', 0))
                        })
                    return {
                        'operation': 'avg',
                        'field': 'value',
                        'result': summary_result.get('latest_value', 0),
                        'groups': groups
                    }
            elif 'learning' in tool_name.lower():
                # 学习进展的转换逻辑
                score_distribution = summary_result.get('score_distribution', {})
                if score_distribution:
                    groups = []
                    for score_range, count in score_distribution.items():
                        groups.append({
                            'group': {'ai_group': score_range},
                            'result': float(count)
                        })
                    return {
                        'operation': 'count',
                        'field': 'score',
                        'result': summary_result.get('total_records', 0),
                        'groups': groups
                    }
            
            # 通用转换：尝试从任何包含分组数据的字段提取
            for key in ['breakdown', 'distribution', 'summary_by_type']:
                breakdown = summary_result.get(key, {})
                if isinstance(breakdown, dict) and breakdown:
                    groups = []
                    for label, value in breakdown.items():
                        groups.append({
                            'group': {'ai_group': label},
                            'result': float(value) if isinstance(value, (int, float)) else 0
                        })
                    return {
                        'operation': 'sum',
                        'field': 'value',
                        'result': sum(float(v) for v in breakdown.values() if isinstance(v, (int, float))),
                        'groups': groups
                    }
        except Exception:
            pass
        
        return None
    
    async def _get_tool_time_budget(self, tool_name: str) -> float:
        """从 /tools 中读取 x_time_budget，未命中则按默认值。单位：秒。"""
        try:
            specs = await self._get_tool_specs()
            for t in specs.get('tools') or []:
                if t.get('name') == tool_name:
                    tb = t.get('x_time_budget')
                    if isinstance(tb, (int, float)):
                        return float(tb)
        except Exception:
            pass
        # 默认预算
        defaults = {
            'store': 2.0,
            'search': 3.0,
            'aggregate': 3.0,
            'schedule_reminder': 2.0,
            'get_pending_reminders': 3.0,
            'mark_reminder_sent': 2.0,
            'batch_store': 5.0,
            'batch_search': 5.0,
            'update_memory_fields': 2.0,
            'soft_delete': 2.0,
            'reembed_memories': 5.0,
            'render_chart': 6.0,
        }
        return defaults.get(tool_name, 3.0)

    def _emb_global_get(self, key: str) -> Optional[List[float]]:
        item = self._emb_cache_global.get(key)
        if not item:
            return None
        vec, ts = item
        if (time.time() - ts) > self._emb_cache_global_ttl:
            try:
                self._emb_cache_global.pop(key, None)
            except Exception:
                pass
            return None
        return vec

    def _emb_global_put(self, key: str, vec: Optional[List[float]]) -> None:
        if not vec:
            return
        # 容量控制（最简单的随机淘汰/先进先出近似）
        try:
            if len(self._emb_cache_global) >= self._emb_cache_global_max_items:
                # pop 任意一个最旧项
                oldest_key = None
                oldest_ts = float('inf')
                for k, (_, ts) in self._emb_cache_global.items():
                    if ts < oldest_ts:
                        oldest_key, oldest_ts = k, ts
                if oldest_key:
                    self._emb_cache_global.pop(oldest_key, None)
        except Exception:
            pass
        self._emb_cache_global[key] = (vec, time.time())

    async def _get_embedding_cached(self, text: str, trace_id: Optional[str]) -> Optional[List[float]]:
        if not text:
            return None
        # trace 级
        cache = self._emb_cache_by_trace.get(trace_id or '', {})
        if text in cache:
            return cache[text]
        # 全局级
        vec = self._emb_global_get(text)
        if vec is not None:
            cache[text] = vec
            if trace_id:
                self._emb_cache_by_trace[trace_id] = cache
            return vec
        # 生成
        try:
            embs = await self.llm.embed([text])
            vec = [float(x) for x in (embs[0] or [])] if embs else None
        except Exception:
            vec = None
        if vec is not None:
            cache[text] = vec
            if trace_id:
                self._emb_cache_by_trace[trace_id] = cache
            self._emb_global_put(text, vec)
        return vec
    
    async def process_message(self, content: str, user_id: str, context: Dict[str, Any] = None) -> str:
        """处理用户消息的主入口 - 统一的 AI 驱动流程
        
        核心流程：
        1. 预处理：附件衍生文本合并到消息内容
        2. 统一理解：AI 分析消息意图、提取实体、判断是否需要澄清
        3. 澄清处理：如果信息不完整，生成澄清问题并返回
        4. 上下文获取：根据 AI 需求获取历史记录、语义搜索等上下文
        5. 工具执行：根据 AI 计划执行工具调用（存储、搜索、聚合等）
        6. 回复生成：根据执行结果生成最终回复
        7. 持久化：存储对话回合和交互轨迹
        
        Args:
            content: 用户输入的消息内容
            user_id: 用户标识（UUID 或可映射为 UUID 的字符串）
            context: 上下文信息（包含 thread_id、channel、attachments 等）
            
        Returns:
            AI 生成的回复文本
        """
        # 为每个请求生成唯一的追踪 ID，用于日志关联和问题排查
        trace_id = str(uuid.uuid4())
        thread_id = (context or {}).get('thread_id') if context else None
        channel = (context or {}).get('channel') if context else None

        logger.info(
            "message.received",
            trace_id=trace_id,
            user_id=user_id,
            thread_id=thread_id,
            channel=channel,
            message_id=(context or {}).get('message_id') if context else None,
            content_preview=content[:200]
        )

        try:
            self._tool_calls_by_trace[trace_id] = []
            self._emb_cache_by_trace[trace_id] = {}

            attachments = (context or {}).get('attachments') if context else None
            derived_texts: List[str] = []
            if isinstance(attachments, list):
                for att in attachments:
                    if not isinstance(att, dict):
                        continue
                    tx = att.get('transcription', {}).get('text') if isinstance(att.get('transcription'), dict) else None
                    if not tx:
                        tx = att.get('ocr_text')
                    if not tx:
                        tx = att.get('vision_summary')
                    if tx:
                        derived_texts.append(str(tx))
            if derived_texts:
                base = (content or '').strip()
                extra = "\n\n[附件提取]\n" + "\n".join(derived_texts)
                content = f"{base}{extra}" if base else "\n".join(derived_texts)

            shared_thread = bool((context or {}).get('shared_thread') or (context or {}).get('conversation_scope') == 'shared')
            light_context = await self._get_recent_memories(
                user_id=user_id,
                limit=4,
                thread_id=thread_id,
                shared_thread=shared_thread,
                channel=channel,
            )

            household_context = await self._household_service.get_context()

            analysis = await self._analyze_message(
                content=content,
                user_id=user_id,
                context=context,
                trace_id=trace_id,
                profile_hint=self._profile_for_context(context),
                light_context=light_context,
                household_context=household_context,
            )

            understanding = analysis.get('understanding', {})
            understanding['original_content'] = content

            if understanding.get('need_clarification'):
                response_directives = analysis.get('response_directives') or {}
                profile = self._profile_for_context(context, response_directives)
                response = await self._generate_clarification_response(
                    original_message=content,
                    understanding=understanding,
                    context=context,
                    profile=profile,
                    response_directives=response_directives,
                    context_payload={'household': household_context},
                )
                result = {'actions_taken': []}

                await self._store_chat_turns_safely(user_id, thread_id, trace_id, content, response, understanding, context)
                await self._persist_interaction_safely(trace_id, user_id, thread_id, channel, context, content, understanding, result, response)
                return response

            response_directives = analysis.get('response_directives') or {}
            profile = self._profile_for_context(context, response_directives)

            context_requests = analysis.get('context_requests') or []
            resolved_context = await self._resolve_context_requests(
                context_requests=context_requests,
                understanding=understanding,
                user_id=user_id,
                context=context,
                trace_id=trace_id,
            )
            context_payload: Dict[str, Any] = {'household': household_context}
            if isinstance(resolved_context, dict):
                context_payload.update(resolved_context)

            plan = await self._build_tool_plan(
                understanding=understanding,
                user_id=user_id,
                context=context,
                profile=profile,
                context_payload=context_payload,
                analysis_plan=analysis.get('tool_plan') or {},
            )
            steps = plan.get('steps') or []

            result = await self._execute_tool_steps(
                steps,
                understanding,
                user_id,
                context=context,
                trace_id=trace_id,
                context_data=context_payload,
            )

            actions_list = result.get('actions_taken', []) if isinstance(result, dict) else []
            logger.info(
                "plan.execution.summary",
                actions=len(actions_list),
                trace_id=trace_id,
                intent=understanding.get('intent'),
                action_types=[(a or {}).get('action') for a in actions_list],
            )

            if await self._is_simple_actions_only(steps):
                response = await self._build_simple_ack_response(
                    understanding=understanding,
                    execution_result=result,
                    context=context,
                    profile=profile,
                    response_directives=response_directives,
                    context_payload=context_payload,
                )
            else:
                response = await self._generate_normal_response(
                    original_message=content,
                    understanding=understanding,
                    execution_result=result,
                    context=context,
                    profile=profile,
                    response_directives=response_directives,
                    context_payload=context_payload,
                )

            await self._store_chat_turns_safely(user_id, thread_id, trace_id, content, response, understanding, context)

            if not self._is_low_budget_mode():
                try:
                    import asyncio as _asyncio
                    _asyncio.create_task(self._maybe_summarize_thread(user_id=user_id, thread_id=thread_id, trace_id=trace_id))
                except Exception as summarise_exc:
                    logger.warning("thread.summarize.skip", trace_id=trace_id, error=str(summarise_exc))

            await self._persist_interaction_safely(trace_id, user_id, thread_id, channel, context, content, understanding, result, response)

            return response

        except Exception as exc:
            logger.error("message.process.error", trace_id=trace_id, error=str(exc))
            return "抱歉，处理您的消息时出现了错误。"
        finally:
            try:
                self._tool_calls_by_trace.pop(trace_id, None)
                self._emb_cache_by_trace.pop(trace_id, None)
            except Exception:
                pass

    def _is_low_budget_mode(self) -> bool:
        """检查是否处于低预算/冷却模式"""
        low_budget = bool(getattr(settings, 'LOW_LLM_BUDGET', False))
        try:
            from .core.llm_client import LLMClient as _LLMClient
            if hasattr(_LLMClient, 'in_cooldown') and callable(getattr(_LLMClient, 'in_cooldown')) and _LLMClient.in_cooldown():
                low_budget = True
        except Exception:
            pass
        return low_budget

    def _can_use_ai_suggested_response(self, understanding: Dict[str, Any]) -> bool:
        """检查AI是否在理解阶段提供了高质量的建议回复（AI驱动优化）"""
        suggested_actions = understanding.get('suggested_actions', [])
        if not suggested_actions or not isinstance(suggested_actions, list):
            return False
            
        # AI标识这是简单操作且提供了具体回复
        first_suggestion = suggested_actions[0]
        if isinstance(first_suggestion, str) and len(first_suggestion.strip()) > 5:
            return True
        elif isinstance(first_suggestion, dict) and 'text' in first_suggestion:
            text = first_suggestion.get('text', '')
            return isinstance(text, str) and len(text.strip()) > 5
        
        return False

    def _looks_like_simple_operation(self, understanding: Dict[str, Any]) -> bool:
        """判断是否是简单操作（AI驱动判断逻辑）"""
        if not understanding.get('need_action', False):
            return True
        
        # AI标识的常见简单操作意图
        intent = understanding.get('intent', '').lower()
        simple_intents = {
            'record_expense', 'record_income', 'record_health',
            'store_info', 'schedule_reminder', 'quick_note'
        }
        
        if any(simple_intent in intent for simple_intent in simple_intents):
            return True
            
        # 检查是否有明确的实体信息（AI已理解完整）
        entities = understanding.get('entities', {})
        return len(entities) >= 2  # 有足够信息进行简单操作

    def _extract_plan_from_understanding(self, understanding: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从AI理解结果中智能提取执行计划（避免二次LLM调用）"""
        if not understanding.get('need_action', False):
            return []
            
        intent = understanding.get('intent', '').lower()
        entities = understanding.get('entities', {})
        
        # 根据AI识别的意图，生成对应的工具调用计划
        if any(keyword in intent for keyword in ['record', 'store', 'save', 'remember']):
            # 存储类操作
            return [{
                'tool': 'store',
                'args': {
                    'content': understanding.get('original_content', ''),
                    'ai_data': entities
                }
            }]
        elif 'remind' in intent and entities.get('datetime'):
            # 提醒类操作
            return [
                {
                    'tool': 'store',
                    'args': {
                        'content': understanding.get('original_content', ''),
                        'ai_data': entities
                    }
                },
                {
                    'tool': 'schedule_reminder', 
                    'args': {
                        'remind_at': entities.get('datetime')
                    }
                }
            ]
        
        return []  # 复杂操作返回空，让AI单独制定计划

    async def _store_chat_turns_safely(self, user_id: str, thread_id: Optional[str], trace_id: str, 
                                      user_message: str, assistant_message: str, 
                                      understanding: Dict[str, Any], context: Optional[Dict[str, Any]]) -> None:
        """安全地存储对话回合"""
        try:
            await self._store_chat_turns(
                user_id=user_id,
                thread_id=thread_id,
                trace_id=trace_id,
                user_message=user_message,
                assistant_message=assistant_message,
                understanding=understanding,
                context=context,
            )
        except Exception as e:
            logger.error("store.chat_turns.failed", trace_id=trace_id, error=str(e))

    async def _persist_interaction_safely(self, trace_id: str, user_id: str, thread_id: Optional[str], 
                                         channel: Optional[str], context: Optional[Dict[str, Any]], 
                                         content: str, understanding: Dict[str, Any], 
                                         result: Dict[str, Any], response: str) -> None:
        """安全地持久化交互轨迹"""
        try:
            tool_calls = self._tool_calls_by_trace.get(trace_id, [])
            await self._persist_interaction(
                trace_id=trace_id,
                user_id=user_id,
                thread_id=thread_id,
                channel=channel,
                message_id=(context or {}).get('message_id') if context else None,
                input_text=content,
                understanding=understanding,
                actions=result,
                response_text=response,
                tool_calls=tool_calls,
            )
        except Exception as e:
            logger.error("interaction.persist.failed", trace_id=trace_id, error=str(e))
    
    async def _get_recent_memories(self, user_id: str, limit: int = 5, thread_id: Optional[str] = None, *, shared_thread: bool = False, channel: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取用户最近的交互记录，用于上下文理解

        Args:
            user_id: 归属用户
            limit: 返回数量上限
            thread_id: 线程标识（用于连续上下文）
            shared_thread: 是否按线程跨用户共享检索
            channel: 渠道（如 threema/api），用于在共享线程下进一步限定
        """
        try:
            # 获取最近的记忆
            filters = {'limit': limit}
            if thread_id:
                filters['thread_id'] = thread_id
                filters['type'] = 'chat_turn'
                if shared_thread:
                    filters['shared_thread'] = True
                if channel:
                    filters['channel'] = channel
            recent_memories = await self._call_mcp_tool(
                'search',
                query='',  # 空查询获取最新记录
                user_id=user_id,
                filters=filters
            )
            
            # 格式化记忆，提取关键信息
            formatted_memories = []
            for memory in recent_memories:
                if isinstance(memory, dict) and not memory.get('_meta'):
                    aiu = memory.get('ai_understanding', {}) if isinstance(memory.get('ai_understanding'), dict) else {}
                    # 时间优先 occurred_at，其次 ai_understanding.timestamp
                    occurred_at = memory.get('occurred_at', '')
                    ts_fallback = ''
                    try:
                        ts_fallback = aiu.get('timestamp', '') if isinstance(aiu, dict) else ''
                    except Exception:
                        ts_fallback = ''
                    formatted_memories.append({
                        'content': memory.get('content', ''),
                        'ai_understanding': aiu,
                        'time': occurred_at or ts_fallback
                    })
            
            return formatted_memories
            
        except Exception as e:
            logger.error(f"Error getting recent memories: {e}")
            return []
    
    async def _analyze_message(
        self,
        *,
        content: str,
        user_id: str,
        context: Optional[Dict[str, Any]],
        trace_id: str,
        profile_hint: Optional[str],
        light_context: List[Dict[str, Any]],
        household_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        thread_id = (context or {}).get('thread_id') if context else None
        channel = (context or {}).get('channel') if context else None
        profile = profile_hint

        system_prompt = await prompt_manager.get_system_prompt_with_tools(profile)
        understanding_prompt = prompt_manager.get_understanding_prompt(profile)

        payload = {
            "message": content,
            "user": {
                "id": user_id,
                "thread_id": thread_id,
                "channel": channel,
            },
            "context": {
                "shared_thread": bool((context or {}).get('shared_thread') or (context or {}).get('conversation_scope') == 'shared'),
                "light_context": light_context,
                "metadata": {
                    "utc_now": datetime.utcnow().isoformat(),
                    "low_budget": self._is_low_budget_mode(),
                },
                "household": household_context,
            },
        }

        prompt_parts: List[str] = []
        if understanding_prompt:
            prompt_parts.append(understanding_prompt)
        prompt_parts.append("输入：")
        prompt_parts.append(self._safe_json_dumps(payload))
        prompt_parts.append("请仅返回契约描述的 JSON，不要添加解释。")
        user_prompt = "\n\n".join(prompt_parts)

        try:
            raw_response = await self.llm.chat_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.2,
                max_tokens=1200,
            )
            response_obj = raw_response if isinstance(raw_response, dict) else {}
        except Exception as exc:
            logger.warning("llm.analysis.retry", trace_id=trace_id, error=str(exc))
            raw_text = await self.llm.chat_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.2,
                max_tokens=1200,
            )
            try:
                start_idx = raw_text.find('{')
                end_idx = raw_text.rfind('}')
                response_obj = json.loads(raw_text[start_idx:end_idx + 1]) if start_idx != -1 and end_idx != -1 else {}
            except Exception:
                response_obj = {}

        try:
            parsed = AnalysisModel(**response_obj)
            analysis = parsed.model_dump()
        except ValidationError as ve:
            logger.warning("llm.analysis.validation_failed", trace_id=trace_id, error=str(ve))
            understanding = response_obj.get('understanding') or {}
            analysis = {
                'understanding': {
                    'intent': understanding.get('intent'),
                    'entities': understanding.get('entities') or {},
                    'need_action': bool(understanding.get('need_action')),
                    'need_clarification': bool(understanding.get('need_clarification')),
                    'missing_fields': understanding.get('missing_fields') or [],
                    'clarification_questions': understanding.get('clarification_questions') or [],
                    'suggested_reply': understanding.get('suggested_reply'),
                    'context_link': understanding.get('context_link') or {},
                    'occurred_at': understanding.get('occurred_at'),
                    'update_existing': understanding.get('update_existing'),
                    'metadata': understanding.get('metadata') or {},
                },
                'context_requests': response_obj.get('context_requests') or [],
                'tool_plan': response_obj.get('tool_plan') or {'steps': []},
                'response_directives': response_obj.get('response_directives') or {},
            }

        if not isinstance(analysis.get('context_requests'), list):
            analysis['context_requests'] = []
        if not isinstance(analysis.get('tool_plan'), dict):
            analysis['tool_plan'] = {'steps': []}
        if not isinstance(analysis.get('response_directives'), dict):
            analysis['response_directives'] = {}

        logger.info(
            "llm.analysis.response",
            trace_id=trace_id,
            intent=analysis['understanding'].get('intent'),
            need_action=analysis['understanding'].get('need_action'),
            need_clarification=analysis['understanding'].get('need_clarification'),
            context_requests=len(analysis.get('context_requests') or []),
            tool_steps=len((analysis.get('tool_plan') or {}).get('steps') or []),
        )

        return analysis

    async def _resolve_context_requests(
        self,
        *,
        context_requests: List[Dict[str, Any]],
        understanding: Dict[str, Any],
        user_id: str,
        context: Optional[Dict[str, Any]],
        trace_id: str,
    ) -> Dict[str, Any]:
        if not context_requests:
            return {}

        resolved: Dict[str, Any] = {}
        thread_id = (context or {}).get('thread_id') if context else None
        channel = (context or {}).get('channel') if context else None
        shared_thread = bool((context or {}).get('shared_thread') or (context or {}).get('conversation_scope') == 'shared')

        for req in context_requests:
            if not isinstance(req, dict):
                continue
            name = req.get('name')
            kind = req.get('kind')
            if not name or not kind:
                continue
            try:
                if kind == 'recent_memories':
                    limit = int(req.get('limit') or 6)
                    resolved[name] = await self._get_recent_memories(
                        user_id=user_id,
                        limit=limit,
                        thread_id=thread_id,
                        shared_thread=shared_thread,
                        channel=channel,
                    )
                elif kind == 'thread_summaries':
                    limit = int(req.get('limit') or 1)
                    resolved[name] = await self._get_recent_thread_summaries(
                        user_id=user_id,
                        thread_id=thread_id,
                        limit=limit,
                        shared_thread=shared_thread,
                        channel=channel,
                    )
                elif kind == 'semantic_search':
                    query = req.get('query') or understanding.get('original_content') or understanding.get('intent') or ''
                    limit = int(req.get('limit') or 5)
                    results = await self._semantic_search(
                        user_id=user_id,
                        query=query,
                        top_k=limit,
                        thread_id=thread_id,
                        shared_thread=shared_thread,
                        channel=channel,
                    )
                    resolved[name] = results
                elif kind == 'direct_search':
                    filters = req.get('filters') if isinstance(req.get('filters'), dict) else {}
                    limit = int(req.get('limit') or 20)
                    filters = {**filters, 'limit': limit}
                    if thread_id and 'thread_id' not in filters:
                        filters['thread_id'] = thread_id
                    if shared_thread:
                        filters.setdefault('shared_thread', True)
                    resolved[name] = await self._call_mcp_tool(
                        'search',
                        query=req.get('query', ''),
                        filters=filters,
                        user_id=user_id,
                        trace_id=trace_id,
                    )
                else:
                    logger.info("context_request.skipped", trace_id=trace_id, name=name, kind=kind)
            except Exception as exc:
                logger.warning("context_request.failed", trace_id=trace_id, name=name, kind=kind, error=str(exc))

        return resolved

    @staticmethod
    def _extract_from_path(data: Any, path: Optional[str]) -> Any:
        if path is None or path == '':
            return data
        current = data
        for segment in path.split('.'):
            if isinstance(current, list):
                if segment == 'last':
                    current = current[-1] if current else None
                elif segment.isdigit():
                    idx = int(segment)
                    current = current[idx] if 0 <= idx < len(current) else None
                else:
                    current = None
            elif isinstance(current, dict):
                current = current.get(segment)
            else:
                current = None
            if current is None:
                break
        return current

    def _resolve_context_reference(self, ref: Dict[str, Any], context_data: Dict[str, Any]) -> Any:
        context_name = ref.get('use_context')
        if not context_name:
            return ref
        source = context_data.get(context_name)
        if source is None:
            return ref.get('fallback')
        path = ref.get('path')
        value = self._extract_from_path(source, path)
        if value is None:
            return ref.get('fallback')
        return value

    def _resolve_args_with_context(
        self,
        value: Any,
        *,
        context_data: Dict[str, Any],
        last_store_id: Optional[str],
        last_aggregate_result: Optional[Dict[str, Any]],
    ) -> Any:
        if isinstance(value, dict):
            if 'use_context' in value:
                return self._resolve_context_reference(value, context_data)
            return {
                k: self._resolve_args_with_context(v, context_data=context_data, last_store_id=last_store_id, last_aggregate_result=last_aggregate_result)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [
                self._resolve_args_with_context(item, context_data=context_data, last_store_id=last_store_id, last_aggregate_result=last_aggregate_result)
                for item in value
            ]
        if isinstance(value, str):
            if value == '$LAST_STORE_ID':
                return last_store_id
            if value == '$LAST_AGGREGATION':
                return last_aggregate_result
        return value

    async def _build_tool_plan(
        self,
        *,
        understanding: Dict[str, Any],
        user_id: str,
        context: Optional[Dict[str, Any]],
        profile: Optional[str],
        context_payload: Dict[str, Any],
        analysis_plan: Dict[str, Any],
    ) -> Dict[str, Any]:
        existing_steps = (analysis_plan or {}).get('steps')
        requires_context = (analysis_plan or {}).get('requires_context') or []
        if isinstance(existing_steps, list) and not requires_context:
            return {'steps': existing_steps}

        system_prompt = await prompt_manager.get_system_prompt_with_tools(profile)
        planning_prompt = await prompt_manager.get_tool_planning_prompt_with_tools(profile)

        payload = {
            'understanding': understanding,
            'analysis_plan': analysis_plan,
            'context_payload': context_payload,
            'user': {
                'id': user_id,
                'channel': (context or {}).get('channel') if context else None,
                'thread_id': (context or {}).get('thread_id') if context else None,
            },
        }

        prompt_parts = []
        if planning_prompt:
            prompt_parts.append(planning_prompt)
        prompt_parts.append('输入数据：')
        prompt_parts.append(self._safe_json_dumps(payload))
        prompt_parts.append('请仅返回 JSON：{"steps": [...], "meta": {...可选}}，不要附加解释。')
        user_prompt = "\n\n".join(prompt_parts)

        try:
            plan = await self.llm.chat_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.2,
                max_tokens=800,
            )
            if not isinstance(plan, dict):
                return {'steps': []}
            steps = plan.get('steps')
            if not isinstance(steps, list):
                return {'steps': []}
            return {'steps': steps, 'meta': plan.get('meta')}
        except Exception as exc:
            logger.warning('tool_plan.fallback', error=str(exc))
            return {'steps': []}
    
    async def _is_simple_actions_only(self, steps: List[Dict[str, Any]]) -> bool:
        """
        基于MCP工具元数据智能判断是否为简单操作
        避免硬编码工具名，支持AI自动进化
        """
        if not steps:
            return True
        
        # 获取工具元数据
        try:
            tools_meta = await self._fetch_mcp_tools_meta()
            tool_info = {tool['name']: tool for tool in tools_meta}
        except Exception:
            # 回退到保守策略：包含已知复杂操作的工具名
            known_complex = {"search", "aggregate", "render_chart"}
            return all((s or {}).get('tool') not in known_complex for s in steps)
        
        # 基于元数据智能判断
        for s in steps:
            tool_name = (s or {}).get('tool')
            if not tool_name or tool_name not in tool_info:
                continue
                
            tool = tool_info[tool_name]
            
            # 判断条件（任一满足即为复杂操作）：
            # 1. 延迟等级为 medium/high （需要详细回复展示结果）
            latency = tool.get('x_latency_hint')
            if latency in ['medium', 'high']:
                return False
                
            # 2. 时间预算 > 2.5秒 （耗时操作需要向用户解释结果）
            time_budget = tool.get('x_time_budget')
            if isinstance(time_budget, (int, float)) and time_budget > 2.5:
                return False
                
            # 3. 具备复杂能力标识（查询、聚合、可视化等）
            capabilities = tool.get('x_capabilities', {})
            complex_capabilities = ['supports_group_by', 'supports_filters', 'database_optimized', 'trend_analysis', 'universal_aggregation']
            if any(capabilities.get(cap) for cap in complex_capabilities):
                return False
                
        return True
    
    async def _execute_tool_steps(
        self,
        steps: List[Dict[str, Any]],
        understanding: Dict[str, Any],
        user_id: str,
        *,
        context: Optional[Dict[str, Any]] = None,
        trace_id: str,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """执行给定的工具步骤，支持引用上下文与常用占位符。"""
        executed: Dict[str, Any] = {"actions_taken": []}
        if not steps:
            return executed

        try:
            dynamic_tools = await self._get_tool_names()
        except Exception:
            dynamic_tools = [
                "store",
                "search",
                "aggregate",
                "schedule_reminder",
                "get_pending_reminders",
                "mark_reminder_sent",
                "update_memory_fields",
                "render_chart",
                "batch_store",
                "batch_search",
                "soft_delete",
                "reembed_memories",
            ]
            logger.warning("MCP server unavailable, using fallback tools")

        allowed_tools = set(dynamic_tools)
        context_data = context_data or {}
        last_store_id: Optional[str] = None
        last_aggregate_result: Optional[Dict[str, Any]] = None

        for step in steps:
            if not isinstance(step, dict):
                continue
            tool = step.get('tool')
            if not tool or tool not in allowed_tools:
                continue

            raw_args = step.get('args') or {}
            args = self._resolve_args_with_context(
                raw_args,
                context_data=context_data,
                last_store_id=last_store_id,
                last_aggregate_result=last_aggregate_result,
            )

            if 'user_id' in args and isinstance(args['user_id'], str):
                if args['user_id'] in {'family', 'family_scope'}:
                    household_scope = (context_data.get('household') or {}).get('family_scope') if isinstance(context_data, dict) else None
                    user_ids = []
                    if isinstance(household_scope, dict):
                        user_ids = household_scope.get('user_ids') or []
                    if user_ids:
                        args['user_id'] = user_ids

            if await self._tool_requires_user_id(tool) and 'user_id' not in args:
                args['user_id'] = await self._resolve_user_id(user_id, context)

            try:
                if await self._tool_supports_embedding(tool):
                    if 'content' in args and 'embedding' not in args:
                        text_for_embed = args.get('content') or understanding.get('original_content', '')
                        if text_for_embed:
                            args['embedding'] = await self._get_embedding_cached(text_for_embed, trace_id)
                    if 'query' in args and 'query_embedding' not in args:
                        query_text = args.get('query')
                        if query_text:
                            args['query_embedding'] = await self._get_embedding_cached(query_text, trace_id)

                output_type = await self._get_tool_output_type(tool)
                if output_type == 'entity_with_id' and 'ai_data' in args:
                    ai_data = args.get('ai_data') or {}
                    entities = understanding.get('entities', {})
                    merged = {**entities, **ai_data}
                    merged.setdefault('occurred_at', understanding.get('occurred_at') or datetime.now().isoformat())
                    if context and context.get('thread_id'):
                        merged.setdefault('thread_id', context.get('thread_id'))
                    merged.setdefault('trace_id', trace_id)
                    args['ai_data'] = merged
            except Exception as prep_exc:
                logger.debug("tool.prep.warning", trace_id=trace_id, tool=tool, error=str(prep_exc))

            exec_result = await self._call_mcp_tool(tool, trace_id=trace_id, **args)
            executed['actions_taken'].append({'action': tool, 'result': exec_result})

            if isinstance(exec_result, dict):
                context_data[f"result_{tool}"] = exec_result
            elif isinstance(exec_result, list):
                context_data[f"result_{tool}"] = exec_result

            output_type = await self._get_tool_output_type(tool)
            if output_type == 'entity_with_id' and isinstance(exec_result, dict) and exec_result.get('success'):
                last_store_id = exec_result.get('id') or last_store_id
            elif output_type == 'aggregation' and isinstance(exec_result, dict):
                last_aggregate_result = exec_result
            elif output_type == 'summary' and isinstance(exec_result, dict) and exec_result.get('success'):
                converted = self._convert_summary_to_aggregation(tool, exec_result)
                if converted:
                    last_aggregate_result = converted

            if last_store_id:
                context_data['last_store_id'] = last_store_id
            if last_aggregate_result:
                context_data['last_aggregate_result'] = last_aggregate_result

        return executed

    async def _store_chat_turns_safely(self, user_id: str, thread_id: Optional[str], trace_id: str, 
                                      user_message: str, assistant_message: str, 
                                      understanding: Dict[str, Any], context: Optional[Dict[str, Any]]) -> None:
        """安全地存储对话回合"""
        try:
            await self._store_chat_turns(
                user_id=user_id,
                thread_id=thread_id,
                trace_id=trace_id,
                user_message=user_message,
                assistant_message=assistant_message,
                understanding=understanding,
                context=context,
            )
        except Exception as e:
            logger.error("store.chat_turns.failed", trace_id=trace_id, error=str(e))

    async def _persist_interaction_safely(self, trace_id: str, user_id: str, thread_id: Optional[str], 
                                         channel: Optional[str], context: Optional[Dict[str, Any]], 
                                         content: str, understanding: Dict[str, Any], 
                                         result: Dict[str, Any], response: str) -> None:
        """安全地持久化交互轨迹"""
        try:
            tool_calls = self._tool_calls_by_trace.get(trace_id, [])
            await self._persist_interaction(
                trace_id=trace_id,
                user_id=user_id,
                thread_id=thread_id,
                channel=channel,
                message_id=(context or {}).get('message_id') if context else None,
                input_text=content,
                understanding=understanding,
                actions=result,
                response_text=response,
                tool_calls=tool_calls,
            )
        except Exception as e:
            logger.error("interaction.persist.failed", trace_id=trace_id, error=str(e))
    
    async def _get_recent_memories(self, user_id: str, limit: int = 5, thread_id: Optional[str] = None, *, shared_thread: bool = False, channel: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取用户最近的交互记录，用于上下文理解

        Args:
            user_id: 归属用户
            limit: 返回数量上限
            thread_id: 线程标识（用于连续上下文）
            shared_thread: 是否按线程跨用户共享检索
            channel: 渠道（如 threema/api），用于在共享线程下进一步限定
        """
        try:
            # 获取最近的记忆
            filters = {'limit': limit}
            if thread_id:
                filters['thread_id'] = thread_id
                filters['type'] = 'chat_turn'
                if shared_thread:
                    filters['shared_thread'] = True
                if channel:
                    filters['channel'] = channel
            recent_memories = await self._call_mcp_tool(
                'search',
                query='',  # 空查询获取最新记录
                user_id=user_id,
                filters=filters
            )
            
            # 格式化记忆，提取关键信息
            formatted_memories = []
            for memory in recent_memories:
                if isinstance(memory, dict) and not memory.get('_meta'):
                    aiu = memory.get('ai_understanding', {}) if isinstance(memory.get('ai_understanding'), dict) else {}
                    # 时间优先 occurred_at，其次 ai_understanding.timestamp
                    occurred_at = memory.get('occurred_at', '')
                    ts_fallback = ''
                    try:
                        ts_fallback = aiu.get('timestamp', '') if isinstance(aiu, dict) else ''
                    except Exception:
                        ts_fallback = ''
                    formatted_memories.append({
                        'content': memory.get('content', ''),
                        'ai_understanding': aiu,
                        'time': occurred_at or ts_fallback
                    })
            
            return formatted_memories
            
        except Exception as e:
            logger.error(f"Error getting recent memories: {e}")
            return []

    def _resolve_placeholders(self, data: Any, search_results_cache: Dict[int, List[Dict[str, Any]]]) -> Any:
        """解析工具参数中由LLM生成的占位符（目前支持SEARCH_RESULT）。"""
        if isinstance(data, dict):
            return {k: self._resolve_placeholders(v, search_results_cache) for k, v in data.items()}
        if isinstance(data, list):
            return [self._resolve_placeholders(item, search_results_cache) for item in data]
        if isinstance(data, str):
            resolved = self._resolve_placeholder_string(data, search_results_cache)
            return resolved
        return data

    def _resolve_placeholder_string(self, value: str, search_results_cache: Dict[int, List[Dict[str, Any]]]) -> Any:
        if not value or not isinstance(value, str):
            return value

        match = re.match(r'^\$SEARCH_RESULT_(\d+)(?:\[(\d+)\])?(?:\.([\w_-]+))?$', value)
        if match:
            search_idx = int(match.group(1))
            item_idx = int(match.group(2) or 0)
            field = match.group(3)
            results = search_results_cache.get(search_idx)
            if not results:
                logger.warning("placeholder.search_result.missing", index=search_idx)
                return value
            if item_idx >= len(results):
                logger.warning("placeholder.search_result.out_of_range", index=search_idx, item=item_idx, available=len(results))
                return value
            item = results[item_idx]
            if field:
                if isinstance(item, dict) and field in item:
                    resolved_value = item[field]
                    logger.info("placeholder.search_result.resolved", placeholder=value, resolved=resolved_value)
                    return resolved_value
                logger.warning("placeholder.search_result.field_missing", index=search_idx, item=item_idx, field=field)
                return value
            logger.info("placeholder.search_result.resolved", placeholder=value, resolved=item)
            return item

        return value

    async def _store_chat_turns(
        self,
        *,
        user_id: str,
        thread_id: Optional[str],
        trace_id: str,
        user_message: str,
        assistant_message: str,
        understanding: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """存储一对对话回合，便于连续对话与回溯。"""
        common = {
            'type': 'chat_turn',
            'thread_id': thread_id,
            'trace_id': trace_id,
            'channel': (context or {}).get('channel') if context else None,
            'timestamp': datetime.now().isoformat()
        }
        # 额外持久化关键澄清/更新相关字段，供后续多轮合并使用
        extra_fields = {
            'need_action': understanding.get('need_action'),
            'need_clarification': understanding.get('need_clarification'),
            'missing_fields': understanding.get('missing_fields'),
            'clarification_questions': understanding.get('clarification_questions'),
            'conversation_act': understanding.get('conversation_act'),
            'update_existing': understanding.get('update_existing'),
            'occurred_at': understanding.get('occurred_at') or (understanding.get('entities') or {}).get('occurred_at'),
        }
        user_ai = {**common, 'role': 'user', 'intent': understanding.get('intent'), 'entities': understanding.get('entities', {}), **extra_fields}
        assistant_ai = {**common, 'role': 'assistant', 'intent': understanding.get('intent'), 'entities': understanding.get('entities', {}), **extra_fields}
        # 使用批量存储，且不强制生成 embedding（可后台重嵌）
        memories = [
            {"content": user_message, "ai_data": user_ai, "user_id": user_id},
            {"content": assistant_message, "ai_data": assistant_ai, "user_id": user_id},
        ]
        await self._call_mcp_tool('batch_store', memories=memories, trace_id=trace_id)

    async def _maybe_summarize_thread(self, *, user_id: str, thread_id: Optional[str], trace_id: str) -> None:
        """当同一线程回合数过多时，生成摘要并存储。"""
        if not thread_id:
            return
        # 拉取最近若干条，筛选当线程的 chat_turn（加精确过滤，减少扫描）
        recent = await self._call_mcp_tool('search', query='', user_id=user_id, filters={'limit': 50, 'type': 'chat_turn', 'thread_id': thread_id}, trace_id=trace_id)
        turns = [r for r in recent if isinstance(r, dict)]
        if len(turns) < 12:
            return
        # 生成摘要
        convo_text = "\n".join([f"- {t.get('content','')}" for t in turns[-10:]])
        system_prompt = prompt_manager.get_system_prompt() + "\n请为以上多轮对话生成简洁摘要，保留关键事实、已确认信息与未决问题。"
        user_prompt = f"需要摘要的最近对话片段：\n{convo_text}\n\n请输出 5-8 行的要点列表。"
        summary = await self.llm.chat_text(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.3, max_tokens=200)
        ai_data = {
            'type': 'thread_summary',
            'thread_id': thread_id,
            'trace_id': trace_id,
            'window': 'last_10_turns',
            'timestamp': datetime.now().isoformat()
        }
        _s_emb = None
        try:
            _s_list = await self.llm.embed([summary])
            _s_emb = _s_list[0] if _s_list else None
        except Exception:
            _s_emb = None
        await self._call_mcp_tool('store', content=summary, ai_data=ai_data, user_id=user_id, embedding=_s_emb)

    async def _get_recent_thread_summaries(self, user_id: str, thread_id: Optional[str], limit: int = 1, *, shared_thread: bool = False, channel: Optional[str] = None) -> List[Dict[str, Any]]:
        filters: Dict[str, Any] = {'limit': 30, 'type': 'thread_summary'}
        if thread_id:
            filters['thread_id'] = thread_id
        if shared_thread:
            filters['shared_thread'] = True
        if channel:
            filters['channel'] = channel
        recent = await self._call_mcp_tool('search', query='thread summary', user_id=user_id, filters=filters)
        summaries: List[Dict[str, Any]] = []
        for r in recent:
            if not isinstance(r, dict):
                continue
            aiu = r.get('ai_understanding')
            if isinstance(aiu, dict) and aiu.get('type') == 'thread_summary' and (thread_id is None or aiu.get('thread_id') == thread_id):
                summaries.append({'content': r.get('content',''), 'ai_understanding': aiu, 'time': r.get('occurred_at')})
        return summaries[:limit]

    async def _semantic_search(self, user_id: str, query: str, top_k: int = 5, *, thread_id: Optional[str] = None, shared_thread: bool = False, channel: Optional[str] = None) -> List[Dict[str, Any]]:
        if not query:
            return []
        filters: Dict[str, Any] = {'limit': top_k}
        if thread_id:
            filters['thread_id'] = thread_id
        if shared_thread:
            filters['shared_thread'] = True
        if channel:
            filters['channel'] = channel
        # 统一由引擎侧生成查询向量
        _q_emb = None
        try:
            _q = query if query is not None else ""
            if _q:
                _q_embs = await self.llm.embed([_q])
                _q_emb = _q_embs[0] if _q_embs else None
        except Exception:
            _q_emb = None
        results = await self._call_mcp_tool('search', query=query, user_id=user_id, filters=filters, query_embedding=_q_emb)
        formatted: List[Dict[str, Any]] = []
        for r in results:
            if isinstance(r, dict):
                formatted.append({'content': r.get('content',''), 'ai_understanding': r.get('ai_understanding', {}), 'time': r.get('occurred_at')})
        return formatted

    async def _persist_interaction(
        self,
        *,
        trace_id: str,
        user_id: str,
        thread_id: Optional[str],
        channel: Optional[str],
        message_id: Optional[str],
        input_text: str,
        understanding: Dict[str, Any],
        actions: Dict[str, Any],
        response_text: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        from .db.database import get_session
        from .db.models import Interaction
        # 仅当 user_id 是合法 UUID 时记录，以避免外键错误
        if not _looks_like_uuid(user_id):
            logger.warning("interaction.persist.skip.invalid_user_id", user_id=user_id, trace_id=trace_id)
            return
        async with get_session() as session:
            session.add(Interaction(
                id=uuid.UUID(trace_id) if _looks_like_uuid(trace_id) else uuid.uuid4(),
                user_id=uuid.UUID(user_id),
                thread_id=thread_id,
                channel=channel,
                message_id=message_id,
                input_text=input_text,
                understanding_json=understanding,
                actions_json=actions,
                tool_calls_json=tool_calls or [],
                response_text=response_text,
            ))


    
    async def _build_simple_ack_response(
        self,
        *,
        understanding: Dict[str, Any],
        execution_result: Dict[str, Any],
        context: Optional[Dict[str, Any]],
        profile: Optional[str],
        response_directives: Dict[str, Any],
        context_payload: Dict[str, Any],
    ) -> str:
        if self._can_use_ai_suggested_response(understanding):
            suggested_actions = understanding.get('suggested_actions', [])
            first_suggestion = suggested_actions[0]
            if isinstance(first_suggestion, str):
                return first_suggestion.strip()
            if isinstance(first_suggestion, dict) and 'text' in first_suggestion:
                return str(first_suggestion['text']).strip()

        if self._is_low_budget_mode():
            actions = execution_result.get('actions_taken', [])
            success_count = sum(1 for action in actions if isinstance(action, dict) and (action.get('result') or {}).get('success'))
            return "✅ 已记录！" if success_count else "⚠️ 处理遇到问题，请稍后重试。"

        return await self._generate_ack_with_ai(
            understanding=understanding,
            execution_result=execution_result,
            context=context,
            profile=profile,
            response_directives=response_directives,
            context_payload=context_payload,
        )

    async def _generate_ack_with_ai(
        self,
        *,
        understanding: Dict[str, Any],
        execution_result: Dict[str, Any],
        context: Optional[Dict[str, Any]],
        profile: Optional[str],
        response_directives: Dict[str, Any],
        context_payload: Dict[str, Any],
    ) -> str:
        ack_template = prompt_manager.get_ack_prompt(profile)
        if not ack_template:
            ack_template = "{task_context}"

        task_context = {
            'understanding': understanding,
            'execution_result': execution_result,
            'response_directives': response_directives,
            'context_payload': context_payload,
            'channel': (context or {}).get('channel'),
        }

        system_prompt = await prompt_manager.get_system_prompt_with_tools(profile)
        user_prompt = ack_template.format(task_context=self._safe_json_dumps(task_context))

        try:
            response = await self.llm.chat_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=120,
            )
            return response.strip() if response else "✅ 已完成。"
        except Exception as exc:
            logger.warning('ack.generate.failed', error=str(exc))
            return "✅ 已完成。"

    async def _generate_clarification_response(
        self,
        *,
        original_message: str,
        understanding: Dict[str, Any],
        context: Optional[Dict[str, Any]],
        profile: Optional[str],
        response_directives: Dict[str, Any],
        context_payload: Dict[str, Any],
    ) -> str:
        clar_prompt = prompt_manager.get_response_clarification_prompt(profile)
        system_prompt = await prompt_manager.get_system_prompt_with_tools(profile)
        payload = {
            'original_message': original_message,
            'understanding': understanding,
            'response_directives': response_directives,
            'context_payload': context_payload,
            'channel': (context or {}).get('channel'),
        }
        user_prompt = (
            (clar_prompt + "\n\n" if clar_prompt else "")
            + "输入：\n"
            + self._safe_json_dumps(payload)
            + "\n\n请生成澄清问题。"
        )

        response = await self.llm.chat_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.4,
            max_tokens=220,
        )
        return response.strip() if response else "抱歉，我还需要更多信息。"

    async def _generate_normal_response(
        self,
        *,
        original_message: str,
        understanding: Dict[str, Any],
        execution_result: Dict[str, Any],
        context: Optional[Dict[str, Any]],
        profile: Optional[str],
        response_directives: Dict[str, Any],
        context_payload: Dict[str, Any],
    ) -> str:
        response_prompt = prompt_manager.get_response_prompt(profile)
        system_prompt = await prompt_manager.get_system_prompt_with_tools(profile)
        payload = {
            'original_message': original_message,
            'understanding': understanding,
            'execution_result': execution_result,
            'response_directives': response_directives,
            'context_payload': context_payload,
            'channel': (context or {}).get('channel'),
        }
        user_prompt = (
            (response_prompt + "\n\n" if response_prompt else "")
            + "输入：\n"
            + self._safe_json_dumps(payload)
            + "\n\n请生成最终回复。"
        )

        response = await self.llm.chat_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.6,
            max_tokens=600,
        )
        generated = response.strip() if response else "抱歉，我将继续关注您的需求。"

        if context and context.get('channel') == 'threema' and len(generated) > 400:
            generated = generated[:397] + '...'
        return generated

    async def generate_chart_and_text(self, *, user_id: str, title: str, x: List[str], series: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        M2：通用图表渲染包装。返回 {text, image_path}。
        供未来的 LLM 工具计划或手工调用。
        """
        try:
            render = await self._call_mcp_tool('render_chart', type='line', title=title, x=x, series=series)
            image_path = render.get('path') if isinstance(render, dict) else None
            summary = f"{title}: 共 {len(x)} 个点。"
            return {"text": summary, "image_path": image_path}
        except Exception as e:
            return {"text": f"{title}: 图表生成失败", "error": str(e)}
    
    async def _call_mcp_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """调用 MCP 工具 - AI 引擎与通用工具层的桥接
        
        设计原则：
        1. 工具完全通用化，不含业务逻辑
        2. AI 决定如何使用工具，工程层只负责调用
        3. 支持超时控制、重试机制、结果缓存
        
        Args:
            tool_name: 工具名称（如 store/search/aggregate）
            **kwargs: 工具参数（由 AI 决定的参数内容）
            
        Returns:
            工具执行结果（原始数据，由 AI 解释使用）
        """
        trace_id = kwargs.get('trace_id')

        # 清理与概括参数，避免日志中出现大体积向量
        def _summarize_args(d: Dict[str, Any]) -> Dict[str, Any]:
            if not isinstance(d, dict):
                return {}
            out: Dict[str, Any] = {}
            for k, v in d.items():
                if k in {"embedding", "query_embedding"}:
                    try:
                        dim = len(v) if isinstance(v, (list, tuple)) else None
                        out[k] = f"[vector {dim} dims]"
                    except Exception:
                        out[k] = "[vector]"
                elif k in {"content", "query"} and isinstance(v, str):
                    out[f"{k}_len"] = len(v)
                    out[f"{k}_preview"] = v[:80]
                else:
                    out[k] = v
            return out

        log_args = _summarize_args(kwargs)
        start_ts = time.perf_counter()
        logger.info(
            "mcp.tool.call.start",
            trace_id=trace_id,
            tool=tool_name,
            args=log_args,
        )

        http_status = None
        result_json: Any = None
        # 如果有真实的MCP客户端
        if self.mcp_client:
            try:
                # 使用httpx进行HTTP调用（复用客户端），按工具时间预算设置超时
                if self._http_client is None:
                    self._http_client = httpx.AsyncClient()
                time_budget = await self._get_tool_time_budget(tool_name)
                timeout = min(max(time_budget * 1.5, 1.0), 15.0)
                response = await self._http_client.post(
                    f"{self.mcp_url}/tool/{tool_name}",
                    json=kwargs,
                    timeout=timeout,
                )
                http_status = response.status_code
                response.raise_for_status() # 检查HTTP状态码
                result_json = response.json()
            except httpx.RequestError as e:
                logger.error(f"HTTP request to MCP tool failed: {e}")
                # 严格模式下不模拟
            except httpx.HTTPStatusError as e:
                logger.error(f"MCP tool HTTP error: {e}")

        # 智能回退处理：基于工具元数据和输出schema
        if result_json is None:
            error_message = f"MCP tool '{tool_name}' unavailable"
            logger.error(
                "mcp.tool.call.failure",
                trace_id=trace_id,
                tool=tool_name,
                http_status=http_status,
                args=log_args,
            )
            raise RuntimeError(error_message)

        # 结束日志与调用记录
        try:
            duration_ms = int((time.perf_counter() - start_ts) * 1000)
            if isinstance(result_json, list):
                result_count = len(result_json)
            elif isinstance(result_json, dict):
                result_count = 1
            else:
                result_count = 0
            logger.info(
                "mcp.tool.call.end",
                trace_id=trace_id,
                tool=tool_name,
                http_status=http_status,
                duration_ms=duration_ms,
                result_count=result_count,
            )
            # 将调用记录入内存，便于持久化
            if trace_id:
                rec = {
                    'tool': tool_name,
                    'args': log_args,
                    'http_status': http_status,
                    'duration_ms': duration_ms,
                    'result_count': result_count,
                    'ts': datetime.now().isoformat(),
                }
                self._tool_calls_by_trace.setdefault(trace_id, []).append(rec)
        except Exception:
            pass

        return result_json
    
    async def check_and_send_reminders(self, send_callback) -> List[Dict[str, Any]]:
        """
        检查并发送到期的提醒 - 改进版
        """
        sent_reminders = []
        
        try:
            # 从数据库获取所有活跃用户
            from .db.database import get_session
            async with get_session() as db:
                # 获取所有有 Threema 渠道的用户
                from sqlalchemy import text
                result = await db.execute(text(
                    """
                    SELECT DISTINCT u.id as user_id
                    FROM users u
                    JOIN user_channels uc ON u.id = uc.user_id
                    WHERE uc.channel = 'threema'
                    """
                ))
                user_rows = result.fetchall()
                
                for row in user_rows:
                    # 兼容 Row/Mapping 访问
                    user_id = str(row[0] if isinstance(row, (tuple, list)) else row['user_id'])
                    
                    # 获取该用户的待发送提醒
                    reminders = await self._call_mcp_tool(
                        'get_pending_reminders',
                        user_id=user_id
                    )
                    
                    for reminder in reminders:
                        # 构建提醒消息
                        reminder_content = reminder.get('content', '您设置的提醒')
                        ai_understanding = reminder.get('ai_understanding', {})
                        remind_detail = ai_understanding.get('remind_content', reminder_content)
                        
                        reminder_text = f"⏰ 提醒：{remind_detail}\n"
                        if ai_understanding.get('repeat') == 'daily':
                            reminder_text += "（每日提醒）"
                        
                        # 发送提醒
                        success = await send_callback(user_id, reminder_text)
                        
                        if success:
                            # 标记为已发送
                            await self._call_mcp_tool(
                                'mark_reminder_sent',
                                reminder_id=reminder['reminder_id']
                            )
                            
                            sent_reminders.append({
                                'user_id': user_id,
                                'reminder': reminder,
                                'sent': True
                            })
                            
                            logger.info(f"Sent reminder to user {user_id}: {remind_detail}")
                        else:
                            logger.error(f"Failed to send reminder {reminder['reminder_id']} to {user_id}")
                            
        except Exception as e:
            logger.error(f"Error in reminder task: {e}")
        
        return sent_reminders 
