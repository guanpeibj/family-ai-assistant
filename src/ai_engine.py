"""
AI引擎V2 - 智能增强版

设计理念：
1. AI 完全主导业务逻辑，工程层只提供基础设施
2. 通过统一的契约结构让 AI 自主处理所有对话复杂度
3. 数据结构开放，AI 可以自由决定存储内容
4. 工具调用完全通用化，不含业务逻辑

增强特性（V2）：
1. 智能Context管理 - 主动获取多维度相关信息
2. 思考循环支持 - 最多3轮深度分析，逐步深化理解
3. 工具反馈优化 - 执行后验证结果，必要时自动补充

核心流程（增强版）：
用户输入 → 
[思考循环] 统一AI理解（含智能上下文） → 
[验证循环] 工具计划 → 执行 → 验证 → 
回复生成

参考文档： docs/V2_INTELLIGENCE_UPGRADE.md
"""
import json
import re  # 用于占位符解析
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
import uuid
import time
import asyncio  # 用于异步计时和事件循环
from pydantic import BaseModel, Field, ValidationError
import structlog
import httpx
import os

from .core.config import settings
from .core.prompt_manager import prompt_manager
from .core.llm_client import LLMClient
from .core.exceptions import (
    AIEngineError, AnalysisError, ContextResolutionError, ToolPlanningError,
    MCPToolError, ToolTimeoutError, ToolExecutionError, LLMError,
    create_error_context, get_user_friendly_message
)
from .core.tool_helper import ToolCapabilityAnalyzer, ToolArgumentProcessor, ToolExecutionMonitor
from .core.ab_testing import get_experiment_version, ab_testing_manager, ExperimentResult
from .services.media_service import make_signed_url
from .services.household_service import household_service

logger = structlog.get_logger(__name__)

# 统一的分析契约模型
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
    """工具执行计划模型（增强版）"""
    requires_context: List[str] = Field(default_factory=list)  # 需要的上下文依赖
    steps: List[ToolStepModel] = Field(default_factory=list)  # 执行步骤列表
    # 工具结果验证相关
    verification: Optional[Dict[str, Any]] = None  # 验证配置

class UnderstandingModel(BaseModel):
    """AI 理解结果模型 - 核心契约结构（增强版）"""
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
    original_content: Optional[str] = None  # 原始用户消息（用于日志和调试）
    # 思考循环相关字段
    thinking_depth: int = 0  # 思考深度（0-3）
    needs_deeper_analysis: bool = False  # 是否需要更深入分析
    analysis_reasoning: Optional[str] = None  # 分析推理过程
    next_exploration_areas: List[str] = Field(default_factory=list)  # 下一步探索方向
    metadata: Dict[str, Any] = Field(default_factory=dict)  # 其他元数据

class AnalysisModel(BaseModel):
    """AI 分析结果完整模型 - 统一契约"""
    understanding: UnderstandingModel  # 理解结果
    context_requests: List[ContextRequestModel] = Field(default_factory=list)  # 需要的上下文
    tool_plan: ToolPlanModel = Field(default_factory=ToolPlanModel)  # 工具执行计划
    response_directives: Dict[str, Any] = Field(default_factory=dict)  # 响应指令（如风格）


class MessageProcessor:
    """消息处理器 - 负责消息预处理和内容合并"""
    
    @staticmethod
    def merge_attachment_texts(content: str, attachments: Optional[List[Dict[str, Any]]]) -> str:
        """合并附件衍生文本到消息内容"""
        if not attachments:
            return content
        
        derived_texts: List[str] = []
        for att in attachments:
            if not isinstance(att, dict):
                continue
            
            # 优先级：转写 > OCR > 视觉摘要
            text = None
            if isinstance(att.get('transcription'), dict):
                text = att['transcription'].get('text')
            if not text:
                text = att.get('ocr_text')
            if not text:
                text = att.get('vision_summary')
            
            if text:
                derived_texts.append(str(text))
        
        if derived_texts:
            base = (content or '').strip()
            extra = "\n\n[附件提取]\n" + "\n".join(derived_texts)
            return f"{base}{extra}" if base else "\n".join(derived_texts)
        
        return content


