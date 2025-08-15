"""
AI驱动的核心引擎 - 让AI决定一切
"""
import json
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
from .core.config import settings
from .services.media_service import make_signed_url

logger = structlog.get_logger(__name__)

def _looks_like_uuid(value: Optional[str]) -> bool:
    if not value or not isinstance(value, str):
        return False
    try:
        uuid.UUID(value)
        return True
    except Exception:
        return False

# 统一改为从 YAML 读取 prompts（见 prompt_manager）


class AIEngine:
    def __init__(self):
        # 统一 LLM 客户端（可按配置切换 OpenAI 兼容/Anthropic 等）
        self.llm = LLMClient()
        self.mcp_client = None
        self.mcp_url = os.getenv('MCP_SERVER_URL', 'http://faa-mcp:8000')
        # 工具调用暂存，用于交互持久化与回溯（按 trace_id 聚合）
        self._tool_calls_by_trace: Dict[str, List[Dict[str, Any]]] = {}
        # HTTP 客户端复用
        self._http_client: Optional[httpx.AsyncClient] = None
        # 每次请求级的嵌入缓存（按 trace_id 划分）
        self._emb_cache_by_trace: Dict[str, Dict[str, List[float]]] = {}
        
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
    
    async def close(self):
        """关闭MCP客户端连接"""
        try:
            if self._http_client is not None:
                await self._http_client.aclose()
        except Exception:
            pass
    
    async def process_message(self, content: str, user_id: str, context: Dict[str, Any] = None) -> str:
        """
        处理用户消息 - 完全由AI驱动
        
        Args:
            content: 消息内容（已解密的文本）
            user_id: 用户ID
            context: 消息上下文（channel、sender_id等，让AI理解）
        """
        # 贯穿式 trace_id
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
            # 初始化本次 trace 的工具调用记录与嵌入缓存
            self._tool_calls_by_trace[trace_id] = []
            self._emb_cache_by_trace[trace_id] = {}
            # 将附件的衍生文本纳入可检索/嵌入的语境（M1：先拼接文本，不做复杂权重）
            attachments = (context or {}).get('attachments') if context else None
            derived_texts: List[str] = []
            if isinstance(attachments, list):
                for att in attachments:
                    if not isinstance(att, dict):
                        continue
                    # 预留字段名，后续可由预处理模块填充
                    tx = att.get('transcription', {}).get('text') if isinstance(att.get('transcription'), dict) else None
                    if not tx:
                        tx = att.get('ocr_text')
                    if not tx:
                        tx = att.get('vision_summary')
                    if tx:
                        derived_texts.append(str(tx))
            if derived_texts:
                content = (content or '').strip()
                extra = "\n\n[来自附件的文本]\n" + "\n".join(derived_texts)
                content = (content + extra) if content else "\n".join(derived_texts)
            # 新流程：先做轻理解以便早停
            understanding = await self._light_understand_message(content, user_id, context, trace_id=trace_id)

            if understanding.get('need_clarification'):
                # 直接生成澄清回复，省略所有后续步骤
                result = {"actions_taken": []}
                response = await self._generate_clarification_response(content, understanding, context)
            else:
                # 对于查询/分析类，升级为重理解（带批量上下文）
                do_semantic = self._should_semantic_search(content)
                if do_semantic:
                    understanding = await self._understand_message(content, user_id, context, trace_id=trace_id)
            
                # 由 LLM 产出工具计划
                plan = await self._build_tool_plan(understanding, user_id, context=context)
                steps = plan.get('steps') or []

                # 如果未做重理解，但计划中存在 search/aggregate，则补做一次重理解以提升回答质量
                if (not do_semantic) and any(((s or {}).get('tool') in {'search','aggregate'}) for s in steps):
                    understanding = await self._understand_message(content, user_id, context, trace_id=trace_id)
                # 执行工具
                result = await self._execute_tool_steps(steps, understanding, user_id, context=context, trace_id=trace_id)
                # 回复：简单操作走快速确认，否则走正常生成
                if self._is_simple_actions_only(steps):
                    response = self._build_simple_ack_response(understanding, result, context)
                else:
                    response = await self._generate_normal_response(content, understanding, result, context)

            # 存储对话回合（用户与助手各一条），用于连续对话与后续检索
            try:
                await self._store_chat_turns(
                    user_id=user_id,
                    thread_id=thread_id,
                    trace_id=trace_id,
                    user_message=content,
                    assistant_message=response,
                    understanding=understanding,
                    context=context,
                )
            except Exception as e:
                logger.error("store.chat_turns.failed", trace_id=trace_id, error=str(e))

            # 触发会话摘要（后台任务）
            try:
                import asyncio as _asyncio
                _asyncio.create_task(self._maybe_summarize_thread(user_id=user_id, thread_id=thread_id, trace_id=trace_id))
            except Exception as e:
                logger.warning("thread.summarize.skip", trace_id=trace_id, error=str(e))

            # 落盘交互轨迹，便于排障
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
            
            return response
            
        except Exception as e:
            logger.error("message.process.error", trace_id=trace_id, error=str(e))
            return "抱歉，处理您的消息时出现了错误。"
        finally:
            # 清理本次 trace 的工具调用缓存
            try:
                if trace_id in self._tool_calls_by_trace:
                    self._tool_calls_by_trace.pop(trace_id, None)
                if trace_id in self._emb_cache_by_trace:
                    self._emb_cache_by_trace.pop(trace_id, None)
            except Exception:
                pass
    
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
                if isinstance(memory, dict):
                    formatted_memories.append({
                        'content': memory.get('content', ''),
                        'ai_understanding': memory.get('ai_understanding', {}),
                        'time': memory.get('occurred_at', '')
                    })
            
            return formatted_memories
            
        except Exception as e:
            logger.error(f"Error getting recent memories: {e}")
            return []
    
    async def _understand_message(self, content: str, user_id: str, context: Dict[str, Any] = None, *, trace_id: str) -> Dict[str, Any]:
        """
        AI理解消息内容 - 增强版，包含历史上下文和信息完整性检查
        """
        # 上下文构建：批量检索减少 MCP 往返
        thread_id = (context or {}).get('thread_id') if context else None
        channel = (context or {}).get('channel') if context else None
        # 共享线程策略：当上下文指示 shared_thread/conversation_scope=shared 时启用
        shared_thread = False
        if context:
            if context.get('shared_thread') is True:
                shared_thread = True
            if context.get('conversation_scope') == 'shared':
                shared_thread = True
        # 启发式控制是否做语义检索，避免不必要的第二次 search
        do_semantic = self._should_semantic_search(content)
        recent_memories, semantic_related, thread_summaries = await self._build_context_via_batch_search(
            user_id=user_id,
            query=content,
            thread_id=thread_id,
            shared_thread=shared_thread,
            channel=channel,
            include_semantic=do_semantic,
            trace_id=trace_id,
        )
        
        # 构建上下文信息
        context_info = ""
        if context:
            context_info = f"\n消息来源：{context.get('channel', '未知')}"
            if context.get('sender_id'):
                context_info += f"\n发送者ID：{context['sender_id']}"
            if context.get('nickname'):
                context_info += f"\n发送者昵称：{context['nickname']}"
        
        # 分块配额 + 重排去重
        def normalize_key(m: Dict[str, Any]) -> str:
            aiu = m.get('ai_understanding') or {}
            intent = aiu.get('intent') if isinstance(aiu, dict) else None
            when = m.get('time') or m.get('occurred_at') or ''
            return f"{m.get('content','')}||{intent or ''}||{when}"

        def fmt_with_budget(items: List[Dict[str, Any]], title: str, char_budget: int, start_index: int = 1, seen: Optional[set] = None) -> Tuple[str, int, int]:
            seen_local = seen if seen is not None else set()
            block_lines: List[str] = []
            count_included = 0
            for idx, m in enumerate(items, start_index):
                key = normalize_key(m)
                if key in seen_local:
                    continue
                seen_local.add(key)
                content_line = m.get('content', '')
                aiu = m.get('ai_understanding') if isinstance(m.get('ai_understanding'), dict) else {}
                intent = aiu.get('intent') if isinstance(aiu, dict) else None
                when = m.get('time') or m.get('occurred_at') or ''
                line = f"\n{idx}. {when}: {content_line}"
                if intent:
                    line += f" (意图: {intent})"
                # 预估添加后长度
                projected = (0 if not block_lines else len(''.join(block_lines))) + len(line)
                if projected > char_budget and count_included > 0:
                    break
                block_lines.append(line)
                count_included += 1
            if not block_lines:
                return "", start_index, 0
            header = f"\n\n{title}:"
            text = header + ''.join(block_lines)
            return text, start_index + count_included, count_included

        # 预算：总 3500，按 摘要:600 / 最近:2100 / 语义:800 分配
        budget_summary = 600
        budget_recent = 2100
        budget_semantic = 800
        seen_keys: set = set()
        running_index = 1
        history_parts: List[str] = []

        # 优先级：摘要 > 最近 > 语义
        if thread_summaries:
            text, running_index, _ = fmt_with_budget(thread_summaries, "会话摘要", budget_summary, running_index, seen_keys)
            if text:
                history_parts.append(text)
        if recent_memories:
            text, running_index, _ = fmt_with_budget(recent_memories, "最近的交互历史（用于理解上下文）", budget_recent, running_index, seen_keys)
            if text:
                history_parts.append(text)
        if semantic_related:
            text, running_index, _ = fmt_with_budget(semantic_related, "与当前问题语义相关的历史", budget_semantic, running_index, seen_keys)
            if text:
                history_parts.append(text)

        history_context = ''.join(history_parts)
        # 兜底再截断（极少数情况下三块之和仍可能略超出）
        if len(history_context) > 3500:
            history_context = history_context[:3500]

        # 打印最终上下文信息到日志
        try:
            logger.info(
                "llm.context.built",
                trace_id=trace_id,
                thread_id=thread_id,
                channel=channel,
                shared_thread=shared_thread,
                context_length=len(history_context),
                context_preview=history_context[:500],
                recent_count=len(recent_memories) if isinstance(recent_memories, list) else 0,
                semantic_enabled=do_semantic,
                semantic_count=len(semantic_related) if isinstance(semantic_related, list) else 0,
                summary_count=len(thread_summaries) if isinstance(thread_summaries, list) else 0,
            )
        except Exception:
            pass
        
        # 获取当前时间用于时间理解
        current_time = datetime.now()
        
        # 使用prompt管理器获取理解指导
        understanding_guide = prompt_manager.get_understanding_prompt()
        
        # 构建动态参数
        prompt_params = {
            'current_time': current_time.isoformat(),
            'content': content,
            'context_info': context_info,
            'history_context': history_context,
            'understanding_guide': understanding_guide if understanding_guide else '',
            'today_date': current_time.date(),
            'yesterday_date': (current_time - timedelta(days=1)).date(),
            'day_before_yesterday_date': (current_time - timedelta(days=2)).date(),
            'current_month': current_time.strftime('%Y-%m')
        }
        
        # 从 YAML 获取格式化的 prompt
        prompt = prompt_manager.get_message_understanding_prompt(**prompt_params)
        
        def _safe_json(text: str) -> Dict[str, Any]:
            try:
                return json.loads(text)
            except Exception:
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end != -1 and end > start:
                    try:
                        return json.loads(text[start:end+1])
                    except Exception:
                        pass
                return {}

        try:
            # 使用包含动态工具信息的系统 prompt
            system_prompt_with_tools = await prompt_manager.get_system_prompt_with_tools()
            understanding = await self.llm.chat_json(
                system_prompt=system_prompt_with_tools,
                user_prompt=prompt,
                temperature=0.3,
                max_tokens=1200,
            )
        except Exception as e:
            # 某些兼容端点可能不支持 JSON 强约束，退化为文本并尝试解析
            logger.warning(f"chat_json failed, fallback to text: {e}")
            raw = await self.llm.chat_text(
                system_prompt=system_prompt_with_tools,
                user_prompt=prompt,
                temperature=0.3,
                max_tokens=1200,
            )
            understanding = _safe_json(raw)
        # 校验与补全理解结果
        class UnderstandingModel(BaseModel):
            intent: Optional[str] = None
            entities: Dict[str, Any] = Field(default_factory=dict)
            need_action: bool = False
            need_clarification: bool = False
            missing_fields: List[str] = Field(default_factory=list)
            clarification_questions: List[str] = Field(default_factory=list)
            suggested_actions: List[Dict[str, Any]] = Field(default_factory=list)
            original_content: str = content
            context_related: Optional[bool] = None

        try:
            parsed = UnderstandingModel(**understanding)
            understanding = parsed.model_dump()
        except ValidationError as ve:
            logger.warning("llm.parse.validation_error", trace_id=trace_id, error=str(ve), raw=understanding)
            # 容错：最少保证必须字段存在
            understanding.setdefault('entities', {})
            understanding.setdefault('need_action', False)
            understanding.setdefault('need_clarification', False)
            understanding.setdefault('missing_fields', [])
            understanding.setdefault('clarification_questions', [])
            understanding.setdefault('suggested_actions', [])

        understanding['original_content'] = content

        logger.info(
            "llm.understanding.response",
            trace_id=trace_id,
            intent=understanding.get('intent'),
            need_action=understanding.get('need_action'),
            need_clarification=understanding.get('need_clarification'),
            entities=understanding.get('entities')
        )
        
        return understanding

    async def _build_context_via_batch_search(
        self,
        *,
        user_id: str,
        query: str,
        thread_id: Optional[str],
        shared_thread: bool,
        channel: Optional[str],
        include_semantic: bool,
        trace_id: str,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """使用 batch_search 一次取回 最近对话/语义相关/线程摘要，并统一格式化。"""
        queries: List[Dict[str, Any]] = []
        # 最近对话
        recent_filters: Dict[str, Any] = {"limit": 10, "type": "chat_turn"}
        if thread_id:
            recent_filters["thread_id"] = thread_id
        if shared_thread:
            recent_filters["shared_thread"] = True
        if channel:
            recent_filters["channel"] = channel
        queries.append({"query": "", "user_id": user_id, "filters": recent_filters})

        # 语义相关（可选）
        q_emb: Optional[List[float]] = None
        if include_semantic and query:
            try:
                cache = self._emb_cache_by_trace.get(trace_id, {})
                if query in cache:
                    q_emb = cache[query]
                else:
                    embs = await self.llm.embed([query])
                    q_emb = embs[0] if embs else None
                    cache[query] = q_emb
                    self._emb_cache_by_trace[trace_id] = cache
            except Exception:
                q_emb = None
            sem_filters: Dict[str, Any] = {"limit": 5}
            if thread_id:
                sem_filters["thread_id"] = thread_id
            if shared_thread:
                sem_filters["shared_thread"] = True
            if channel:
                sem_filters["channel"] = channel
            queries.append({"query": query, "user_id": user_id, "filters": sem_filters, "query_embedding": q_emb})

        # 线程摘要
        summ_filters: Dict[str, Any] = {"limit": 30, "type": "thread_summary"}
        if thread_id:
            summ_filters["thread_id"] = thread_id
        if shared_thread:
            summ_filters["shared_thread"] = True
        if channel:
            summ_filters["channel"] = channel
        queries.append({"query": "thread summary", "user_id": user_id, "filters": summ_filters})

        # 执行批量检索
        batch_res = await self._call_mcp_tool("batch_search", queries=queries, trace_id=trace_id)
        if not isinstance(batch_res, list):
            return [], [], []

        # 拆分并格式化
        recent_res = batch_res[0] if len(batch_res) > 0 and isinstance(batch_res[0], list) else []
        sem_res = []
        if include_semantic:
            if len(batch_res) > 1 and isinstance(batch_res[1], list):
                sem_res = batch_res[1]
        summ_res = batch_res[-1] if len(batch_res) >= 1 and isinstance(batch_res[-1], list) else []

        def _fmt_list(src: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            out: List[Dict[str, Any]] = []
            for r in src:
                if isinstance(r, dict) and not r.get("_meta"):
                    out.append({
                        "content": r.get("content", ""),
                        "ai_understanding": r.get("ai_understanding", {}),
                        "time": r.get("occurred_at"),
                    })
            return out

        recent_formatted = _fmt_list(recent_res)
        sem_formatted = _fmt_list(sem_res)

        summ_formatted: List[Dict[str, Any]] = []
        for r in summ_res:
            if not isinstance(r, dict):
                continue
            aiu = r.get("ai_understanding")
            if isinstance(aiu, dict) and aiu.get("type") == "thread_summary" and (thread_id is None or aiu.get("thread_id") == thread_id):
                summ_formatted.append({
                    "content": r.get("content", ""),
                    "ai_understanding": aiu,
                    "time": r.get("occurred_at"),
                })

        return recent_formatted, sem_formatted, (summ_formatted[:1])

    async def _light_understand_message(self, content: str, user_id: str, context: Dict[str, Any] = None, *, trace_id: str) -> Dict[str, Any]:
        """轻理解：不做历史检索，低开销判定意图/实体/是否需要澄清。"""
        current_time = datetime.now()
        prompt_params = {
            'current_time': current_time.isoformat(),
            'content': content,
            'context_info': '',
            'history_context': '',
            'understanding_guide': prompt_manager.get_understanding_prompt() or '',
            'today_date': current_time.date(),
            'yesterday_date': (current_time - timedelta(days=1)).date(),
            'day_before_yesterday_date': (current_time - timedelta(days=2)).date(),
            'current_month': current_time.strftime('%Y-%m')
        }
        prompt = prompt_manager.get_message_understanding_prompt(**prompt_params)
        system_prompt_with_tools = await prompt_manager.get_system_prompt_with_tools()
        try:
            understanding = await self.llm.chat_json(
                system_prompt=system_prompt_with_tools,
                user_prompt=prompt,
                temperature=0.2,
                max_tokens=400,
            )
        except Exception:
            raw = await self.llm.chat_text(
                system_prompt=system_prompt_with_tools,
                user_prompt=prompt,
                temperature=0.2,
                max_tokens=400,
            )
            try:
                understanding = json.loads(raw)
            except Exception:
                understanding = {}

        class UnderstandingModel(BaseModel):
            intent: Optional[str] = None
            entities: Dict[str, Any] = Field(default_factory=dict)
            need_action: bool = False
            need_clarification: bool = False
            missing_fields: List[str] = Field(default_factory=list)
            clarification_questions: List[str] = Field(default_factory=list)
            suggested_actions: List[Dict[str, Any]] = Field(default_factory=list)
            original_content: str = content
            context_related: Optional[bool] = None

        try:
            parsed = UnderstandingModel(**understanding)
            understanding = parsed.model_dump()
        except ValidationError as ve:
            logger.warning("llm.light.parse.validation_error", trace_id=trace_id, error=str(ve), raw=understanding)
            understanding.setdefault('entities', {})
            understanding.setdefault('need_action', False)
            understanding.setdefault('need_clarification', False)
            understanding.setdefault('missing_fields', [])
            understanding.setdefault('clarification_questions', [])
            understanding.setdefault('suggested_actions', [])
        understanding['original_content'] = content
        return understanding
    
    async def _build_tool_plan(self, understanding: Dict[str, Any], user_id: str, *, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        由 LLM 产出工具计划（Tool Plan/DSL）。
        返回格式示例：
        {
          "steps": [
            {"tool": "store", "args": {"content": "...", "ai_data": {...}}},
            {"tool": "aggregate", "args": {"operation": "sum", "field": "amount", "filters": {...}}}
          ]
        }
        """
        # 使用包含动态工具信息的 prompts
        system_prompt = await prompt_manager.get_system_prompt_with_tools()
        planning_guide = await prompt_manager.get_tool_planning_prompt_with_tools()
        user_prompt = (
            (planning_guide or "你将以工具编排的方式完成任务。只输出 steps JSON。")
        )
        context_info = {
            "user_id": user_id,
            "channel": (context or {}).get("channel") if context else None,
            "thread_id": (context or {}).get("thread_id") if context else None,
        }
        plan_input = {
            "understanding": understanding,
            "context": context_info,
        }
        try:
            plan = await self.llm.chat_json(
                system_prompt=system_prompt,
                user_prompt=f"输入：\n{json.dumps(plan_input, ensure_ascii=False)}\n\n请输出工具计划JSON。\n{user_prompt}",
                temperature=0.2,
                max_tokens=800,
            )
            if not isinstance(plan, dict):
                return {"steps": []}
            steps = plan.get("steps")
            if not isinstance(steps, list):
                return {"steps": []}
            return {"steps": steps}
        except Exception:
            return {"steps": []}
    
    def _is_simple_actions_only(self, steps: List[Dict[str, Any]]) -> bool:
        """只包含 store/schedule_reminder 等轻量操作。"""
        if not steps:
            return True
        for s in steps:
            t = (s or {}).get('tool')
            if t in {"search", "aggregate", "render_chart"}:
                return False
        return True
    
    async def _execute_tool_steps(self, steps: List[Dict[str, Any]], understanding: Dict[str, Any], user_id: str, *, context: Optional[Dict[str, Any]] = None, trace_id: str) -> Dict[str, Any]:
        """执行给定的工具步骤；支持嵌入缓存与最小化参数注入。"""
        result = {"actions_taken": []}
        if not steps:
            return result

        last_store_id: Optional[str] = None
        allowed_tools = {"store", "search", "aggregate", "schedule_reminder", "get_pending_reminders", "mark_reminder_sent", "update_memory_fields", "render_chart", "batch_store", "batch_search"}

        for step in steps:
            if not isinstance(step, dict):
                continue
            tool = step.get('tool')
            args = step.get('args') or {}
            if tool not in allowed_tools:
                continue

            # 注入通用参数
            if tool in {"store", "search", "aggregate", "get_pending_reminders", "batch_store", "batch_search"}:
                args.setdefault('user_id', user_id)

            # 解析占位符依赖
            if tool == 'schedule_reminder':
                mem_id = args.get('memory_id')
                if mem_id == '$LAST_STORE_ID' and last_store_id:
                    args['memory_id'] = last_store_id
                if args.get('from_last_store') and last_store_id:
                    args['memory_id'] = last_store_id
                    args.pop('from_last_store', None)

            # 生成嵌入：优先从本次 trace 的缓存复用
            try:
                if tool == 'store':
                    text_for_embed = args.get('content') or understanding.get('original_content', '')
                    if text_for_embed and 'embedding' not in args:
                        cache = self._emb_cache_by_trace.get(trace_id, {})
                        if text_for_embed in cache:
                            args['embedding'] = cache[text_for_embed]
                        else:
                            embs = await self.llm.embed([text_for_embed])
                            # 确保为 Python float 列表，防止 JSON 序列化失败
                            args['embedding'] = ([float(x) for x in embs[0]] if (embs and embs[0]) else None)
                            cache[text_for_embed] = args['embedding']
                            self._emb_cache_by_trace[trace_id] = cache
                    # 合并 ai_data
                    ai_data = args.get('ai_data') or {}
                    entities = understanding.get('entities', {})
                    merged = {**entities, **ai_data}
                    if not merged.get('occurred_at'):
                        merged['occurred_at'] = datetime.now().isoformat()
                    if context and context.get('thread_id'):
                        merged.setdefault('thread_id', context.get('thread_id'))
                    merged.setdefault('trace_id', trace_id)
                    if context and isinstance(context.get('attachments'), list):
                        merged.setdefault('attachments', context.get('attachments'))
                    args['ai_data'] = merged
                elif tool == 'search':
                    q = args.get('query')
                    if q and not args.get('query_embedding'):
                        cache = self._emb_cache_by_trace.get(trace_id, {})
                        if q in cache:
                            args['query_embedding'] = cache[q]
                        else:
                            embs = await self.llm.embed([q])
                            args['query_embedding'] = ([float(x) for x in embs[0]] if (embs and embs[0]) else None)
                            cache[q] = args['query_embedding']
                            self._emb_cache_by_trace[trace_id] = cache
            except Exception:
                pass

            exec_result = await self._call_mcp_tool(tool, **{**args, 'trace_id': trace_id})
            result['actions_taken'].append({'action': tool, 'result': exec_result})
            if tool == 'store' and isinstance(exec_result, dict) and exec_result.get('success'):
                last_store_id = exec_result.get('id') or last_store_id
        return result

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
        user_ai = {**common, 'role': 'user', 'intent': understanding.get('intent'), 'entities': understanding.get('entities', {})}
        assistant_ai = {**common, 'role': 'assistant', 'intent': understanding.get('intent'), 'entities': understanding.get('entities', {})}
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


    
    async def _generate_response(self, original_message: str, understanding: Dict[str, Any], execution_result: Dict[str, Any], context: Dict[str, Any] = None) -> str:
        """
        生成自然语言回复 - 增强版，优先处理信息完整性检查
        """
        # 🎯 优先级1：处理信息不完整的情况
        if understanding.get('need_clarification'):
            return await self._generate_clarification_response(original_message, understanding, context)
        
        # 🎯 优先级2：处理正常的完整信息回复
        return await self._generate_normal_response(original_message, understanding, execution_result, context)

    def _build_simple_ack_response(self, understanding: Dict[str, Any], execution_result: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> str:
        """简单确认类回复（无需再次调用 LLM）。"""
        actions = execution_result.get('actions_taken') or []
        ok = any((a.get('action') == 'store' and isinstance(a.get('result'), dict) and a['result'].get('success')) for a in actions)
        intent = understanding.get('intent') or ''
        entities = understanding.get('entities') or {}
        key_bits: List[str] = []
        # 提取一些常见字段形成简短回显
        for k in ['amount', 'occurred_at', 'category', 'person', 'value', 'unit', 'item']:
            v = entities.get(k)
            if v is not None:
                key_bits.append(f"{k}={v}")
        echo = ("，".join(key_bits)) if key_bits else ""
        prefix = "已记录" if ok else "已处理"
        if intent:
            text = f"{prefix}（{intent}）"
        else:
            text = prefix
        if echo:
            text += f"：{echo}"
        return text
    
    async def _generate_clarification_response(self, original_message: str, understanding: Dict[str, Any], context: Dict[str, Any] = None) -> str:
        """
        生成澄清询问的回复
        """
        missing_fields = understanding.get('missing_fields', [])
        clarification_questions = understanding.get('clarification_questions', [])
        
        # 构建渠道特定的提示
        channel_hint = ""
        if context and context.get('channel') == 'threema':
            channel_hint = "\n注意：通过Threema回复，保持简洁友好。"
        
        # 获取回复生成指导（澄清专用与通用）
        response_guide = prompt_manager.get_response_prompt() or ''
        # 若定义了专门的澄清块，附加进系统提示
        clar_block = ''
        try:
            clar_block = prompt_manager.prompts.get(prompt_manager.current_version, {}).get('response_clarification', '')
        except Exception:
            clar_block = ''
        
        # 使用动态 task prompt
        task_params = {
            'channel_hint': channel_hint,
            'missing_fields': ', '.join(missing_fields),
            'clarification_questions': ', '.join(clarification_questions)
        }
        task_prompt = prompt_manager.get_clarification_task_prompt(**task_params)
        
        # 构建系统提示（使用动态工具信息）
        base_system_prompt = await prompt_manager.get_system_prompt_with_tools()
        system_prompt = base_system_prompt + ("\n" + clar_block if clar_block else "") + f"\n\n{response_guide if response_guide else ''}\n\n{task_prompt}"
        
        # 准备详细的上下文信息
        detailed_context = {
            "用户消息": original_message,
            "理解结果": understanding,
            "缺少信息": missing_fields,
            "建议询问": clarification_questions
        }
        
        # 使用动态用户提示
        user_params = {
            'detailed_context': json.dumps(detailed_context, ensure_ascii=False, indent=2)
        }
        prompt = prompt_manager.get_clarification_user_prompt(**user_params)
        
        return await self.llm.chat_text(
            system_prompt=system_prompt,
            user_prompt=prompt,
            temperature=0.5,
            max_tokens=200,
        )
    
    async def _generate_normal_response(self, original_message: str, understanding: Dict[str, Any], execution_result: Dict[str, Any], context: Dict[str, Any] = None) -> str:
        """
        生成正常的回复（信息完整时）
        """
        # 构建执行结果的详细描述
        actions_summary = []
        search_results = []
        aggregation_results = {}
        
        for action in execution_result.get('actions_taken', []):
            action_type = action['action']
            result = action['result']
            
            if action_type == 'store' and result.get('success'):
                actions_summary.append("✓ 已记录")
            elif action_type == 'schedule_reminder' and result.get('success'):
                actions_summary.append("✓ 已设置提醒")
            elif action_type == 'search' and isinstance(result, list):
                search_results = result
            elif action_type == 'aggregate' and 'result' in result:
                aggregation_results[result.get('operation', 'sum')] = result['result']
        
        # 构建渠道特定的提示
        channel_hint = ""
        if context and context.get('channel') == 'threema':
            channel_hint = "\n注意：通过Threema回复，保持简洁友好，使用表情符号增加亲和力。"
        
        # 获取回复生成指导（正常回复）
        response_guide = prompt_manager.get_response_prompt() or ''
        normal_block = ''
        try:
            normal_block = prompt_manager.prompts.get(prompt_manager.current_version, {}).get('response_normal', '')
        except Exception:
            normal_block = ''
        
        # 使用动态 task prompt
        task_params = {
            'channel_hint': channel_hint,
            'actions_summary': ', '.join(actions_summary) if actions_summary else '无操作'
        }
        task_prompt = prompt_manager.get_normal_task_prompt(**task_params)
        
        # 构建系统提示（使用动态工具信息）
        base_system_prompt = await prompt_manager.get_system_prompt_with_tools()
        system_prompt = base_system_prompt + ("\n" + normal_block if normal_block else "") + f"\n\n{response_guide if response_guide else ''}\n\n{task_prompt}"
        
        # 准备详细的上下文信息
        detailed_context = {
            "用户消息": original_message,
            "理解结果": understanding,
            "执行情况": actions_summary,
            "查询结果数量": len(search_results) if search_results else 0,
            "统计结果": aggregation_results
        }
        
        # 如果有搜索结果，添加摘要
        if search_results:
            detailed_context["最近记录示例"] = [
                {"内容": r.get('content', ''), "金额": r.get('amount')} 
                for r in search_results[:3]
            ]
        
        # 使用动态用户提示
        user_params = {
            'detailed_context': json.dumps(detailed_context, ensure_ascii=False, indent=2)
        }
        prompt = prompt_manager.get_normal_user_prompt(**user_params)
        
        generated_response = await self.llm.chat_text(
            system_prompt=system_prompt,
            user_prompt=prompt,
            temperature=0.7,
            max_tokens=500,
        )
        
        # 如果存在可绘制的聚合分组，渲染图表并追加链接（M2 回退方案）
        chart_url: Optional[str] = None
        try:
            for action in execution_result.get('actions_taken', []):
                if action.get('action') == 'aggregate' and isinstance(action.get('result'), dict):
                    groups = action['result'].get('groups')
                    if isinstance(groups, list) and groups:
                        x_labels: List[str] = []
                        y_values: List[float] = []
                        for g in groups:
                            grp = g.get('group') or {}
                            label = grp.get('period') or grp.get('ai_group') or ''
                            if isinstance(label, str):
                                x_labels.append(label)
                            else:
                                x_labels.append(str(label))
                            y_values.append(float(g.get('result') or 0))
                        render_res = await self._call_mcp_tool('render_chart', type='line', title='统计趋势', x=x_labels, series=[{"name": "value", "y": y_values}])
                        path = render_res.get('path') if isinstance(render_res, dict) else None
                        if path:
                            chart_url = make_signed_url(path)
                            break
        except Exception:
            pass
        
        # 后处理：确保回复不会太长
        if len(generated_response) > 500 and context and context.get('channel') == 'threema':
            # 对于Threema，截断过长的消息
            generated_response = generated_response[:497] + "..."
        # 追加图表链接
        if chart_url:
            generated_response += f"\n图表：{chart_url}"
        
        return generated_response

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
        """
        调用MCP工具 - 使用真实客户端或回退到模拟
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
                # 使用httpx进行HTTP调用（复用客户端）
                if self._http_client is None:
                    self._http_client = httpx.AsyncClient()
                response = await self._http_client.post(
                        f"{self.mcp_url}/tool/{tool_name}",
                        json=kwargs,
                        timeout=10.0
                    )
                http_status = response.status_code
                response.raise_for_status() # 检查HTTP状态码
                result_json = response.json()
            except httpx.RequestError as e:
                logger.error(f"HTTP request to MCP tool failed: {e}")
                # 回退到模拟模式
        
        # 模拟模式（用于开发和测试）或 HTTP 返回失败时的兜底
        if result_json is None:
            if tool_name == 'store':
                result_json = {"success": True, "id": f"mock-{datetime.now().timestamp()}"}
            elif tool_name == 'search':
                # 模拟一些搜索结果
                if "本月" in str(kwargs.get('query', '')):
                    result_json = [
                        {"content": "买菜花了50元", "amount": 50, "occurred_at": datetime.now().isoformat()},
                        {"content": "打车花了30元", "amount": 30, "occurred_at": datetime.now().isoformat()}
                    ]
                else:
                    result_json = []
            elif tool_name == 'aggregate':
                # 模拟聚合结果
                if kwargs.get('operation') == 'sum':
                    result_json = {"operation": "sum", "field": "amount", "result": 523.5}
                else:
                    result_json = {"result": 0}
            elif tool_name == 'get_pending_reminders':
                # 模拟待发送提醒
                result_json = []
            else:
                result_json = {"success": True}

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

    def _should_semantic_search(self, content: str) -> bool:
        """启发式：仅在疑似查询/统计/回顾类或较复杂文本时启用语义检索。"""
        if not content:
            return False
        text = str(content)
        # 问句或信息检索词
        query_markers = ["?", "？", "查询", "查", "查看", "看看", "统计", "多少", "总共", "合计", "历史", "最近", "以前", "上次", "对比", "趋势"]
        if any(m in text for m in query_markers):
            return True
        # 文本较长时也启用（需要更多上下文理解）
        return len(text) >= 40
    
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