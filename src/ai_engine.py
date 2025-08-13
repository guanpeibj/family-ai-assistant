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

# 家庭AI助手的系统提示词
FAMILY_AI_SYSTEM_PROMPT = """
你是一个贴心的家庭AI助手，专门服务于一个有3个孩子的家庭。

你的核心能力：
1. 记账管理：识别并记录家庭收支，提供统计分析和预算建议
2. 健康追踪：记录家人健康数据（身高、体重、疫苗等），跟踪变化趋势
3. 杂事提醒：管理日常事务，及时提醒重要事项

回复原则：
- 温馨友好，像家人般关怀
- 简洁实用，不说废话
- 主动提供有价值的统计和建议
- 记住这是一个有3个孩子的家庭，关注育儿相关需求

信息理解指南：
- "今天/昨天/上周"等时间表达要转换为具体日期
- 识别家庭成员：儿子、女儿（大女儿、二女儿）、妻子、我/老公
- 支出自动分类：餐饮、购物、交通、医疗、教育、日用品等
- 如果提到"更新"或"改为"，要覆盖之前的记录

你有以下工具可以使用：
- store: 存储任何重要信息（支出、收入、健康数据、杂事等）
- search: 查找历史记录
- aggregate: 统计分析数据（求和、计数、平均值等）
- schedule_reminder: 设置提醒
- get_pending_reminders: 查看待发送提醒
- mark_reminder_sent: 标记提醒已发送
"""