class ContextManager:
    """上下文管理器 - 负责获取和解析各种上下文数据"""
    
    def __init__(self, ai_engine):
        self.ai_engine = ai_engine
    
    async def get_basic_context(
        self, 
        user_id: str, 
        thread_id: Optional[str], 
        shared_thread: bool,
        channel: Optional[str]
    ) -> Dict[str, Any]:
        """获取基础上下文数据"""
        start_time = asyncio.get_event_loop().time()
        try:
            # 1. 最近对话记录
            logger.debug(
                "context.basic.fetching_memories",
                user_id=user_id,
                thread_id=thread_id,
                shared_thread=shared_thread
            )
            
            memory_start = asyncio.get_event_loop().time()
            light_context = await self._get_recent_memories(
                user_id=user_id,
                limit=4,
                thread_id=thread_id,
                shared_thread=shared_thread,
                channel=channel,
            )
            
            logger.info(
                "context.memories.fetched",
                count=len(light_context),
                duration_ms=int((asyncio.get_event_loop().time() - memory_start) * 1000),
                memory_preview=[{
                    'content': m.get('content', '')[:50],
                    'time': m.get('time')
                } for m in light_context[:2]]  # 只显示前2条
            )
            
            # 2. 家庭结构上下文
            household_start = asyncio.get_event_loop().time()
            household_context = await household_service.get_context()
            
            logger.info(
                "context.household.fetched",
                duration_ms=int((asyncio.get_event_loop().time() - household_start) * 1000),
                members=len(household_context.get('members', [])),
                names=[m.get('display_name') for m in household_context.get('members', [])]
            )
            
            logger.info(
                "context.basic.complete",
                total_duration_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
                memories_count=len(light_context),
                household_members=len(household_context.get('members', []))
            )
            
            return {
                'light_context': light_context,
                'household': household_context
            }
        except Exception as e:
            logger.warning(
                "basic_context.failed",
                error=str(e),
                duration_ms=int((asyncio.get_event_loop().time() - start_time) * 1000)
            )
            return {'light_context': [], 'household': {}}
    
    async def resolve_context_requests(
        self,
        context_requests: List[Dict[str, Any]],
        understanding: Dict[str, Any],
        user_id: str,
        thread_id: Optional[str],
        shared_thread: bool,
        channel: Optional[str],
        trace_id: str
    ) -> Dict[str, Any]:
        """解析 AI 请求的额外上下文"""
        if not context_requests:
            return {}
        
        start_time = asyncio.get_event_loop().time()
        resolved: Dict[str, Any] = {}
        
        logger.info(
            "context.requests.resolving",
            trace_id=trace_id,
            count=len(context_requests),
            types=[req.get('kind') for req in context_requests if isinstance(req, dict)],
            names=[req.get('name') for req in context_requests if isinstance(req, dict)]
        )
        
        for req in context_requests:
            if not isinstance(req, dict):
                continue
                
            name = req.get('name')
            kind = req.get('kind')
            if not name or not kind:
                continue
            
            req_start = asyncio.get_event_loop().time()
            try:
                if kind == 'recent_memories':
                    limit = int(req.get('limit', 6))
                    resolved[name] = await self._get_recent_memories(
                        user_id=user_id,
                        limit=limit,
                        thread_id=thread_id,
                        shared_thread=shared_thread,
                        channel=channel,
                    )
                
                elif kind == 'semantic_search':
                    query = req.get('query') or understanding.get('original_content', '')
                    limit = int(req.get('limit', 5))
                    
                    logger.debug(
                        "context.semantic_search.starting",
                        trace_id=trace_id,
                        name=name,
                        query_preview=query[:50] + '...' if len(query) > 50 else query,
                        limit=limit
                    )
                    
                    search_start = asyncio.get_event_loop().time()
                    results = await self._semantic_search(
                        user_id=user_id,
                        query=query,
                        top_k=limit,
                        thread_id=thread_id,
                        shared_thread=shared_thread,
                        channel=channel,
                    )
                    resolved[name] = results
                    
                    logger.info(
                        "context.semantic_search.complete",
                        trace_id=trace_id,
                        name=name,
                        duration_ms=int((asyncio.get_event_loop().time() - search_start) * 1000),
                        results_count=len(results),
                        top_result=results[0].get('content', '')[:50] if results else None
                    )
                
                elif kind == 'direct_search':
                    filters = req.get('filters', {})
                    limit = req.get('limit', 20)
                    # 确保 limit 是有效的整数，防止 int(None) 错误
                    if limit is None or limit == '':
                        limit = 20
                    try:
                        limit = int(limit)
                    except (ValueError, TypeError):
                        limit = 20
                    filters['limit'] = limit
                    
                    scope = req.get('scope', 'family')  # context_request可以指定scope
                    
                    # 获取家庭上下文（用于person解析和全家查询）
                    from src.services.household_service import household_service
                    household_context = await household_service.get_context()
                    family_user_ids = household_context.get('family_scope', {}).get('user_ids', [])
                    
                    # 根据scope决定user_id和是否添加thread_id
                    context_user_id = user_id
                    if scope == 'family':
                        # 家庭范围：使用所有家庭user_ids，不限制thread_id
                        if family_user_ids:
                            context_user_id = family_user_ids
                        # 不添加thread_id过滤
                    elif scope == 'thread':
                        # 线程范围：当前用户 + thread_id
                        context_user_id = user_id
                        if thread_id and 'thread_id' not in filters:
                            filters['thread_id'] = thread_id
                    elif scope == 'personal':
                        # 个人范围：解析person字段
                        person_key = req.get('person_key')
                        person = req.get('person')
                        person_identifier = person_key if person_key else person
                        
                        if person_identifier:
                            resolved_id = self.ai_engine.tool_executor._resolve_person_to_user_id(
                                person_identifier, user_id, household_context
                            )
                            if resolved_id:
                                context_user_id = resolved_id
                        # 不添加thread_id
                    
                    if shared_thread:
                        filters['shared_thread'] = True
                    
                    logger.debug(
                        "context.direct_search.starting",
                        trace_id=trace_id,
                        name=name,
                        scope=scope,
                        user_id_type='list' if isinstance(context_user_id, list) else 'single',
                        filters=list(filters.keys())
                    )
                    
                    search_start = asyncio.get_event_loop().time()
                    results = await self.ai_engine._call_mcp_tool(
                        'search',
                        query=req.get('query', ''),
                        filters=filters,
                        user_id=context_user_id,
                        trace_id=trace_id,
                    )
                    resolved[name] = results
                    
                    logger.info(
                        "context.direct_search.complete",
                        trace_id=trace_id,
                        name=name,
                        duration_ms=int((asyncio.get_event_loop().time() - search_start) * 1000),
                        filters=filters,
                        results_count=len(results) if isinstance(results, list) else 0
                    )
                
                else:
                    logger.info("context_request.unsupported", kind=kind, name=name)
                    
            except Exception as exc:
                logger.warning(
                    "context_request.failed",
                    trace_id=trace_id,
                    name=name,
                    kind=kind,
                    error=str(exc),
                    duration_ms=int((asyncio.get_event_loop().time() - req_start) * 1000)
                )
                resolved[name] = []
        
        total_duration = int((asyncio.get_event_loop().time() - start_time) * 1000)
        logger.info(
            "context.requests.resolved",
            trace_id=trace_id,
            total_duration_ms=total_duration,
            resolved_names=list(resolved.keys()),
            resolved_counts={k: len(v) if isinstance(v, list) else 1 for k, v in resolved.items()}
        )
        
        return resolved
    
    async def _get_recent_memories(
        self, 
        user_id: str, 
        limit: int,
        thread_id: Optional[str],
        shared_thread: bool,
        channel: Optional[str]
    ) -> List[Dict[str, Any]]:
        """获取最近的交互记录"""
        try:
            filters = {'limit': limit}
            if thread_id:
                filters['thread_id'] = thread_id
                filters['type'] = 'chat_turn'
                if shared_thread:
                    filters['shared_thread'] = True
                if channel:
                    filters['channel'] = channel
            
            recent_memories = await self.ai_engine._call_mcp_tool(
                'search',
                query='',
                user_id=user_id,
                filters=filters
            )
            
            # 格式化记忆
            formatted_memories = []
            for memory in recent_memories:
                if isinstance(memory, dict) and not memory.get('_meta'):
                    aiu = memory.get('ai_understanding', {})
                    # 处理时间字段：优先使用occurred_at，备选created_at
                    time_value = memory.get('occurred_at') or memory.get('created_at')
                    formatted_memories.append({
                        'content': memory.get('content', ''),
                        'ai_understanding': aiu if isinstance(aiu, dict) else {},
                        'time': time_value  # 现在会是时间戳或None（如果两个字段都为空）
                    })
            
            return formatted_memories
            
        except Exception as e:
            logger.error("get_recent_memories.failed", error=str(e))
            return []
    
    async def _semantic_search(
        self, 
        user_id: str, 
        query: str, 
        top_k: int,
        thread_id: Optional[str],
        shared_thread: bool,
        channel: Optional[str]
    ) -> List[Dict[str, Any]]:
        """语义搜索"""
        if not query:
            return []
        
        try:
            filters = {'limit': top_k}
            if thread_id:
                filters['thread_id'] = thread_id
            if shared_thread:
                filters['shared_thread'] = True
            if channel:
                filters['channel'] = channel
            
            # 生成查询向量
            query_embedding = None
            try:
                embs = await self.ai_engine.llm.embed([query])
                query_embedding = embs[0] if embs else None
            except Exception:
                pass
            
            results = await self.ai_engine._call_mcp_tool(
                'search',
                query=query,
                user_id=user_id,
                filters=filters,
                query_embedding=query_embedding
            )
            
            # 格式化结果
            formatted = []
            for r in results:
                if isinstance(r, dict):
                    formatted.append({
                        'content': r.get('content', ''),
                        'ai_understanding': r.get('ai_understanding', {}),
                        'time': r.get('occurred_at', '')
                    })
            
            return formatted
            
        except Exception as e:
            logger.error("semantic_search.failed", error=str(e))
            return []