class AIEngine:
    def __init__(self):
        # 统一 LLM 客户端（可按配置切换 OpenAI 兼容/Anthropic 等）
        self.llm = LLMClient()
        self.mcp_client = None
        self.mcp_url = os.getenv('MCP_SERVER_URL', 'http://faa-mcp:8000')
        
    async def initialize_mcp(self):
        """初始化MCP客户端连接"""
        try:
            # 暂时使用HTTP调用方式，而不是stdio
            # 这样更简单且适合容器化部署
            logger.info(f"Connecting to MCP server at {self.mcp_url}")
            
            # 测试连接
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.mcp_url}/health", timeout=5.0)
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
        # HTTP客户端无需特殊关闭
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
            content_preview=content[:200]
        )

        try:
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
            # 第一步：理解用户意图和提取信息
            understanding = await self._understand_message(content, user_id, context, trace_id=trace_id)
            
            # 第二步：执行必要的操作
            result = await self._execute_actions(understanding, user_id, context=context, trace_id=trace_id)
            
            # 第三步：生成回复
            response = await self._generate_response(content, understanding, result, context)

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

            # 触发会话摘要（异步短路，不阻塞主流程）
            try:
                await self._maybe_summarize_thread(user_id=user_id, thread_id=thread_id, trace_id=trace_id)
            except Exception as e:
                logger.warning("thread.summarize.skip", trace_id=trace_id, error=str(e))

            # 落盘交互轨迹，便于排障
            try:
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
                )
            except Exception as e:
                logger.error("interaction.persist.failed", trace_id=trace_id, error=str(e))
            
            return response
            
        except Exception as e:
            logger.error("message.process.error", trace_id=trace_id, error=str(e))
            return "抱歉，处理您的消息时出现了错误。"
    
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
        # 上下文构建：近期对话窗口 + 语义检索 + 摘要（改为分块配额与重排去重）
        thread_id = (context or {}).get('thread_id') if context else None
        channel = (context or {}).get('channel') if context else None
        # 共享线程策略：当上下文指示 shared_thread/conversation_scope=shared 时启用
        shared_thread = False
        if context:
            if context.get('shared_thread') is True:
                shared_thread = True
            if context.get('conversation_scope') == 'shared':
                shared_thread = True
        recent_memories = await self._get_recent_memories(
            user_id,
            limit=10,
            thread_id=thread_id,
            shared_thread=shared_thread,
            channel=channel
        )
        semantic_related = await self._semantic_search(
            user_id,
            query=content,
            top_k=5,
            thread_id=thread_id,
            shared_thread=shared_thread,
            channel=channel
        )
        thread_summaries = await self._get_recent_thread_summaries(user_id, thread_id, limit=1, shared_thread=shared_thread, channel=channel)
        
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
                context_preview=history_context[:500]
            )
        except Exception:
            pass
        
        # 获取当前时间用于时间理解
        current_time = datetime.now()
        
        # 使用prompt管理器获取理解指导
        understanding_guide = prompt_manager.get_understanding_prompt()
        
        prompt = f"""
        分析用户消息并提取所有相关信息，特别注意信息完整性检查。
        
        当前时间：{current_time.isoformat()}
        用户消息：{content}
        {context_info}
        {history_context}
        
        {understanding_guide if understanding_guide else ''}
        
        请分析并返回JSON格式的理解结果，包括但不限于：
        1. intent: 用户意图（record_expense/record_income/record_health/query/set_reminder/update_info/general_chat/clarification_response等）
        2. entities: 提取的实体信息
        3. need_action: 是否需要执行动作（如果信息不完整，应该为false）
        4. need_clarification: 是否需要询问更多信息（最重要！）
        5. missing_fields: 缺少的关键信息字段列表
        6. clarification_questions: 具体的询问问题列表
        7. suggested_actions: 建议的动作列表
        8. original_content: 原始消息内容（用于存储）
        9. context_related: 是否与历史上下文相关
        
        **信息完整性检查规则**：
        - 记账必需：金额、用途、受益人（如涉及孩子）
        - 提醒必需：内容、时间、对象（如涉及孩子）
        - 健康记录必需：家庭成员、指标、数值
        - 信息更新必需：更新目标、新信息
        
        时间理解规则：
        - "今天" = {current_time.date()}
        - "昨天" = {(current_time - timedelta(days=1)).date()}
        - "前天" = {(current_time - timedelta(days=2)).date()}
        - "上周X" = 计算具体日期
        - "这个月" = {current_time.strftime('%Y-%m')}
        - "上个月" = 计算具体月份
        
        财务相关提取：
        - amount: 金额（数字）
        - type: expense（支出）/income（收入）
        - category: 自动分类（餐饮/购物/交通/医疗/教育/育儿用品/日用品/娱乐/其他）
        - description: 具体描述
        - person: 如果涉及特定家庭成员
        
        健康相关提取：
        - person: 家庭成员（儿子/大女儿/二女儿/妻子/我）
        - metric: 指标（身高/体重/体温/疫苗/症状等）
        - value: 数值
        - unit: 单位
        
        提醒相关提取：
        - remind_content: 提醒内容
        - remind_time: 提醒时间（转换为ISO格式）
        - repeat: 重复模式（daily/weekly/monthly/once）
        
        信息更新识别：
        - 如果包含"改为"、"改成"、"现在是"、"更新为"等词汇，设置 update_existing: true
        - 提取要更新的信息类型和新值
        
        基于历史上下文的理解：
        - 如果消息中提到"刚才"、"上面"、"之前"等，要关联历史记录
        - 识别是否是对之前记录的补充或修正
        
        如果用户只是回答了之前的询问，识别为 clarification_response 意图。
        
        请提取所有你认为重要的信息，occurred_at字段必须是具体的ISO格式时间。
        """
        
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
            understanding = await self.llm.chat_json(
                system_prompt=prompt_manager.get_system_prompt(),
                user_prompt=prompt,
                temperature=0.3,
                max_tokens=1200,
            )
        except Exception as e:
            # 某些兼容端点可能不支持 JSON 强约束，退化为文本并尝试解析
            logger.warning(f"chat_json failed, fallback to text: {e}")
            raw = await self.llm.chat_text(
                system_prompt=prompt_manager.get_system_prompt(),
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
        system_prompt = prompt_manager.get_system_prompt()
        planning_guide = prompt_manager.get_tool_planning_prompt()
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
    
    async def _execute_actions(self, understanding: Dict[str, Any], user_id: str, *, context: Optional[Dict[str, Any]] = None, trace_id: str) -> Dict[str, Any]:
        """
        根据理解结果执行动作 - 增强版，支持信息完整性检查
        """
        result = {"actions_taken": []}
        
        # 🚨 重要：如果需要澄清信息，先存一条对话记忆用于多轮上下文（不执行业务动作）
        if understanding.get('need_clarification'):
            try:
                entities = understanding.get('entities', {})
                ai_data = {
                    'intent': 'clarification_pending',
                    'entities': entities,
                    'need_clarification': True,
                    'timestamp': datetime.now().isoformat(),
                }
                # 确保有 occurred_at，便于时间序排序
                if not ai_data.get('occurred_at'):
                    ai_data['occurred_at'] = datetime.now().isoformat()
                # 线程/追踪信息
                if context and context.get('thread_id'):
                    ai_data['thread_id'] = context.get('thread_id')
                ai_data['trace_id'] = trace_id
                # 生成嵌入
                _emb = None
                try:
                    _embs = await self.llm.embed([understanding.get('original_content', '')])
                    _emb = _embs[0] if _embs else None
                except Exception:
                    _emb = None
                store_result = await self._call_mcp_tool(
                    'store',
                    content=understanding.get('original_content', ''),
                    ai_data=ai_data,
                    user_id=user_id,
                    embedding=_emb
                )
                result['actions_taken'].append({'action': 'store', 'result': store_result})
            except Exception as e:
                logger.error(f"Failed to store clarification context: {e}")
            logger.info("Information incomplete, stored context and waiting for clarification")
            return result
        
        # 只有信息完整时才尝试执行动作（由 LLM 决定是否需要行动）
        if not understanding.get('need_action'):
            return result
        
        # 先让 LLM 产出通用工具计划
        plan = await self._build_tool_plan(understanding, user_id, context=context)
        steps = plan.get('steps') or []

        # 若计划为空，作为兜底不执行具体动作，仅返回
        if not steps:
            return result

        last_store_id: Optional[str] = None
        allowed_tools = {"store", "search", "aggregate", "schedule_reminder", "get_pending_reminders", "mark_reminder_sent"}

        for step in steps:
            if not isinstance(step, dict):
                continue
            tool = step.get('tool')
            args = step.get('args') or {}
            if tool not in allowed_tools:
                continue

            # 注入通用参数
            if tool in {"store", "search", "aggregate", "get_pending_reminders"}:
                args.setdefault('user_id', user_id)

            # 解析占位符依赖
            if tool == 'schedule_reminder':
                mem_id = args.get('memory_id')
                if mem_id == '$LAST_STORE_ID' and last_store_id:
                    args['memory_id'] = last_store_id
                if args.get('from_last_store') and last_store_id:
                    args['memory_id'] = last_store_id
                    args.pop('from_last_store', None)

            # 生成嵌入：store.content 或 search.query
            try:
                if tool == 'store':
                    text_for_embed = args.get('content') or understanding.get('original_content', '')
                    if text_for_embed:
                        embs = await self.llm.embed([text_for_embed])
                        args.setdefault('embedding', (embs[0] if embs else None))
                    # 最低限保障：ai_data 合并 entities 与 occurred_at
                    ai_data = args.get('ai_data') or {}
                    entities = understanding.get('entities', {})
                    merged = {**entities, **ai_data}
                    if not merged.get('occurred_at'):
                        merged['occurred_at'] = datetime.now().isoformat()
                    if context and context.get('thread_id'):
                        merged.setdefault('thread_id', context.get('thread_id'))
                    merged.setdefault('trace_id', trace_id)
                    # M1：将附件元数据纳入存储（便于后续检索与追溯）
                    if context and isinstance(context.get('attachments'), list):
                        merged.setdefault('attachments', context.get('attachments'))
                    args['ai_data'] = merged
                elif tool == 'search':
                    q = args.get('query')
                    if q and not args.get('query_embedding'):
                        embs = await self.llm.embed([q])
                        args['query_embedding'] = embs[0] if embs else None
                elif tool == 'aggregate':
                    pass
            except Exception:
                # 忽略嵌入失败，走无嵌入路径
                pass

            # 执行工具
            exec_result = await self._call_mcp_tool(tool, **args)
            result['actions_taken'].append({'action': tool, 'result': exec_result})

            # 记录 last_store_id 供后续依赖
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
        user_ai = {
            **common,
            'role': 'user',
            'intent': understanding.get('intent'),
            'entities': understanding.get('entities', {})
        }
        assistant_ai = {
            **common,
            'role': 'assistant',
            'intent': understanding.get('intent'),
            'entities': understanding.get('entities', {})
        }
        # 批量生成两段文本的嵌入
        _user_emb = None
        _assistant_emb = None
        try:
            embs = await self.llm.embed([user_message, assistant_message])
            if embs and len(embs) >= 2:
                _user_emb, _assistant_emb = embs[0], embs[1]
        except Exception:
            _user_emb = None
            _assistant_emb = None
        await self._call_mcp_tool('store', content=user_message, ai_data=user_ai, user_id=user_id, embedding=_user_emb)
        await self._call_mcp_tool('store', content=assistant_message, ai_data=assistant_ai, user_id=user_id, embedding=_assistant_emb)

    async def _maybe_summarize_thread(self, *, user_id: str, thread_id: Optional[str], trace_id: str) -> None:
        """当同一线程回合数过多时，生成摘要并存储。"""
        if not thread_id:
            return
        # 拉取最近若干条，筛选当线程的 chat_turn
        recent = await self._call_mcp_tool('search', query='', user_id=user_id, filters={'limit': 50})
        turns = [r for r in recent if isinstance(r, dict) and isinstance(r.get('ai_understanding'), dict) and r['ai_understanding'].get('type') == 'chat_turn' and r['ai_understanding'].get('thread_id') == thread_id]
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
                tool_calls_json=None,
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
        
        # 获取回复生成指导
        response_guide = prompt_manager.get_response_prompt()
        
        # 构建系统提示
        system_prompt = prompt_manager.get_system_prompt() + f"""

当前任务：用户提供的信息不完整，需要询问缺少的信息。

{response_guide if response_guide else ''}

询问要求：
1. 确认已理解的部分信息
2. 礼貌地询问缺少的信息
3. 提供选择选项（如适用）
4. 使用温和、专业的语气
5. 一次只询问一个最重要的问题
{channel_hint}

缺少的信息：{', '.join(missing_fields)}
建议的询问：{', '.join(clarification_questions)}
"""
        
        # 准备详细的上下文信息
        detailed_context = {
            "用户消息": original_message,
            "理解结果": understanding,
            "缺少信息": missing_fields,
            "建议询问": clarification_questions
        }
        
        prompt = f"""
用户提供的信息不完整，需要询问缺少的信息。

{json.dumps(detailed_context, ensure_ascii=False, indent=2)}

请生成一个温和、专业的询问回复，遵循以下格式：
1. 确认已理解部分："好的，我理解您要..."
2. 礼貌询问："请问您..."
3. 提供选择（如适用）："是...还是...？"

记住要像家人一样温暖，但又保持专业的精确度。
"""
        
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
        
        # 获取回复生成指导
        response_guide = prompt_manager.get_response_prompt()
        
        # 构建系统提示
        system_prompt = prompt_manager.get_system_prompt() + f"""

当前任务：基于用户消息和执行结果，生成一个有价值的回复。

{response_guide if response_guide else ''}

回复要求：
1. 确认已完成的操作（{', '.join(actions_summary) if actions_summary else '无操作'}）
2. 如果记录了支出/收入，自动提供本月/今日累计
3. 如果是查询，用简洁的方式展示结果
4. 根据家庭历史数据，提供个性化建议
5. 如果发现异常模式（如超支），温和提醒
6. 使用温暖、像家人般的语气
{channel_hint}

记住这是一个有3个孩子的家庭，可能关注：
- 育儿支出和健康
- 家庭预算管理
- 日常生活便利性
"""
        
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
        
        prompt = f"""
基于以下信息生成回复：

{json.dumps(detailed_context, ensure_ascii=False, indent=2)}

请生成一个符合要求的回复。如果是财务相关，考虑：
- 本月总支出是否异常？
- 某类支出是否过高？
- 是否需要预算提醒？

如果是健康相关，考虑：
- 成长趋势是否正常？
- 是否到了疫苗接种时间？
- 是否需要健康建议？

如果是提醒相关：
- 确认提醒的具体时间
- 如果是重复提醒，说明频率

记住要像关心家人一样，给出简洁、实用的建议。
"""
        
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
        logger.info(f"Calling MCP tool: {tool_name} with args: {kwargs}")
        
        # 如果有真实的MCP客户端
        if self.mcp_client:
            try:
                # 使用httpx进行HTTP调用
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.mcp_url}/tool/{tool_name}",
                        json=kwargs,
                        timeout=10.0
                    )
                    response.raise_for_status() # 检查HTTP状态码
                    return response.json()
            except httpx.RequestError as e:
                logger.error(f"HTTP request to MCP tool failed: {e}")
                # 回退到模拟模式
        
        # 模拟模式（用于开发和测试）
        if tool_name == 'store':
            return {"success": True, "id": f"mock-{datetime.now().timestamp()}"}
        elif tool_name == 'search':
            # 模拟一些搜索结果
            if "本月" in str(kwargs.get('query', '')):
                return [
                    {"content": "买菜花了50元", "amount": 50, "occurred_at": datetime.now().isoformat()},
                    {"content": "打车花了30元", "amount": 30, "occurred_at": datetime.now().isoformat()}
                ]
            return []
        elif tool_name == 'aggregate':
            # 模拟聚合结果
            if kwargs.get('operation') == 'sum':
                return {"operation": "sum", "field": "amount", "result": 523.5}
            return {"result": 0}
        elif tool_name == 'get_pending_reminders':
            # 模拟待发送提醒
            return []
        else:
            return {"success": True}
    
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