class ToolExecutor:
    """工具执行器 - 负责 MCP 工具调用和结果处理"""
    
    def __init__(self, ai_engine):
        self.ai_engine = ai_engine
        self.capability_analyzer = ToolCapabilityAnalyzer()
        self.argument_processor = ToolArgumentProcessor()
        self.execution_monitor = ToolExecutionMonitor()
    
    def _resolve_person_to_user_id(
        self,
        person_or_key: str,
        current_user_id: str,
        household_context: Dict[str, Any]
    ) -> Optional[str]:
        """将AI识别的person解析为user_id（极简版本，无硬编码）
        
        设计理念：
        - AI负责将"儿子"/"妻子"等人称代词解析为具体名字或member_key
        - 引擎只负责简单查找，不做任何映射逻辑
        - 完全数据驱动，新增成员无需改代码
        
        Args:
            person_or_key: AI输出的person字段（应该是具体名字或member_key）
            current_user_id: 当前用户ID
            household_context: 家庭上下文
        
        Returns:
            解析后的user_id，如果无法解析返回None
        """
        if not person_or_key:
            return None
        
        person_stripped = person_or_key.strip()
        
        # 特殊情况："我" → 当前用户（这是唯一的硬编码，因为无法从household推断）
        if person_stripped in ['我', '我的']:
            return current_user_id
        
        # 从household context中查找（数据驱动）
        members = household_context.get('members', [])
        members_index = household_context.get('members_index', {})
        
        # 1. 优先匹配member_key（最准确）
        if person_stripped in members_index:
            user_ids = members_index[person_stripped].get('user_ids', [])
            return user_ids[0] if user_ids else None
        
        # 2. 匹配display_name（大小写不敏感）
        person_lower = person_stripped.lower()
        for member in members:
            display_name = member.get('display_name', '')
            if display_name.lower() == person_lower:
                user_ids = member.get('user_ids', [])
                return user_ids[0] if user_ids else None
        
        # 3. 无法解析：返回None（AI应该输出更明确的标识）
        logger.warning(
            "person_resolution.failed",
            person=person_or_key,
            available_members=[m.get('display_name') for m in members]
        )
        return None
    
    async def execute_tool_plan(
        self,
        steps: List[Dict[str, Any]],
        understanding: Dict[str, Any],
        user_id: str,
        context: Optional[Dict[str, Any]],
        trace_id: str,
        context_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行工具计划"""
        if not steps:
            return {"actions_taken": []}
        
        try:
            # 获取可用工具列表
            available_tools = await self._get_available_tools()
            
            executed = {"actions_taken": []}
            last_store_id = None
            last_aggregate_result = None
            
            for step in steps:
                if not isinstance(step, dict):
                    continue
                
                tool_name = step.get('tool')
                if not tool_name or tool_name not in available_tools:
                    logger.warning("tool.not_available", tool=tool_name)
                    continue
                
                # 处理工具参数
                raw_args = step.get('args', {})
                processed_args = await self._prepare_tool_arguments(
                    tool_name=tool_name,
                    raw_args=raw_args,
                    understanding=understanding,
                    user_id=user_id,
                    context=context,
                    context_data=context_data,
                    trace_id=trace_id,
                    last_store_id=last_store_id,
                    last_aggregate_result=last_aggregate_result
                )
                
                # 执行工具
                start_time = time.perf_counter()
                try:
                    result = await self.ai_engine._call_mcp_tool(
                        tool_name, 
                        trace_id=trace_id, 
                        **processed_args
                    )
                    
                    duration_ms = int((time.perf_counter() - start_time) * 1000)
                    self.execution_monitor.record_call(tool_name, duration_ms, True)
                    
                    executed['actions_taken'].append({
                        'action': tool_name,
                        'result': result
                    })
                    
                    # 更新上下文数据
                    context_data[f"result_{tool_name}"] = result
                    
                    # 处理特殊返回值
                    last_store_id, last_aggregate_result = self._update_execution_state(
                        tool_name, result, last_store_id, last_aggregate_result
                    )
                    
                except Exception as e:
                    duration_ms = int((time.perf_counter() - start_time) * 1000)
                    self.execution_monitor.record_call(tool_name, duration_ms, False)
                    
                    logger.error(
                        "tool.execution.failed",
                        tool=tool_name,
                        trace_id=trace_id,
                        error=str(e)
                    )
                    
                    executed['actions_taken'].append({
                        'action': tool_name,
                        'result': {'success': False, 'error': str(e)}
                    })
            
            return executed
            
        except Exception as e:
            raise ToolExecutionError(
                f"工具执行失败: {str(e)}",
                trace_id=trace_id,
                context={"steps_count": len(steps)},
                cause=e
            )
    
    async def _get_available_tools(self) -> set:
        """获取可用工具集合"""
        try:
            tool_names = await self.capability_analyzer.get_tool_names(
                self.ai_engine._http_client,
                self.ai_engine.mcp_url
            )
            return set(tool_names)
        except Exception:
            # 回退工具列表
            return {
                "store", "search", "aggregate", "schedule_reminder",
                "get_pending_reminders", "mark_reminder_sent",
                "update_memory_fields", "render_chart", "batch_store",
                "batch_search", "soft_delete", "reembed_memories"
            }
    
    async def _prepare_tool_arguments(
        self,
        tool_name: str,
        raw_args: Dict[str, Any],
        understanding: Dict[str, Any],
        user_id: str,
        context: Optional[Dict[str, Any]],
        context_data: Dict[str, Any],
        trace_id: str,
        last_store_id: Optional[str],
        last_aggregate_result: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """准备工具调用参数"""
        # 解析上下文引用
        args = self.argument_processor.resolve_args_with_context(
            raw_args,
            context_data=context_data,
            last_store_id=last_store_id,
            last_aggregate_result=last_aggregate_result
        )
        
        # 方案B4：基于AI识别的scope智能处理user_id和thread_id
        # 核心理念：默认全家范围，AI明确指定时才按人或线程过滤
        if tool_name in ['search', 'aggregate'] and 'user_id' not in args:
            # 获取家庭上下文
            household_scope = context_data.get('household', {}).get('family_scope', {})
            all_family_user_ids = household_scope.get('user_ids', [])
            household_context = context_data.get('household', {})
            
            # 从AI的understanding中获取scope和person
            scope = understanding.get('entities', {}).get('scope', 'family')
            person = understanding.get('entities', {}).get('person')
            
            if scope == 'family':
                # 家庭范围（默认）：所有家庭成员，不限thread_id
                if all_family_user_ids:
                    args['user_id'] = all_family_user_ids
                else:
                    args['user_id'] = user_id
                # 不添加thread_id过滤（家庭数据跨线程共享）
                
                logger.debug(
                    "tool_args.scope_family",
                    trace_id=trace_id,
                    tool=tool_name,
                    family_count=len(all_family_user_ids) if isinstance(all_family_user_ids, list) else 1
                )
                
            elif scope == 'thread':
                # 线程范围：当前用户 + 限制thread_id
                args['user_id'] = user_id
                # 自动添加thread_id（如果工具参数中没有明确指定）
                if 'filters' in args and thread_id and 'thread_id' not in args.get('filters', {}):
                    if 'filters' not in args:
                        args['filters'] = {}
                    args['filters']['thread_id'] = thread_id
                
                logger.debug(
                    "tool_args.scope_thread",
                    trace_id=trace_id,
                    tool=tool_name,
                    user_id=user_id,
                    thread_id=thread_id
                )
                
            elif scope == 'personal':
                # 个人范围：解析person为具体user_id
                # 优先使用person_key（member_key），其次使用person（display_name）
                person_key = understanding.get('entities', {}).get('person_key')
                person_identifier = person_key if person_key else person
                
                resolved_user_id = None
                if person_identifier:
                    resolved_user_id = self._resolve_person_to_user_id(
                        person_identifier, user_id, household_context
                    )
                
                if resolved_user_id:
                    args['user_id'] = resolved_user_id
                else:
                    # 解析失败，回退到当前用户
                    args['user_id'] = user_id
                    logger.warning(
                        "tool_args.person_resolution_failed",
                        trace_id=trace_id,
                        person_key=person_key,
                        person=person,
                        fallback_to_current_user=True
                    )
                
                logger.debug(
                    "tool_args.scope_personal",
                    trace_id=trace_id,
                    tool=tool_name,
                    person_key=person_key,
                    person=person,
                    resolved_user_id=args['user_id']
                )
            
            else:
                # 未识别的scope，回退到family
                args['user_id'] = all_family_user_ids if all_family_user_ids else user_id
                logger.warning(
                    "tool_args.unknown_scope",
                    trace_id=trace_id,
                    scope=scope,
                    fallback='family'
                )
        
        # 自动添加 user_id（如果工具需要）
        if await self.capability_analyzer.requires_user_id(
            tool_name, self.ai_engine._http_client, self.ai_engine.mcp_url
        ) and 'user_id' not in args:
            args['user_id'] = await self._resolve_user_id(user_id, context)
        
        # 自动添加向量嵌入（如果工具支持）
        if await self.capability_analyzer.supports_embedding(
            tool_name, self.ai_engine._http_client, self.ai_engine.mcp_url
        ):
            if 'content' in args and 'embedding' not in args:
                text_for_embed = args.get('content') or understanding.get('original_content', '')
                if text_for_embed:
                    args['embedding'] = await self.ai_engine._get_embedding_cached(text_for_embed, trace_id)
            
            if 'query' in args and 'query_embedding' not in args:
                query_text = args.get('query')
                if query_text:
                    args['query_embedding'] = await self.ai_engine._get_embedding_cached(query_text, trace_id)
        
        # 仅为存储类工具合并实体信息到 ai_data（保持AI自主决策）
        output_type = await self.capability_analyzer.get_output_type(
            tool_name, self.ai_engine._http_client, self.ai_engine.mcp_url
        )
        if output_type == 'entity_with_id':
            # 确保存储工具总是有必需的参数
            if 'content' not in args:
                # 使用原始内容作为 fallback
                args['content'] = understanding.get('original_content', '')
            
            # 确保存储工具总是有 ai_data 参数
            ai_data = args.get('ai_data', {})
            entities = understanding.get('entities', {})
            merged = {**entities, **ai_data}
            merged.setdefault('occurred_at', understanding.get('occurred_at') or datetime.now().isoformat())
            if context and context.get('thread_id'):
                merged.setdefault('thread_id', context.get('thread_id'))
            merged.setdefault('trace_id', trace_id)
            args['ai_data'] = merged
        
        return args
    
    async def _resolve_user_id(self, user_id: str, context: Optional[Dict[str, Any]]) -> str:
        """解析用户ID（简化版本）"""
        # 这里可以实现用户ID的映射逻辑
        # 当前简化为直接返回
        return user_id
    
    def _update_execution_state(
        self,
        tool_name: str,
        result: Any,
        last_store_id: Optional[str],
        last_aggregate_result: Optional[Dict[str, Any]]
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """更新执行状态（用于后续工具引用）"""
        new_store_id = last_store_id
        new_aggregate_result = last_aggregate_result
        
        if isinstance(result, dict):
            if result.get('success') and result.get('id'):
                new_store_id = result['id']
            
            if tool_name == 'aggregate' or 'result' in result or 'groups' in result:
                new_aggregate_result = result
        
        return new_store_id, new_aggregate_result
    
    async def is_simple_operation(self, steps: List[Dict[str, Any]]) -> bool:
        """判断是否为简单操作"""
        return await self.capability_analyzer.is_simple_operation(
            steps, self.ai_engine._http_client, self.ai_engine.mcp_url
        )


class AIEngineV2:
    """AI 引擎核心类 V2 - 重构版本
    
    设计原则：
    - 让 AI 决定一切业务逻辑
    - 工程层只提供基础能力（LLM调用、工具执行、数据存储）
    - 通过 Prompt 和数据驱动系统演进
    """
    
    def __init__(self):
        # 核心组件
        self.llm = LLMClient()
        self.mcp_client = None
        self.mcp_url = os.getenv('MCP_SERVER_URL', 'http://faa-mcp:8000')
        
        # HTTP 客户端（复用连接）
        self._http_client: Optional[httpx.AsyncClient] = None
        
        # 辅助组件
        self.message_processor = MessageProcessor()
        self.context_manager = ContextManager(self)
        self.tool_executor = ToolExecutor(self)
        
        # 向量嵌入缓存（两级缓存优化性能）
        self._emb_cache_by_trace: Dict[str, Dict[str, List[float]]] = {}
        self._emb_cache_global: Dict[str, Tuple[List[float], float]] = {}
        self._emb_cache_global_max_items = 1000
        self._emb_cache_global_ttl = 3600.0
        
        # 工具调用记录（按 trace_id 聚合）
        self._tool_calls_by_trace: Dict[str, List[Dict[str, Any]]] = {}
    
    # =================== 主入口方法 ===================
    
    async def process_message(self, content: str, user_id: str, context: Dict[str, Any] = None) -> str:
        """处理用户消息的主入口 - AI驱动的统一流程
        
        核心理念：让AI决定一切，工程只提供执行框架
        流程：理解 → 规划 → 执行 → 响应
        
        Args:
            content: 用户输入的消息内容
            user_id: 用户标识
            context: 上下文信息（渠道、线程、附件等）
            
        Returns:
            AI 生成的回复文本
        """
        trace_id = str(uuid.uuid4())
        start_time = asyncio.get_event_loop().time()
        
        try:
            # 初始化追踪
            self._init_trace(trace_id, user_id, context)
            
            # 步骤1：消息预处理（合并附件文本）
            step1_start = asyncio.get_event_loop().time()
            processed_content = await self._preprocess_message(content, context)
            logger.info(
                "step1.preprocess.completed",
                trace_id=trace_id,
                original_length=len(content or ''),
                processed_length=len(processed_content),
                has_attachments=bool(context and context.get('attachments')),
                duration_ms=int((asyncio.get_event_loop().time() - step1_start) * 1000)
            )
            
            # 步骤2：获取实验版本（A/B 测试）
            prompt_version = self._get_experiment_version(user_id, context)
            logger.debug("step2.experiment.version", trace_id=trace_id, version=prompt_version)
            
            # 步骤3：AI 理解分析（核心）
            step3_start = asyncio.get_event_loop().time()
            analysis = await self._analyze_message(processed_content, user_id, context, trace_id, prompt_version)
            logger.info(
                "step3.analysis.completed",
                trace_id=trace_id,
                intent=analysis.understanding.intent,
                need_clarification=analysis.understanding.need_clarification,
                need_action=analysis.understanding.need_action,
                context_requests_count=len(analysis.context_requests),
                tool_steps_count=len(analysis.tool_plan.steps),
                duration_ms=int((asyncio.get_event_loop().time() - step3_start) * 1000)
            )
            
            # 步骤4：处理澄清分支
            if analysis.understanding.need_clarification:
                clarification_response = await self._handle_clarification(analysis, context, prompt_version)
                logger.info(
                    "step4.clarification.returned",
                    trace_id=trace_id,
                    response_length=len(clarification_response),
                    total_duration_ms=int((asyncio.get_event_loop().time() - start_time) * 1000)
                )
                return clarification_response
            
            # 步骤5：执行工具并生成响应
            step5_start = asyncio.get_event_loop().time()
            response = await self._execute_and_respond(analysis, processed_content, user_id, context, trace_id, prompt_version)
            logger.info(
                "step5.execution.completed",
                trace_id=trace_id,
                response_length=len(response),
                duration_ms=int((asyncio.get_event_loop().time() - step5_start) * 1000),
                total_duration_ms=int((asyncio.get_event_loop().time() - start_time) * 1000)
            )
            
            # 步骤6：记录实验结果（如果在实验中）
            self._record_experiment_result(user_id, context, trace_id, analysis, response)
            
            return response
            
        except Exception as e:
            error_response = await self._handle_error(e, trace_id, user_id)
            logger.error(
                "process.failed",
                trace_id=trace_id,
                total_duration_ms=int((asyncio.get_event_loop().time() - start_time) * 1000)
            )
            return error_response
        finally:
            self._cleanup_trace(trace_id)
    
    # =================== 核心步骤方法 ===================
    
    def _init_trace(self, trace_id: str, user_id: str, context: Optional[Dict[str, Any]]):
        """初始化请求追踪 - 记录消息接收的起点"""
        thread_id = (context or {}).get('thread_id')
        channel = (context or {}).get('channel')
        
        # 提取消息预览（前50字符）用于日志
        content_preview = (context or {}).get('content', '')[:50]
        if len((context or {}).get('content', '')) > 50:
            content_preview += '...'
        
        logger.info(
            "message.received",
            trace_id=trace_id,
            user_id=user_id,
            thread_id=thread_id,
            channel=channel,
            content_preview=content_preview,
            has_attachments=bool(context and context.get('attachments'))
        )
        
        self._tool_calls_by_trace[trace_id] = []
        self._emb_cache_by_trace[trace_id] = {}
    
    async def _preprocess_message(self, content: str, context: Optional[Dict[str, Any]]) -> str:
        """消息预处理：合并附件衍生文本"""
        attachments = (context or {}).get('attachments') if context else None
        return self.message_processor.merge_attachment_texts(content, attachments)
    
    def _get_experiment_version(self, user_id: str, context: Optional[Dict[str, Any]]) -> str:
        """获取用户的实验版本（A/B 测试）"""
        channel = (context or {}).get('channel') if context else None
        return get_experiment_version(
            user_id=user_id,
            channel=channel,
            default_version="v4_default"
        )
    
    async def _analyze_message(
        self,
        content: str,
        user_id: str,
        context: Optional[Dict[str, Any]],
        trace_id: str,
        prompt_version: str
    ) -> AnalysisModel:
        """AI 理解分析：支持多轮思考循环的统一分析入口
        
        增强功能：
        - 支持思考深度（thinking_depth）判断
        - 支持基于初步结果的深度分析循环
        - 最多进行3轮思考，逐步深化理解
        """
        try:
            thread_id = (context or {}).get('thread_id') if context else None
            channel = (context or {}).get('channel') if context else None
            shared_thread = bool((context or {}).get('shared_thread'))
            
            # 初始化累积的上下文数据
            accumulated_context = {}
            analysis = None
            thinking_rounds = 0
            max_thinking_rounds = 3
            
            # 思考循环：最多3轮
            while thinking_rounds < max_thinking_rounds:
                thinking_rounds += 1
                
                # 获取基础上下文（第一轮）或使用累积的上下文
                if thinking_rounds == 1:
                    logger.info(
                        "analysis.round.started",
                        trace_id=trace_id,
                        round=thinking_rounds,
                        action="fetching_basic_context"
                    )
                    base_context = await self.context_manager.get_basic_context(
                        user_id=user_id,
                        thread_id=thread_id,
                        shared_thread=shared_thread,
                        channel=channel
                    )
                    accumulated_context = base_context.copy()
                    
                    # 记录基础上下文的内容
                    logger.info(
                        "analysis.basic_context.details",
                        trace_id=trace_id,
                        round=thinking_rounds,
                        light_context_count=len(accumulated_context.get('light_context', [])),
                        light_context_preview=[{
                            'content': ctx.get('content', '')[:50] + '...' if len(ctx.get('content', '')) > 50 else ctx.get('content', ''),
                            'type': ctx.get('ai_understanding', {}).get('type') if isinstance(ctx.get('ai_understanding'), dict) else None,
                            'time': ctx.get('time')  # 显示时间方便调试
                        } for ctx in accumulated_context.get('light_context', [])[:3]],  # 只显示前3条
                        household_members=len(accumulated_context.get('household', {}).get('members', [])),
                        household_names=[m.get('display_name') for m in accumulated_context.get('household', {}).get('members', [])] if accumulated_context.get('household') else []
                    )
                
                # 构建分析请求（包含累积的上下文）
                analysis_payload = {
                    "message": content,
                    "user": {"id": user_id, "thread_id": thread_id, "channel": channel},
                    "context": {
                        "shared_thread": shared_thread,
                        "light_context": accumulated_context.get('light_context', []),
                        "household": accumulated_context.get('household', {}),
                        "accumulated_insights": accumulated_context.get('insights', {}),
                        "thinking_round": thinking_rounds,
                        "metadata": {
                            "utc_now": datetime.utcnow().isoformat(),
                            "low_budget": self._is_low_budget_mode(),
                        }
                    }
                }
                
                # 记录准备发送给LLM的内容
                logger.info(
                    "analysis.payload.summary",
                    trace_id=trace_id,
                    round=thinking_rounds,
                    message_preview=content[:100] + '...' if len(content) > 100 else content,
                    context_light_count=len(analysis_payload['context']['light_context']),
                    has_insights=bool(analysis_payload['context'].get('accumulated_insights')),
                    thinking_round=analysis_payload['context']['thinking_round']
                )
                
                # 调用 LLM 进行分析
                system_prompt = await prompt_manager.get_system_prompt_with_tools(prompt_version)
                understanding_prompt = prompt_manager.get_understanding_prompt(prompt_version)
                
                user_prompt = "\n\n".join([
                    understanding_prompt,
                    "输入：",
                    json.dumps(analysis_payload, ensure_ascii=False, default=str),
                    "请仅返回契约描述的 JSON，不要添加解释。"
                ])
                
                logger.debug(
                    "llm.request.details",
                    trace_id=trace_id,
                    round=thinking_rounds,
                    system_prompt_length=len(system_prompt),
                    user_prompt_length=len(user_prompt),
                    temperature=0.2,
                    max_tokens=1500
                )
                
                llm_start_time = asyncio.get_event_loop().time()
                raw_response = await self.llm.chat_json(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.2,
                    max_tokens=1500,  # 增加token限制以支持更深入的分析
                )
                llm_duration_ms = int((asyncio.get_event_loop().time() - llm_start_time) * 1000)
                
                # 记录LLM响应的详细内容
                logger.info(
                    "llm.response.summary",
                    trace_id=trace_id,
                    round=thinking_rounds,
                    duration_ms=llm_duration_ms,
                    response_keys=list(raw_response.keys()) if isinstance(raw_response, dict) else [],
                    has_understanding='understanding' in raw_response,
                    has_tool_plan='tool_plan' in raw_response,
                    has_context_requests='context_requests' in raw_response
                )
                
                # 记录理解内容的详细信息
                if 'understanding' in raw_response:
                    understanding = raw_response['understanding']
                    logger.info(
                        "llm.understanding.details",
                        trace_id=trace_id,
                        round=thinking_rounds,
                        intent=understanding.get('intent'),
                        need_action=understanding.get('need_action', False),
                        need_clarification=understanding.get('need_clarification', False),
                        entities=list(understanding.get('entities', {}).keys()),
                        entities_values={k: str(v)[:50] for k, v in understanding.get('entities', {}).items()},
                        clarification_questions=understanding.get('clarification_questions', []),
                        thinking_depth=understanding.get('thinking_depth', 0),
                        needs_deeper_analysis=understanding.get('needs_deeper_analysis', False)
                    )
                
                # 记录工具计划详情
                if 'tool_plan' in raw_response and raw_response['tool_plan'].get('steps'):
                    steps = raw_response['tool_plan']['steps']
                    logger.info(
                        "llm.tool_plan.details",
                        trace_id=trace_id,
                        round=thinking_rounds,
                        steps_count=len(steps),
                        tools=[s.get('tool') for s in steps],
                        first_step_preview={
                            'tool': steps[0].get('tool'),
                            'args': list(steps[0].get('args', {}).keys())
                        } if steps else None
                    )
                
                # 解析响应并保存原始内容
                try:
                    analysis = AnalysisModel(**raw_response)
                    # 保存原始内容用于日志和调试
                    analysis.understanding.original_content = content
                    
                    # 检查是否需要更深入的分析
                    needs_deeper = raw_response.get('understanding', {}).get('needs_deeper_analysis', False)
                    
                    if not needs_deeper or thinking_rounds >= max_thinking_rounds:
                        # 不需要继续或已达到最大轮数
                        logger.info(
                            "thinking_loop.completed", 
                            trace_id=trace_id,
                            rounds=thinking_rounds,
                            thinking_depth=raw_response.get('understanding', {}).get('thinking_depth', 0)
                        )
                        break
                    
                    # 需要更深入分析，先获取额外上下文
                    if analysis.context_requests:
                        logger.info(
                            "thinking_loop.fetching_context",
                            trace_id=trace_id,
                            round=thinking_rounds,
                            requests_count=len(analysis.context_requests),
                            request_types=[req.kind for req in analysis.context_requests],
                            exploration_areas=analysis.understanding.next_exploration_areas
                        )
                        
                        context_start = asyncio.get_event_loop().time()
                        resolved_context = await self.context_manager.resolve_context_requests(
                            context_requests=[req.model_dump() for req in analysis.context_requests],
                            understanding=analysis.understanding.model_dump(),
                            user_id=user_id,
                            thread_id=thread_id,
                            shared_thread=shared_thread,
                            channel=channel,
                            trace_id=trace_id
                        )
                        
                        # 记录解析的上下文内容
                        logger.info(
                            "thinking_loop.context_resolved",
                            trace_id=trace_id,
                            round=thinking_rounds,
                            duration_ms=int((asyncio.get_event_loop().time() - context_start) * 1000),
                            resolved_keys=list(resolved_context.keys()),
                            resolved_counts={k: len(v) if isinstance(v, list) else 1 for k, v in resolved_context.items()},
                            sample_content={
                                k: v[0] if isinstance(v, list) and v else str(v)[:100]
                                for k, v in list(resolved_context.items())[:3]  # 只显示前3个
                            }
                        )
                        
                        # 更新累积的上下文
                        accumulated_context.update(resolved_context)
                        accumulated_context['insights'] = {
                            'round': thinking_rounds,
                            'previous_analysis': analysis.understanding.model_dump(),
                            'exploration_areas': raw_response.get('understanding', {}).get('next_exploration_areas', [])
                        }
                    
                except ValidationError:
                    # 回退处理
                    return self._create_fallback_analysis(content, raw_response)
            
            return analysis
            
        except Exception as e:
            raise AnalysisError(
                f"消息理解分析失败: {str(e)}",
                trace_id=trace_id,
                context={"content_length": len(content), "thinking_rounds": thinking_rounds},
                cause=e
            )
    
    async def _handle_clarification(
        self,
        analysis: AnalysisModel,
        context: Optional[Dict[str, Any]],
        prompt_version: str
    ) -> str:
        """处理澄清流程"""
        try:
            # 获取澄清提示
            clarification_prompt = prompt_manager.get_response_clarification_prompt(prompt_version)
            system_prompt = await prompt_manager.get_system_prompt_with_tools(prompt_version)
            
            payload = {
                'original_message': analysis.understanding.original_content,
                'understanding': analysis.understanding.model_dump(),
                'response_directives': analysis.response_directives,
                'channel': (context or {}).get('channel')
            }
            
            user_prompt = "\n\n".join([
                clarification_prompt,
                "输入：",
                json.dumps(payload, ensure_ascii=False, default=str),
                "请生成澄清问题。"
            ])
            
            response = await self.llm.chat_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.4,
                max_tokens=220,
            )
            
            return response.strip() if response else "抱歉，我还需要更多信息。"
            
        except Exception as e:
            logger.warning("clarification.failed", error=str(e))
            return "抱歉，我还需要更多信息。"
    
    async def _execute_and_respond(
        self,
        analysis: AnalysisModel,
        original_content: str,
        user_id: str,
        context: Optional[Dict[str, Any]],
        trace_id: str,
        prompt_version: str
    ) -> str:
        """执行工具并生成响应（支持结果验证和反馈优化）
        
        增强功能：
        - 工具执行后验证结果完整性
        - 必要时执行补充查询
        - 最多3轮迭代优化
        """
        try:
            thread_id = (context or {}).get('thread_id') if context else None
            channel = (context or {}).get('channel') if context else None
            shared_thread = bool((context or {}).get('shared_thread'))
            
            # 获取额外上下文
            resolved_context = await self.context_manager.resolve_context_requests(
                context_requests=[req.model_dump() for req in analysis.context_requests],
                understanding=analysis.understanding.model_dump(),
                user_id=user_id,
                thread_id=thread_id,
                shared_thread=shared_thread,
                channel=channel,
                trace_id=trace_id
            )
            
            # 准备上下文数据
            context_payload = {
                'household': (await self.context_manager.get_basic_context(
                    user_id, thread_id, shared_thread, channel
                )).get('household', {})
            }
            context_payload.update(resolved_context)
            
            # 构建完整工具计划
            tool_plan = await self._build_complete_tool_plan(
                analysis=analysis,
                user_id=user_id,
                context=context,
                context_payload=context_payload,
                prompt_version=prompt_version
            )
            
            # 工具执行和验证循环（最多3轮）
            execution_rounds = 0
            max_execution_rounds = 3
            accumulated_results = {'actions_taken': []}
            
            while execution_rounds < max_execution_rounds:
                execution_rounds += 1
                
                # 执行工具
                round_result = await self.tool_executor.execute_tool_plan(
                    steps=tool_plan.get('steps', []),
                    understanding=analysis.understanding.model_dump(),
                    user_id=user_id,
                    context=context,
                    trace_id=trace_id,
                    context_data=context_payload
                )
                
                # 累积结果
                accumulated_results['actions_taken'].extend(
                    round_result.get('actions_taken', [])
                )
                
                # 获取验证配置
                verification_config = tool_plan.get('verification') or analysis.tool_plan.verification
                
                if not verification_config or not verification_config.get('check_completeness'):
                    # 不需要验证，直接结束
                    logger.info(
                        "tool_execution.completed_without_verification",
                        trace_id=trace_id,
                        round=execution_rounds
                    )
                    break
                
                # 验证结果完整性
                needs_supplement = await self._verify_execution_results(
                    results=accumulated_results,
                    verification_config=verification_config,
                    understanding=analysis.understanding.model_dump(),
                    trace_id=trace_id
                )
                
                if not needs_supplement:
                    # 结果满意，结束循环
                    logger.info(
                        "tool_execution.verified_complete",
                        trace_id=trace_id,
                        rounds=execution_rounds
                    )
                    break
                
                if execution_rounds >= max_execution_rounds:
                    # 达到最大轮数，停止
                    logger.warning(
                        "tool_execution.max_rounds_reached",
                        trace_id=trace_id,
                        rounds=execution_rounds
                    )
                    break
                
                # 需要补充查询，构建补充计划
                fallback_strategy = verification_config.get('fallback_strategy', 'expand_search')
                
                logger.info(
                    "tool_execution.supplementing",
                    trace_id=trace_id,
                    round=execution_rounds,
                    strategy=fallback_strategy
                )
                
                # 基于策略调整工具计划
                tool_plan = await self._adjust_tool_plan(
                    original_plan=tool_plan,
                    strategy=fallback_strategy,
                    previous_results=accumulated_results,
                    understanding=analysis.understanding.model_dump(),
                    prompt_version=prompt_version
                )
            
            # 使用累积的结果生成响应
            execution_result = accumulated_results
            
            # 生成响应
            is_simple = await self.tool_executor.is_simple_operation(tool_plan.get('steps', []))
            
            if is_simple:
                response = await self._generate_simple_response(
                    analysis, execution_result, context, prompt_version, context_payload
                )
            else:
                response = await self._generate_detailed_response(
                    original_content, analysis, execution_result, context, prompt_version, context_payload
                )
            
            # 存储对话回合
            await self._store_conversation_turn(
                user_id=user_id,
                thread_id=thread_id,
                trace_id=trace_id,
                user_message=original_content,
                assistant_message=response,
                understanding=analysis.understanding.model_dump(),
                context=context
            )
            
            return response
            
        except Exception as e:
            raise AIEngineError(
                f"执行和响应生成失败: {str(e)}",
                trace_id=trace_id,
                context={"user_id": user_id},
                cause=e
            )
    
    # =================== 辅助方法 ===================
    
    def _create_fallback_analysis(self, content: str, raw_response: dict) -> AnalysisModel:
        """创建回退分析结果"""
        understanding = raw_response.get('understanding', {})
        return AnalysisModel(
            understanding=UnderstandingModel(
                intent=understanding.get('intent'),
                entities=understanding.get('entities', {}),
                need_action=bool(understanding.get('need_action')),
                need_clarification=bool(understanding.get('need_clarification')),
                missing_fields=understanding.get('missing_fields', []),
                clarification_questions=understanding.get('clarification_questions', []),
                thinking_depth=understanding.get('thinking_depth', 0),
                needs_deeper_analysis=bool(understanding.get('needs_deeper_analysis')),
                analysis_reasoning=understanding.get('analysis_reasoning'),
                next_exploration_areas=understanding.get('next_exploration_areas', []),
                original_content=content
            ),
            context_requests=[],
            tool_plan=ToolPlanModel(
                steps=[],
                verification=understanding.get('verification')
            ),
            response_directives=raw_response.get('response_directives', {})
        )
    
    async def _verify_execution_results(
        self,
        results: Dict[str, Any],
        verification_config: Dict[str, Any],
        understanding: Dict[str, Any],
        trace_id: str
    ) -> bool:
        """验证工具执行结果的完整性
        
        返回 True 表示需要补充查询，False 表示结果满意
        """
        try:
            # 验证输入参数类型（调试用）
            if not isinstance(results, dict):
                logger.warning(
                    "verification.invalid_results_type",
                    trace_id=trace_id,
                    results_type=type(results).__name__,
                    results_preview=str(results)[:100] if results else 'None'
                )
                return False  # 类型错误，跳过验证
            
            if not isinstance(verification_config, dict):
                logger.debug(
                    "verification.no_config",
                    trace_id=trace_id,
                    config_type=type(verification_config).__name__
                )
                return False  # 没有验证配置，跳过验证
            # 检查最小结果数量
            min_expected = verification_config.get('min_results_expected')
            if min_expected:
                actual_count = sum(
                    1 for action in results.get('actions_taken', [])
                    if (isinstance(action, dict) and 
                        isinstance(action.get('result'), dict) and 
                        action.get('result', {}).get('success'))
                )
                if actual_count < min_expected:
                    logger.info(
                        "verification.insufficient_results",
                        trace_id=trace_id,
                        expected=min_expected,
                        actual=actual_count
                    )
                    return True  # 需要补充
            
            # 检查是否有失败的操作
            failed_actions = []
            for action in results.get('actions_taken', []):
                if not isinstance(action, dict):
                    continue
                result = action.get('result')
                if isinstance(result, dict):
                    if not result.get('success'):
                        failed_actions.append(action)
                else:
                    # result 不是字典，视为失败
                    failed_actions.append(action)
            
            if failed_actions and verification_config.get('retry_on_failure'):
                logger.info(
                    "verification.has_failures",
                    trace_id=trace_id,
                    failed_count=len(failed_actions)
                )
                return True  # 需要重试
            
            # 基于理解深度判断
            thinking_depth = understanding.get('thinking_depth', 0)
            if thinking_depth >= 2:  # 复杂问题
                # 检查是否有足够的数据支持分析
                if isinstance(results, dict):
                    total_results = len(results.get('actions_taken', []))
                    if total_results < 2:  # 复杂问题至少需要2个数据源
                        return True
                else:
                    # results不是预期的dict格式，跳过验证
                    return False
            
            return False  # 结果满意
            
        except Exception as e:
            logger.warning(
                "verification.failed",
                trace_id=trace_id,
                error=str(e)
            )
            return False  # 验证失败，不再补充
    
    async def _adjust_tool_plan(
        self,
        original_plan: Dict[str, Any],
        strategy: str,
        previous_results: Dict[str, Any],
        understanding: Dict[str, Any],
        prompt_version: str
    ) -> Dict[str, Any]:
        """基于策略调整工具执行计划"""
        try:
            if strategy == 'expand_search':
                # 扩大搜索范围
                adjusted_steps = []
                for step in original_plan.get('steps', []):
                    step_copy = step.copy()
                    if step_copy.get('tool') == 'search':
                        # 增加搜索限制
                        args = step_copy.get('args', {})
                        current_limit = args.get('filters', {}).get('limit', 10)
                        args.setdefault('filters', {})['limit'] = min(current_limit * 2, 50)
                        step_copy['args'] = args
                    adjusted_steps.append(step_copy)
                
                return {'steps': adjusted_steps, 'verification': original_plan.get('verification')}
            
            elif strategy == 'try_different_approach':
                # 尝试不同的方法（例如从精确搜索改为语义搜索）
                # 这里需要根据具体情况调整，暂时返回原计划
                return original_plan
            
            else:
                # 默认策略：返回原计划
                return original_plan
                
        except Exception as e:
            logger.warning(
                "adjust_plan.failed",
                error=str(e)
            )
            return original_plan
    
    async def _build_complete_tool_plan(
        self,
        analysis: AnalysisModel,
        user_id: str,
        context: Optional[Dict[str, Any]],
        context_payload: Dict[str, Any],
        prompt_version: str
    ) -> Dict[str, Any]:
        """构建完整的工具执行计划"""
        existing_steps = analysis.tool_plan.steps
        if existing_steps and not analysis.tool_plan.requires_context:
            return {'steps': [step.model_dump() for step in existing_steps]}
        
        # 需要 AI 重新规划
        system_prompt = await prompt_manager.get_system_prompt_with_tools(prompt_version)
        planning_prompt = await prompt_manager.get_tool_planning_prompt_with_tools(prompt_version)
        
        payload = {
            'understanding': analysis.understanding.model_dump(),
            'analysis_plan': analysis.tool_plan.model_dump(),
            'context_payload': context_payload,
            'user': {
                'id': user_id,
                'channel': (context or {}).get('channel'),
                'thread_id': (context or {}).get('thread_id'),
            }
        }
        
        user_prompt = "\n\n".join([
            planning_prompt,
            '输入数据：',
            json.dumps(payload, ensure_ascii=False, default=str),
            '请仅返回 JSON：{"steps": [...], "meta": {...可选}}，不要附加解释。'
        ])
        
        try:
            plan = await self.llm.chat_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.2,
                max_tokens=800,
            )
            
            if isinstance(plan, dict) and isinstance(plan.get('steps'), list):
                return plan
        except Exception as e:
            logger.warning('tool_plan.generation.failed', error=str(e))
        
        return {'steps': []}
    
    async def _generate_simple_response(
        self,
        analysis: AnalysisModel,
        execution_result: Dict[str, Any],
        context: Optional[Dict[str, Any]],
        prompt_version: str,
        context_payload: Dict[str, Any]
    ) -> str:
        """生成简单确认回复"""
        # 检查是否有 AI 建议的回复
        if analysis.understanding.suggested_reply:
            return analysis.understanding.suggested_reply.strip()
        
        # 低预算模式简化回复
        if self._is_low_budget_mode():
            success_count = sum(
                1 for action in execution_result.get('actions_taken', [])
                if isinstance(action, dict) and (action.get('result', {}) or {}).get('success')
            )
            return "✅ 已记录！" if success_count else "⚠️ 处理遇到问题，请稍后重试。"
        
        # 使用 AI 生成确认回复
        return await self._generate_ack_with_ai(
            analysis, execution_result, context, prompt_version, context_payload
        )
    
    async def _generate_detailed_response(
        self,
        original_message: str,
        analysis: AnalysisModel,
        execution_result: Dict[str, Any],
        context: Optional[Dict[str, Any]],
        prompt_version: str,
        context_payload: Dict[str, Any]
    ) -> str:
        """生成详细回复"""
        response_prompt = prompt_manager.get_response_prompt(prompt_version)
        system_prompt = await prompt_manager.get_system_prompt_with_tools(prompt_version)
        
        payload = {
            'original_message': original_message,
            'understanding': analysis.understanding.model_dump(),
            'execution_result': execution_result,
            'response_directives': analysis.response_directives,
            'context_payload': context_payload,
            'channel': (context or {}).get('channel'),
        }
        
        user_prompt = "\n\n".join([
            response_prompt,
            "输入：",
            json.dumps(payload, ensure_ascii=False, default=str),
            "请生成最终回复。"
        ])
        
        try:
            response = await self.llm.chat_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.6,
                max_tokens=600,
            )
            
            generated = response.strip() if response else "抱歉，我将继续关注您的需求。"
            
            # Threema 长度限制
            if context and context.get('channel') == 'threema' and len(generated) > 400:
                generated = generated[:397] + '...'
            
            return generated
            
        except Exception as e:
            logger.warning('detailed_response.failed', error=str(e))
            return "抱歉，我将继续关注您的需求。"
    
    async def _generate_ack_with_ai(
        self,
        analysis: AnalysisModel,
        execution_result: Dict[str, Any],
        context: Optional[Dict[str, Any]],
        prompt_version: str,
        context_payload: Dict[str, Any]
    ) -> str:
        """使用 AI 生成确认回复"""
        ack_template = prompt_manager.get_ack_prompt(prompt_version)
        if not ack_template:
            ack_template = "{task_context}"
        
        task_context = {
            'understanding': analysis.understanding.model_dump(),
            'execution_result': execution_result,
            'response_directives': analysis.response_directives,
            'context_payload': context_payload,
            'channel': (context or {}).get('channel'),
        }
        
        system_prompt = await prompt_manager.get_system_prompt_with_tools(prompt_version)
        user_prompt = ack_template.format(
            task_context=json.dumps(task_context, ensure_ascii=False, default=str)
        )
        
        try:
            response = await self.llm.chat_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=120,
            )
            return response.strip() if response else "✅ 已完成。"
        except Exception:
            return "✅ 已完成。"
    
    def _record_experiment_result(
        self,
        user_id: str,
        context: Optional[Dict[str, Any]],
        trace_id: str,
        analysis: AnalysisModel,
        response: str
    ):
        """记录实验结果（用于 A/B 测试）"""
        try:
            # 获取活跃实验
            active_experiments = ab_testing_manager.list_active_experiments()
            if not active_experiments:
                return
            
            channel = (context or {}).get('channel', 'unknown')
            
            # 为每个实验记录结果
            for experiment in active_experiments:
                variant, version = ab_testing_manager.get_variant_for_user(
                    user_id, experiment['id'], channel=channel
                )
                
                if variant != "control":  # 只记录实验组的结果
                    result = ExperimentResult(
                        user_id=user_id,
                        experiment_id=experiment['id'],
                        variant=variant,
                        trace_id=trace_id,
                        channel=channel,
                        timestamp=time.time(),
                        response_time_ms=0,  # TODO: 计算实际响应时间
                        success=True,  # TODO: 基于实际执行结果判断
                        need_clarification=analysis.understanding.need_clarification,
                        tool_calls_count=len(analysis.tool_plan.steps),
                        response_length=len(response)
                    )
                    
                    ab_testing_manager.record_result(result)
                    
        except Exception as e:
            logger.warning("experiment_result.record.failed", error=str(e))
    
    async def _handle_error(self, error: Exception, trace_id: str, user_id: str) -> str:
        """统一错误处理"""
        logger.error(
            "message.process.error",
            trace_id=trace_id,
            user_id=user_id,
            error_type=type(error).__name__,
            error=str(error)
        )
        
        # 根据错误类型返回用户友好的消息
        if isinstance(error, (AnalysisError, ContextResolutionError, ToolPlanningError)):
            return get_user_friendly_message(error)
        elif isinstance(error, (MCPToolError, ToolTimeoutError, ToolExecutionError)):
            return get_user_friendly_message(error)
        elif isinstance(error, LLMError):
            return get_user_friendly_message(error)
        else:
            return "抱歉，处理您的消息时出现了问题，请稍后重试。"
    
    def _cleanup_trace(self, trace_id: str):
        """清理追踪数据"""
        try:
            self._tool_calls_by_trace.pop(trace_id, None)
            self._emb_cache_by_trace.pop(trace_id, None)
        except Exception:
            pass
    
    def _is_low_budget_mode(self) -> bool:
        """检查是否处于低预算模式"""
        return bool(getattr(settings, 'LOW_LLM_BUDGET', False))
    
    # =================== MCP 工具调用 ===================
    
    async def _call_mcp_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """调用 MCP 工具 - 简化版本"""
        trace_id = kwargs.get('trace_id')
        
        if self._http_client is None:
            self._http_client = httpx.AsyncClient()
        
        try:
            timeout = 10.0  # 统一超时时间
            response = await self._http_client.post(
                f"{self.mcp_url}/tool/{tool_name}",
                json=kwargs,
                timeout=timeout,
            )
            response.raise_for_status()
            result = response.json()
            
            # 记录调用
            if trace_id:
                self._tool_calls_by_trace.setdefault(trace_id, []).append({
                    'tool': tool_name,
                    'success': True,
                    'timestamp': time.time()
                })
            
            return result
            
        except Exception as e:
            # 记录失败
            if trace_id:
                self._tool_calls_by_trace.setdefault(trace_id, []).append({
                    'tool': tool_name,
                    'success': False,
                    'error': str(e),
                    'timestamp': time.time()
                })
            
            raise ToolExecutionError(
                f"工具 {tool_name} 调用失败: {str(e)}",
                trace_id=trace_id,
                context={"tool_name": tool_name},
                cause=e
            )
    
    # =================== 向量嵌入缓存 ===================
    
    async def _get_embedding_cached(self, text: str, trace_id: Optional[str]) -> Optional[List[float]]:
        """获取缓存的向量嵌入"""
        if not text:
            return None
        
        # 检查 trace 级缓存
        trace_cache = self._emb_cache_by_trace.get(trace_id or '', {})
        if text in trace_cache:
            return trace_cache[text]
        
        # 检查全局缓存
        global_item = self._emb_cache_global.get(text)
        if global_item:
            vec, ts = global_item
            if (time.time() - ts) < self._emb_cache_global_ttl:
                trace_cache[text] = vec
                if trace_id:
                    self._emb_cache_by_trace[trace_id] = trace_cache
                return vec
        
        # 生成新向量
        try:
            embs = await self.llm.embed([text])
            vec = [float(x) for x in (embs[0] or [])] if embs else None
        except Exception:
            vec = None
        
        if vec is not None:
            # 更新缓存
            trace_cache[text] = vec
            if trace_id:
                self._emb_cache_by_trace[trace_id] = trace_cache
            
            # 更新全局缓存（LRU）
            self._update_global_embedding_cache(text, vec)
        
        return vec
    
    def _update_global_embedding_cache(self, text: str, vec: List[float]):
        """更新全局向量缓存（简单的 LRU）"""
        try:
            # 容量控制
            if len(self._emb_cache_global) >= self._emb_cache_global_max_items:
                # 移除最旧的项
                oldest_key = min(
                    self._emb_cache_global.keys(),
                    key=lambda k: self._emb_cache_global[k][1]
                )
                self._emb_cache_global.pop(oldest_key, None)
            
            self._emb_cache_global[text] = (vec, time.time())
        except Exception:
            pass
    
    # =================== 对话存储 ===================
    
    async def _store_conversation_turn(
        self,
        user_id: str,
        thread_id: Optional[str],
        trace_id: str,
        user_message: str,
        assistant_message: str,
        understanding: Dict[str, Any],
        context: Optional[Dict[str, Any]]
    ):
        """存储对话回合"""
        try:
            common = {
                'type': 'chat_turn',
                'thread_id': thread_id,
                'trace_id': trace_id,
                'channel': (context or {}).get('channel'),
                'timestamp': datetime.now().isoformat()
            }
            
            # 平铺entities到顶层（与单个store保持一致，确保amount/occurred_at在顶层）
            entities = understanding.get('entities', {})
            
            user_ai = {
                **common,
                'role': 'user',
                'intent': understanding.get('intent'),
                **entities,  # 平铺entities，不再嵌套
            }
            
            assistant_ai = {
                **common,
                'role': 'assistant',
                'intent': understanding.get('intent'),
                **entities,  # 平铺entities，不再嵌套
            }
            
            memories = [
                {"content": user_message, "ai_data": user_ai, "user_id": user_id},
                {"content": assistant_message, "ai_data": assistant_ai, "user_id": user_id},
            ]
            
            await self._call_mcp_tool('batch_store', memories=memories, trace_id=trace_id)
            
        except Exception as e:
            logger.error("store_conversation.failed", trace_id=trace_id, error=str(e))
    
    # =================== 提醒任务 ===================
    
    async def check_and_send_reminders(self, send_func):
        """检查并发送待发提醒
        
        Args:
            send_func: 发送函数，签名为 async def(user_id: str, content: str) -> bool
        """
        try:
            # 获取所有活跃用户列表
            all_users = await self._get_all_active_users()
            
            if not all_users:
                logger.debug("reminder.no_users")
                return
            
            total_reminders = 0
            
            # 逐个检查每个用户的待发提醒
            for user_id in all_users:
                try:
                    user_reminders = await self._call_mcp_tool(
                        'get_pending_reminders',
                        user_id=user_id
                    )
                    
                    if not user_reminders or not isinstance(user_reminders, list):
                        continue
                    
                    total_reminders += len(user_reminders)
                    
                    for reminder in user_reminders:
                        await self._process_single_reminder(reminder, user_id, send_func)
                
                except Exception as e:
                    logger.error(
                        "reminder.user_check_failed",
                        user_id=user_id,
                        error=str(e)
                    )
            
            if total_reminders > 0:
                logger.info("reminder.check_completed", total_found=total_reminders)
            
        except Exception as e:
            logger.error("reminder.check_failed", error=str(e))
    
    async def _get_all_active_users(self) -> List[str]:
        """获取所有活跃用户ID列表"""
        try:
            # 方法1：通过家庭服务获取所有用户
            household_context = await household_service.get_context()
            family_scope = household_context.get('family_scope', {})
            user_ids = family_scope.get('user_ids', [])
            
            if user_ids:
                logger.debug("reminder.users_from_household", count=len(user_ids))
                return user_ids
            
            # 方法2：回退策略 - 通过数据库直接查询
            logger.info("reminder.fallback_to_db_query")
            return await self._get_users_from_db()
            
        except Exception as e:
            logger.warning("get_active_users.failed", error=str(e))
            return []
    
    async def _get_users_from_db(self) -> List[str]:
        """从数据库直接获取用户列表（回退方法）"""
        try:
            # 简化：只获取有渠道的用户（能接收提醒的用户）
            if self._http_client is None:
                self._http_client = httpx.AsyncClient()
            
            # 通过MCP服务调用原生SQL（如果支持）
            # 这里暂时返回空列表，避免复杂的实现
            logger.warning("reminder.no_users_available")
            return []
            
        except Exception as e:
            logger.warning("get_users_from_db.failed", error=str(e))
            return []
    
    async def _process_single_reminder(self, reminder: dict, user_id: str, send_func):
        """处理单个提醒"""
        try:
            reminder_id = reminder.get('reminder_id')
            content = reminder.get('content', '')
            ai_understanding = reminder.get('ai_understanding', {})
            
            if not reminder_id:
                logger.warning("reminder.missing_id", reminder=reminder)
                return
            
            # 生成提醒消息
            reminder_text = self._format_reminder_message(content, ai_understanding)
            
            # 发送提醒
            success = await send_func(user_id, reminder_text)
            
            if success:
                # 标记为已发送
                await self._call_mcp_tool(
                    'mark_reminder_sent',
                    reminder_id=reminder_id
                )
                
                logger.info(
                    "reminder.sent", 
                    reminder_id=reminder_id,
                    user_id=user_id
                )
            else:
                logger.warning(
                    "reminder.send_failed",
                    reminder_id=reminder_id,
                    user_id=user_id
                )
        
        except Exception as e:
            logger.error(
                "reminder.process_single_failed",
                reminder_id=reminder.get('reminder_id'),
                user_id=user_id,
                error=str(e)
            )
    
    def _format_reminder_message(self, content: str, ai_understanding: dict) -> str:
        """格式化提醒消息"""
        try:
            # 提取关键信息
            reminder_type = ai_understanding.get('type', '')
            person = ai_understanding.get('person', '')
            event = ai_understanding.get('event', '')
            
            # 根据类型生成提醒
            if reminder_type == 'vaccination':
                if person:
                    return f"🏥 提醒：该给{person}打疫苗了！\n\n详情：{content}"
                else:
                    return f"🏥 疫苗提醒：{content}"
            
            elif reminder_type == 'medication':
                if person:
                    return f"💊 用药提醒：记得给{person}吃药\n\n详情：{content}"
                else:
                    return f"💊 用药提醒：{content}"
            
            elif reminder_type == 'appointment':
                return f"📅 预约提醒：{content}"
            
            elif reminder_type == 'task':
                return f"✅ 任务提醒：{content}"
            
            else:
                # 通用提醒格式
                return f"⏰ 提醒：{content}"
                
        except Exception:
            # 回退到简单格式
            return f"⏰ 提醒：{content}"
    
    # =================== 初始化和清理 ===================
    
    async def initialize_mcp(self):
        """初始化 MCP 客户端连接"""
        try:
            if self._http_client is None:
                self._http_client = httpx.AsyncClient()
            
            response = await self._http_client.get(f"{self.mcp_url}/health", timeout=5.0)
            if response.status_code == 200:
                logger.info("mcp.connected", url=self.mcp_url)
                self.mcp_client = True
            else:
                logger.warning("mcp.health_check.failed", status=response.status_code)
                
        except Exception as e:
            logger.error("mcp.connection.failed", error=str(e))
            self.mcp_client = None
    
    async def initialize_embedding_warmup(self):
        """预热 embedding 模型"""
        try:
            logger.info("embedding.warmup.start")
            success = await self.llm.warmup_embedding_model()
            if success:
                logger.info("embedding.warmup.success")
            else:
                logger.warning("embedding.warmup.failed")
        except Exception as e:
            logger.warning("embedding.warmup.error", error=str(e))
    
    async def close(self):
        """关闭连接和清理资源"""
        try:
            if self._http_client is not None:
                await self._http_client.aclose()
        except Exception:
            pass


# 导出兼容性别名
AIEngine = AIEngineV2

# 创建全局实例（保持向后兼容）
ai_engine = AIEngineV2()

# V2版本别名（如果需要的话）
ai_engine_v2 = ai_engine
