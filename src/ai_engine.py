"""
AI Engine v3 - Unified Plan-Act Loop
====================================

该模块实现 FAA 核心的单循环智能体编排器，围绕以下目标展开：

核心原则
--------
1. **AI 主导**：所有业务判断、工具规划、补救策略均交由 LLM 决策，工程层只负责执行。
2. **工程极简**：提供统一的数据管道、可观测日志与安全兜底，不在代码中写死业务流程。
3. **可扩展**：上下文裁剪、工具调用、最终回复均以契约驱动，可随 prompt / 模型演进而迭代。

主要组件
--------
- `AgentActionModel` / `AgentFinalResponseModel`：LLM 输入输出契约。
- `AgentState`：保存单轮对话的所有步骤、观测、上下文快照。
- `ContextManager`：负责编排记忆、家庭信息与动态上下文的预算与获取。
- `AIEngineV2`：总控协调器，驱动 Plan→Act→Observe 循环、处理工具结果并生成最终回复。
"""
from __future__ import annotations

import asyncio
import calendar
import json
import os
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import httpx
import structlog
from pydantic import BaseModel, Field, ValidationError

from .core.ab_testing import ExperimentResult, ab_testing_manager, get_experiment_version
from .core.config import settings
from .core.context_policy import ContextPolicy, DynamicKeyPolicy
from .core.exceptions import (
    AIEngineError,
    ContextResolutionError,
    LLMError,
    MCPToolError,
    ToolExecutionError,
    create_error_context,
    get_user_friendly_message,
)
from .core.llm_client import LLMClient
from .core.prompt_manager import prompt_manager
from .services.household_service import household_service
from .services.media_service import make_signed_url

logger = structlog.get_logger(__name__)

# -----------------------------------------------------------------------------
# Agent 数据结构
# -----------------------------------------------------------------------------


class AgentActionModel(BaseModel):
    """
    LLM 输出的一次行动契约。

    字段含义：
    - `thought`：本轮执行前的思考过程，便于调试和复盘。
    - `action`：要采取的动作类型（call_tool / fetch_context / respond / clarify / finalize 等）。
    - `tool`：当 action 为 call_tool 时指定 MCP 工具名称。
    - `input`：动作参数，允许是字符串 / JSON / 列表，稍后通过 `normalized_input` 统一成 dict。
    - `expected_outcome`：对行动结果的预期描述，帮助后续回合进行验证。
    - `stop`：布尔值，指示本次行动后是否立即退出主循环。
    - `metadata`：扩展字段，预留给 prompt 实验或 A/B 测试时使用。
    """

    thought: Optional[str] = Field(default=None, description="行动前的思考")
    action: str = Field(..., description="行动类型：call_tool/fetch_context/respond/clarify/no_op")
    tool: Optional[str] = Field(default=None, description="当调用工具时的工具名称")
    input: Any = Field(default_factory=dict, description="行动输入，可为字符串或对象")
    expected_outcome: Optional[str] = Field(default=None, description="预期目标")
    stop: bool = Field(default=False, description="是否立即终止循环")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")

    def normalized_input(self) -> Dict[str, Any]:
        """
        将 input 规范化为字典，方便后续处理。

        - prompt 可能输出字符串 / 列表 / 字典，本方法统一转换为 dict。
        - 如果是字符串，优先尝试解析 JSON；解析失败则包裹在 `{"value": 原串}`。
        - 如果是列表，转换为 `{"items": [...]}`，便于兼容多请求的场景。
        """
        if isinstance(self.input, dict):
            return self.input
        if isinstance(self.input, list):
            return {"items": self.input}
        if isinstance(self.input, str) and self.input.strip():
            try:
                parsed = json.loads(self.input)
                if isinstance(parsed, dict):
                    return parsed
                return {"value": parsed}
            except Exception:
                return {"value": self.input}
        return {}


class AgentFinalResponseModel(BaseModel):
    """
    LLM 最终输出契约。

    字段含义：
    - `reply`：返回给用户的文本回复。
    - `memory_record`：用于写入长期记忆的结构化数据（intent、entities、should_store 等）。
    - `followups`：建议的后续追问或提醒列表。
    - `status`：整体状态，便于上层统计（success / warning / error）。
    """

    reply: str = Field(..., description="返回给用户的文本")
    memory_record: Dict[str, Any] = Field(default_factory=dict, description="用于记忆存储的结构化数据")
    followups: List[str] = Field(default_factory=list, description="推荐的后续问题")
    status: str = Field(default="success", description="最终状态标记")


class AgentState:
    """
    保存单次对话生命周期内所有状态信息。

    功能概述：
    - 维护会话级元信息（user/thread/channel/trace）。
    - 累积每轮的行动记录与 observation，供后续提示词引用。
    - 管理上下文预算轮次（`context_round`），保证逐步扩容而非一次性灌入。
    - 构建 LLM 所需的结构化 payload（规划、总结阶段）。
    """

    def __init__(self, *, user_id: str, thread_id: Optional[str], channel: Optional[str], trace_id: str, user_message: str) -> None:
        """初始化会话状态并记录基础元信息。"""
        # 中文注释：记录对话元信息，便于日志追踪和上下文生成
        self.user_id = user_id
        self.thread_id = thread_id
        self.channel = channel
        self.trace_id = trace_id
        self.original_user_message = user_message
        self.created_at = time.monotonic()

        # 中文注释：记录每一步的思考、行动与观察摘要
        self.steps: List[Dict[str, Any]] = []
        self.observation_summaries: List[str] = []
        self.latest_observation: Optional[Dict[str, Any]] = None
        # 中文注释：raw_observations 保存完整的工具/上下文结果，LLM 可按需引用
        self.raw_observations: Dict[int, Dict[str, Any]] = {}

        # 中文注释：raw_context 保存真实数据；context_round 控制定额预算
        self.raw_context: Dict[str, Any] = {}
        self.context_round: int = 0
        self.metadata: Dict[str, Any] = {}

    @property
    def step_count(self) -> int:
        """返回已记录的行动次数。"""
        return len(self.steps)

    def add_step(self, action: AgentActionModel, observation: Dict[str, Any]) -> None:
        """
        记录单步行动与观测结果。

        - 会把 action/observation 的关键信息压缩后追加到 steps。
        - 通过 `_shrink_data` 控制 observation 中 data 的体积，避免提示词爆炸。
        - 维护 `observation_summaries` 供 LLM 查看最近摘要。
        """
        step_index = self.step_count + 1
        summary = observation.get("summary")
        observation_entry: Dict[str, Any] = {
            "success": observation.get("success"),
            "summary": summary,
            "type": observation.get("type"),
            "error": observation.get("error"),
        }
        if "data" in observation:
            data_preview = self._shrink_data(observation.get("data"))
            observation_entry["data_preview"] = data_preview
            # 中文注释：兼容旧版提示词，保留 data 字段但仅提供截断内容
            observation_entry["data"] = data_preview
        if "update_context" in observation and isinstance(observation["update_context"], dict):
            observation_entry["update_context_keys"] = list(observation["update_context"].keys())
        if "terminate" in observation:
            observation_entry["terminate"] = observation.get("terminate")
        if "ref" in observation:
            observation_entry["ref"] = observation.get("ref")

        observation.setdefault("ref", f"observation:{step_index}")

        self.steps.append(
            {
                "index": step_index,
                "thought": action.thought,
                "action": action.action,
                "tool": action.tool,
                "input": action.normalized_input(),
                "expected_outcome": action.expected_outcome,
                "stop": action.stop,
                "observation": observation_entry,
            }
        )
        if isinstance(summary, str) and summary:
            self.observation_summaries.append(summary)
        self.latest_observation = observation
        self.raw_observations[step_index] = observation

    def get_observation_by_ref(self, ref: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        根据 ref 获取完整的 observation 数据。

        中文注释：ref 形如 `observation:3`，供 LLM 在需要时通过 fetch_context 拿到全量信息。
        """
        if not ref or not isinstance(ref, str):
            return None
        if not ref.startswith("observation:"):
            return None
        try:
            index = int(ref.split(":", 1)[1])
        except (ValueError, IndexError):
            return None
        return self.raw_observations.get(index)

    def _shrink_data(self, data: Any, *, depth: int = 0) -> Any:
        """
        对工具返回的数据进行安全裁剪。

        递归地限制列表长度、字典键数量以及字符串长度，确保写入步骤日志时足够精简。
        `depth` 参数用于递归时逐级收紧裁剪阈值。
        """
        if data is None:
            return None
        if isinstance(data, str):
            return data if len(data) <= 200 else f"{data[:200]}..."
        if isinstance(data, list):
            limit = 3 if depth == 0 else 2
            return [self._shrink_data(item, depth=depth + 1) for item in data[:limit]]
        if isinstance(data, dict):
            limit = 5 if depth == 0 else 3
            trimmed: Dict[str, Any] = {}
            for idx, (key, value) in enumerate(data.items()):
                if idx >= limit:
                    trimmed["__more__"] = f"... trimmed {len(data) - limit} keys"
                    break
                trimmed[key] = self._shrink_data(value, depth=depth + 1)
            return trimmed
        return data

    def build_planning_payload(self, *, context_view: Dict[str, Any], max_turns: int) -> Dict[str, Any]:
        """
        生成供 LLM 规划用的 JSON 载荷。

        包含：
        - 用户与渠道信息。
        - 最近几轮动作与 observation 摘要，帮助模型衔接上下文。
        - 当前的上下文视图与剩余回合数。
        """
        recent_steps = self.steps[-3:]
        recent_observations = self.observation_summaries[-3:]
        remaining = max(0, max_turns - self.step_count)
        return {
            "user": {
                "id": self.user_id,
                "thread_id": self.thread_id,
                "channel": self.channel,
            },
            "conversation": {
                "original_user_message": self.original_user_message,
                "recent_steps": recent_steps,
                "recent_observations": recent_observations,
            },
            "context": context_view,
            "meta": {
                "remaining_turns": remaining,
                "trace_id": self.trace_id,
            },
        }

    def build_final_payload(self, *, context_view: Dict[str, Any], status: str, reason: Optional[str]) -> Dict[str, Any]:
        """
        生成最终总结阶段的 JSON 载荷。

        汇总所有步骤、上下文视图以及结束原因，供最终回复 prompt 使用。
        """
        return {
            "user": {
                "id": self.user_id,
                "thread_id": self.thread_id,
                "channel": self.channel,
            },
            "conversation": {
                "original_user_message": self.original_user_message,
                "steps": self.steps,
                "latest_observation": self.latest_observation,
            },
            "context": context_view,
            "status": status,
            "reason": reason,
        }


# -----------------------------------------------------------------------------
# 消息与上下文工具
# -----------------------------------------------------------------------------


class MessageProcessor:
    """
    负责在进入智能体前对用户消息进行预处理。

    主要工作：
    - 将语音转写、OCR、视觉摘要等附件衍生文本整合到主消息中。
    - 保留原始文本顺序，方便 LLM 获取完整语境。
    """

    @staticmethod
    def merge_attachment_texts(content: str, attachments: Optional[List[Dict[str, Any]]]) -> str:
        """
        合并附件文本。

        优先级：语音转写 (`transcription.text`) > OCR 文本 > 视觉摘要。
        当存在多个衍生文本时，会在正文后附加 `[附件提取]` 段落。
        """
        if not attachments:
            return content
        derived_texts: List[str] = []
        for att in attachments:
            if not isinstance(att, dict):
                continue
            text = None
            if isinstance(att.get("transcription"), dict):
                text = att["transcription"].get("text")
            if not text:
                text = att.get("ocr_text")
            if not text:
                text = att.get("vision_summary")
            if text:
                derived_texts.append(str(text))
        if not derived_texts:
            return content
        base = (content or "").strip()
        extra = "\n\n[附件提取]\n" + "\n".join(derived_texts)
        return f"{base}{extra}" if base else "\n".join(derived_texts)


class ContextManager:
    """
    统一管理智能体所需的上下文。

    负责：
    - 从记忆库与家庭服务拉取原始数据。
    - 根据预算裁剪上下文并生成给 LLM 的视图。
    - 按需执行语义/直接搜索，满足 LLM 的补充请求。
    """

    def __init__(self, ai_engine: "AIEngineV2") -> None:
        """记录引擎引用并装载上下文策略。"""
        self.ai_engine = ai_engine
        self.policy = ContextPolicy()
        self._reserved_context_keys = {"light_context", "household", "insights"}
        # 中文注释：缓存家庭信息，避免每轮重复访问服务
        self._household_cache: Dict[str, Any] = {}
        self._household_cache_expire: float = 0.0


    async def get_basic_context(
        self,
        user_id: str,
        thread_id: Optional[str],
        shared_thread: bool,
        channel: Optional[str],
    ) -> Dict[str, Any]:
        """
        拉取基础上下文。

        返回值：
        - `light_context`：最近对话片段，帮助 LLM 理解语境。
        - `household`：家庭成员结构与 family_scope，供 scope 判定与人称解析。
        """
        loop = asyncio.get_event_loop()
        start_time = loop.time()
        try:
            # 中文注释：并发获取轻量记忆、家庭信息与线程摘要
            memory_task = asyncio.create_task(
                self._get_recent_memories(
                    user_id=user_id,
                    limit=self.policy.light_context["limit"],
                    thread_id=thread_id,
                    shared_thread=shared_thread,
                    channel=channel,
                )
            )
            household_task = asyncio.create_task(self._get_household_context())
            thread_task = asyncio.create_task(self._get_thread_summary(user_id, thread_id))

            light_context, household_context, thread_summary = await asyncio.gather(
                memory_task,
                household_task,
                thread_task,
                return_exceptions=True,
            )

            if isinstance(light_context, Exception):
                logger.warning("context.memories.failed", error=str(light_context))
                light_context = []
            else:
                logger.info(
                    "context.memories.fetched",
                    duration_ms=int((loop.time() - start_time) * 1000),
                    count=len(light_context),
                )

            if isinstance(household_context, Exception):
                logger.warning("context.household.failed", error=str(household_context))
                household_context = {}

            if isinstance(thread_summary, Exception):
                logger.debug("context.thread_summary.unavailable", thread_id=thread_id, error=str(thread_summary))
                thread_summary = None
            elif thread_summary:
                logger.debug(
                    "context.thread_summary.attached",
                    thread_id=thread_id,
                    has_scratchpad=bool(thread_summary.get("thread_scratchpad")),
                )

            logger.info(
                "context.basic.ready",
                duration_ms=int((loop.time() - start_time) * 1000),
                user_id=user_id,
            )

            context_payload = {
                "light_context": light_context,
                "household": household_context,
            }
            if thread_summary:
                context_payload["thread_summary"] = thread_summary
            return context_payload
        except Exception as exc:
            logger.warning(
                "context.basic.failed",
                error=str(exc),
                duration_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
            )
            return {"light_context": [], "household": {}}

    async def _get_household_context(self) -> Dict[str, Any]:
        """
        获取家庭信息，带本地缓存。

        中文注释：家庭结构更新频率低，通过简单 TTL 缓存减少后端压力。
        """
        loop = asyncio.get_event_loop()
        now = loop.time()
        if self._household_cache and now < self._household_cache_expire:
            logger.debug(
                "context.household.cache_hit",
                ttl_ms=int((self._household_cache_expire - now) * 1000),
            )
            return self._household_cache

        start = now
        payload = await household_service.get_context()
        payload = payload or {}
        duration_ms = int((loop.time() - start) * 1000)
        self._household_cache = payload
        self._household_cache_expire = loop.time() + 60.0
        logger.info(
            "context.household.refresh",
            duration_ms=duration_ms,
            members=len(payload.get("members", [])),
        )
        return payload

    async def resolve_context_requests(
        self,
        context_requests: List[Dict[str, Any]],
        understanding: Dict[str, Any],
        user_id: str,
        thread_id: Optional[str],
        shared_thread: bool,
        channel: Optional[str],
        trace_id: str,
        existing_context: Optional[Dict[str, Any]] = None,
        agent_state: Optional[AgentState] = None,
    ) -> Dict[str, Any]:
        """
        根据 LLM 指令获取补充上下文。

        - 支持 recent_memories / semantic_search / direct_search / context_ref / observation_ref。
        - 若 `existing_context` 已包含目标 name，则直接复用。
        - 所有操作均带日志，方便回溯性能与命中率。
        """
        if not context_requests:
            return {}
        resolved: Dict[str, Any] = {}
        logger.info(
            "context.requests.start",
            trace_id=trace_id,
            count=len(context_requests),
            kinds=[req.get("kind") for req in context_requests if isinstance(req, dict)],
        )
        for req in context_requests:
            if not isinstance(req, dict):
                continue
            name = req.get("name")
            kind = req.get("kind")
            if not name or not kind:
                continue
            if existing_context and name in existing_context:
                logger.debug("context.requests.cache_hit", trace_id=trace_id, name=name)
                resolved[name] = existing_context[name]
                continue
            start = asyncio.get_event_loop().time()
            try:
                if kind == "recent_memories":
                    limit = int(req.get("limit", 6))
                    resolved[name] = await self._get_recent_memories(
                        user_id=user_id,
                        limit=limit,
                        thread_id=thread_id,
                        shared_thread=shared_thread,
                        channel=channel,
                    )
                elif kind == "semantic_search":
                    query = req.get("query") or understanding.get("original_content", "")
                    if not query:
                        resolved[name] = []
                    else:
                        top_k = int(req.get("limit", 5))
                        resolved[name] = await self._semantic_search(
                            user_id=user_id,
                            query=query,
                            top_k=top_k,
                            thread_id=thread_id,
                            shared_thread=shared_thread,
                            channel=channel,
                        )
                elif kind == "direct_search":
                    resolved[name] = await self._direct_search(
                        request=req,
                        user_id=user_id,
                        thread_id=thread_id,
                        shared_thread=shared_thread,
                        channel=channel,
                    )
                elif kind == "context_ref":
                    ref = req.get("ref") or req.get("target")
                    resolved[name] = self._resolve_context_ref(
                        ref=ref,
                        existing_context=existing_context,
                        agent_state=agent_state,
                    )
                elif kind == "observation_ref":
                    ref = req.get("ref")
                    payload = agent_state.get_observation_by_ref(ref) if agent_state else None
                    resolved[name] = payload or {}
                else:
                    logger.info("context.requests.unsupported", trace_id=trace_id, name=name, kind=kind)
                    resolved[name] = []
                logger.info(
                    "context.requests.done",
                    trace_id=trace_id,
                    name=name,
                    kind=kind,
                    duration_ms=int((asyncio.get_event_loop().time() - start) * 1000),
                )
            except Exception as exc:
                logger.warning(
                    "context.requests.failed",
                    trace_id=trace_id,
                    name=name,
                    error=str(exc),
                    duration_ms=int((asyncio.get_event_loop().time() - start) * 1000),
                )
                resolved[name] = []
        return resolved

    def _resolve_context_ref(
        self,
        *,
        ref: Optional[str],
        existing_context: Optional[Dict[str, Any]],
        agent_state: Optional[AgentState],
    ) -> Any:
        """
        根据 manifest ref 提供完整上下文数据。

        中文注释：ref 形如 `context:expense_category_config`，优先从已加载上下文中读取，
        若缓存未命中则回退到 AgentState 保存的原始原件。
        """
        if not ref or not isinstance(ref, str):
            return {}
        if ":" in ref:
            prefix, identifier = ref.split(":", 1)
        else:
            prefix, identifier = "context", ref
        if prefix in {"context", "dynamic"}:
            if existing_context and identifier in existing_context:
                return existing_context[identifier]
            if agent_state and identifier in agent_state.raw_context:
                return agent_state.raw_context[identifier]
            return {}
        if prefix == "observation":
            if agent_state:
                payload = agent_state.get_observation_by_ref(ref)
                return payload or {}
            return {}
        logger.debug("context.ref.unsupported", ref=ref)
        return {}

    def prepare_tool_context_update(
        self,
        *,
        tool_name: str,
        params: Dict[str, Any],
        result: Any,
    ) -> Dict[str, Any]:
        """
        将工具调用结果注入会话上下文。

        中文注释：对于关键查询（财务、健康等），使用 lossless 视图保留完整数据，
        避免模型基于截断内容进行推理。
        """
        if result is None:
            return {}
        if not isinstance(params, dict):
            params = {}
        timestamp = datetime.now(ZoneInfo(settings.DEFAULT_TIMEZONE)).isoformat()
        update: Dict[str, Any] = {}

        if tool_name == "search":
            filters = params.get("filters") or {}
            resource_type = filters.get("type")
            payload = {
                "fetched_at": timestamp,
                "query": params.get("query"),
                "filters": filters,
                "source_tool": tool_name,
                "data": result,
            }
            if resource_type:
                update[resource_type] = payload
            else:
                scope = filters.get("scope") or params.get("scope") or "general"
                query_text = (params.get("query") or "").strip() or "all"
                key = f"search::{scope}::{query_text}"
                update[key] = payload
            return update

        identifier = (
            params.get("name")
            or params.get("identifier")
            or params.get("id")
            or params.get("target")
            or params.get("key")
        )
        key = f"{tool_name}::{identifier}" if identifier else f"{tool_name}_result"
        update[key] = {
            "fetched_at": timestamp,
            "input": params,
            "source_tool": tool_name,
            "data": result,
        }
        return update

    def build_plan_view(self, raw_context: Dict[str, Any], planning_round: int) -> Dict[str, Any]:
        """中文注释：按照策略输出 LLM 可消费的上下文视图及 manifest。"""
        trimmed_light = self._trim_light_context(raw_context.get("light_context", []))
        household_summary, household_total = self._summarize_household(raw_context.get("household", {}))
        dynamic_summary, dynamic_manifest = self._summarize_dynamic(raw_context, planning_round)
        return {
            "light_context": trimmed_light,
            "household": household_summary,
            "dynamic": dynamic_summary,
            "manifest": {
                "light_context_total": len(raw_context.get("light_context", [])),
                "household_members_total": household_total,
                **dynamic_manifest,
            },
        }

    # ------------------------------------------------------------------
    # 内部工具方法（上下文裁剪）
    # ------------------------------------------------------------------

    def _trim_light_context(self, memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """根据策略裁剪轻量记忆。"""
        cfg = self.policy.light_context
        limit = cfg["limit"]
        char_limit = cfg["char_limit"]
        result: List[Dict[str, Any]] = []
        for item in (memories or [])[:limit]:
            preview = item.get("content", "")
            result.append(
                {
                    "content": self._safe_preview(preview, char_limit),
                    "time": item.get("time"),
                    "ai_understanding": item.get("ai_understanding", {}),
                    "speaker": item.get("speaker"),
                    "speaker_display": item.get("speaker_display"),
                }
            )
        return result

    def _summarize_household(self, household: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """压缩家庭成员信息并返回总成员数。"""
        cfg = self.policy.household
        members = household.get("members", []) or []
        summary: List[Dict[str, Any]] = []
        for member in members[: cfg["members_limit"]]:
            tags = list((member.get("profile") or {}).get("tags", []))
            summary.append(
                {
                    "member_key": member.get("member_key"),
                    "display_name": member.get("display_name"),
                    "relationship": member.get("relationship"),
                    "user_ids_count": len(member.get("user_ids", [])),
                    "tags": tags[: cfg["tag_limit"]],
                }
            )
        return {
            "members": summary,
            "family_scope_user_ids": household.get("family_scope", {}),
        }, len(members)

    def _summarize_dynamic(self, raw_context: Dict[str, Any], planning_round: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """根据 token 预算生成动态上下文视图。"""
        dynamic_summary: Dict[str, Any] = {}
        manifest_entries: List[Dict[str, Any]] = []
        available_keys_set: set[str] = set()

        for key in raw_context.keys():
            if key in self._reserved_context_keys:
                continue
            if key.startswith("_"):
                continue
            available_keys_set.add(key)

        for key in self.policy.known_dynamic_keys():
            if key in self._reserved_context_keys or key.startswith("_"):
                continue
            available_keys_set.add(key)

        ordered_keys = self.policy.sorted_dynamic_keys(list(available_keys_set))
        token_budget = self._dynamic_token_budget(planning_round)
        consumed_tokens = 0
        skipped_keys: List[str] = []

        for key in ordered_keys:
            policy = self.policy.get_dynamic_policy(key)
            value = raw_context.get(key)
            if policy.mode == "lossless":
                entry = self._build_lossless_entry(key, value, policy)
                dynamic_summary[key] = entry["view"]
                manifest_entries.append(entry["manifest"])
                continue

            if value is None:
                skipped_keys.append(key)
                manifest_entries.append(
                    {
                        "key": key,
                        "mode": policy.mode,
                        "skipped": True,
                        "reason": "value_not_loaded",
                    }
                )
                continue

            summarized = self._summarize_value(value, policy)
            estimated_tokens = ContextPolicy.estimate_tokens(summarized)
            if consumed_tokens + estimated_tokens > token_budget:
                skipped_keys.append(key)
                manifest_entries.append(
                    {
                        "key": key,
                        "mode": policy.mode,
                        "estimated_tokens": estimated_tokens,
                        "skipped": True,
                        "reason": "token_budget_exceeded",
                    }
                )
                continue

            dynamic_summary[key] = {
                "mode": policy.mode,
                "data": summarized,
            }
            consumed_tokens += estimated_tokens
            manifest_entries.append(
                {
                    "key": key,
                    "mode": policy.mode,
                    "estimated_tokens": estimated_tokens,
                }
            )

        manifest = {
            "available_dynamic_keys": ordered_keys,
            "selected_dynamic_keys": list(dynamic_summary.keys()),
            "skipped_dynamic_keys": skipped_keys,
            "token_budget": token_budget,
            "token_consumed": consumed_tokens,
            "entries": manifest_entries,
        }
        return dynamic_summary, manifest

    def _summarize_value(self, value: Any, policy: DynamicKeyPolicy, depth: int = 0) -> Any:
        """递归裁剪列表/字典/字符串，兼顾深层次结构。"""
        if value is None:
            return None
        item_limit = policy.item_limit or 5
        char_limit = policy.char_limit or 200
        if depth > 0:
            item_limit = max(1, min(item_limit, 2))
            char_limit = max(40, min(char_limit, 160))
        if isinstance(value, list):
            items = [self._summarize_value(item, policy, depth + 1) for item in value[:item_limit]]
            if len(value) > item_limit:
                items.append(f"... trimmed {len(value) - item_limit} items")
            return items
        if isinstance(value, dict):
            summary: Dict[str, Any] = {}
            for index, (k, v) in enumerate(value.items()):
                if index >= item_limit:
                    summary["__more__"] = f"... trimmed {len(value) - item_limit} keys"
                    break
                summary[k] = self._summarize_value(v, policy, depth + 1)
            return summary
        if isinstance(value, str):
            return self._safe_preview(value, char_limit)
        return value

    def _build_lossless_entry(
        self,
        key: str,
        value: Any,
        policy: DynamicKeyPolicy,
    ) -> Dict[str, Any]:
        """构建 lossless 模式的视图与 manifest。"""
        ref = f"context:{key}"
        is_loaded = value is not None
        preview = (
            self._safe_preview(value, policy.preview_chars)
            if is_loaded
            else "[context not loaded]"
        )
        byte_size = self._estimate_bytes(value) if is_loaded else 0
        manifest_entry = {
            "key": key,
            "mode": "lossless",
            "ref": ref,
            "bytes": byte_size,
            "preview_len": len(preview),
            "loaded": is_loaded,
        }
        view = {
            "mode": "lossless",
            "ref": ref,
            "preview": preview,
            "bytes": byte_size,
            "loaded": is_loaded,
        }
        if is_loaded:
            view["data"] = value
        return {"view": view, "manifest": manifest_entry}

    def _dynamic_token_budget(self, planning_round: int) -> int:
        """根据轮次计算动态上下文可用 token 预算。"""
        cfg = self.policy.budgets
        base = cfg["base_token_budget"]
        increment = cfg["per_round_increment"]
        max_budget = cfg["max_token_budget"]
        budget = base + (max(0, planning_round - 1) * increment)
        return min(budget, max_budget)

    @staticmethod
    def _estimate_bytes(value: Any) -> int:
        """估算对象序列化后的字节数。"""
        try:
            return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))
        except Exception:
            return len(str(value).encode("utf-8"))

    @staticmethod
    def _safe_preview(text: Any, limit: int) -> str:
        """安全截断字符串，避免超长字段进入提示词。"""
        value = str(text)
        return value if len(value) <= limit else f"{value[:limit]}..."

    # ------------------------------------------------------------------
    # 上下文检索实现
    # ------------------------------------------------------------------

    async def _get_recent_memories(
        self,
        user_id: str,
        limit: int,
        thread_id: Optional[str],
        shared_thread: bool,
        channel: Optional[str],
    ) -> List[Dict[str, Any]]:
        """调用 MCP `search` 工具拉取最近记忆，输出统一字段结构。"""
        filters = {"limit": limit}
        if thread_id:
            filters["thread_id"] = thread_id
            filters["type"] = "chat_turn"
            if shared_thread:
                filters["shared_thread"] = True
            if channel:
                filters["channel"] = channel
        try:
            memories = await self.ai_engine._call_mcp_tool(
                "search",
                query="",
                user_id=user_id,
                filters=filters,
            )
        except Exception as exc:
            logger.error("context.memories.failed", error=str(exc))
            return []
        result: List[Dict[str, Any]] = []
        for memory in memories or []:
            if not isinstance(memory, dict):
                continue
            aiu = memory.get("ai_understanding", {})
            time_value = memory.get("occurred_at") or memory.get("created_at")
            speaker_value = (
                memory.get("speaker")
                or (memory.get("ai_data") or {}).get("speaker")
                or memory.get("role")
            )
            speaker_display = (
                memory.get("speaker_display")
                or (memory.get("ai_data") or {}).get("speaker_display")
                or speaker_value
            )
            result.append(
                {
                    "content": memory.get("content", ""),
                    "ai_understanding": aiu if isinstance(aiu, dict) else {},
                    "time": time_value,
                    "speaker": speaker_value,
                    "speaker_display": speaker_display,
                }
            )
        return result

    async def _get_thread_summary(self, user_id: str, thread_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """检索线程级工作记忆，返回最新的 scratchpad 数据。"""
        if not thread_id:
            return None
        try:
            filters = {
                "thread_id": thread_id,
                "type": "thread_summary",
                "limit": 1,
            }
            records = await self.ai_engine._call_mcp_tool(
                "search",
                query="",
                user_id=user_id,
                filters=filters,
            )
            if not records or not isinstance(records, list):
                return None
            record = records[0]
            ai_data = record.get("ai_data") or record.get("ai_understanding") or {}
            summary = {
                "thread_scratchpad": ai_data.get("thread_scratchpad"),
                "structured_summary": ai_data.get("structured_summary"),
                "conversation_focus": ai_data.get("conversation_focus"),
                "updated_at": ai_data.get("updated_at") or record.get("occurred_at"),
                "content": record.get("content"),
            }
            return summary
        except Exception as exc:
            logger.warning("context.thread_summary.failed", error=str(exc), thread_id=thread_id)
            return None

    async def _semantic_search(
        self,
        user_id: str,
        query: str,
        top_k: int,
        thread_id: Optional[str],
        shared_thread: bool,
        channel: Optional[str],
    ) -> List[Dict[str, Any]]:
        """执行语义检索，返回内容/理解标签/时间戳等关键字段。"""
        filters = {"limit": top_k}
        if thread_id:
            filters["thread_id"] = thread_id
        if shared_thread:
            filters["shared_thread"] = True
        if channel:
            filters["channel"] = channel
        query_embedding = None
        try:
            embs = await self.ai_engine.llm.embed([query])
            query_embedding = embs[0] if embs else None
        except Exception:
            query_embedding = None
        try:
            results = await self.ai_engine._call_mcp_tool(
                "search",
                query=query,
                user_id=user_id,
                filters=filters,
                query_embedding=query_embedding,
            )
        except Exception as exc:
            logger.error("context.semantic.failed", error=str(exc))
            return []
        formatted: List[Dict[str, Any]] = []
        for item in results or []:
            if isinstance(item, dict):
                formatted.append(
                    {
                        "content": item.get("content", ""),
                        "ai_understanding": item.get("ai_understanding", {}),
                        "time": item.get("occurred_at"),
                    }
                )
        return formatted

    async def _direct_search(
        self,
        request: Dict[str, Any],
        user_id: str,
        thread_id: Optional[str],
        shared_thread: bool,
        channel: Optional[str],
    ) -> List[Dict[str, Any]]:
        """
        根据请求执行 direct_search。

        - scope 为 family 时使用家庭 user_id 集合。
        - scope 为 personal 时解析成员标识映射到具体 user_id。
        - 返回原始列表，供上层控制裁剪。
        """
        filters = request.get("filters", {}) or {}
        limit = request.get("limit", 20)
        try:
            limit = int(limit)
        except Exception:
            limit = 20
        filters["limit"] = limit
        scope = request.get("scope", "family")
        household_context = await household_service.get_context()
        family_user_ids = household_context.get("family_scope", {}).get("user_ids", [])
        context_user_id: Any = user_id
        if scope == "family":
            context_user_id = family_user_ids or user_id
        elif scope == "thread":
            context_user_id = user_id
            if thread_id and "thread_id" not in filters:
                filters["thread_id"] = thread_id
        elif scope == "personal":
            person_key = request.get("person_key")
            identifier = person_key or request.get("person")
            resolved = self._resolve_person_to_user_id(identifier, user_id, household_context)
            context_user_id = resolved or user_id
        if shared_thread:
            filters["shared_thread"] = True
        results = await self.ai_engine._call_mcp_tool(
            "search",
            query=request.get("query", ""),
            user_id=context_user_id,
            filters=filters,
            trace_id=request.get("trace_id"),
        )
        return results if isinstance(results, list) else []

    def _resolve_person_to_user_id(
        self,
        person_or_key: Optional[str],
        current_user_id: str,
        household_context: Dict[str, Any],
    ) -> Optional[str]:
        """
        将 LLM 给出的人员标识解析为 user_id。

        支持：
        - 直接 member_key 命中。
        - 成员 display_name 大小写不敏感匹配。
        - 特殊值“我/我的”回退到当前用户。
        """
        if not person_or_key:
            return None
        candidate = person_or_key.strip()
        if not candidate:
            return None
        if candidate in {"我", "我的"}:
            return current_user_id
        members = household_context.get("members", [])
        members_index = household_context.get("members_index", {})
        if candidate in members_index:
            user_ids = members_index[candidate].get("user_ids", [])
            return user_ids[0] if user_ids else None
        lower = candidate.lower()
        for member in members:
            display_name = member.get("display_name", "")
            if display_name.lower() == lower:
                user_ids = member.get("user_ids", [])
                return user_ids[0] if user_ids else None
        logger.debug("context.person_resolution_failed", candidate=candidate)
        return None


# -----------------------------------------------------------------------------
# 主引擎
# -----------------------------------------------------------------------------


class AIEngineV2:
    """
    FAA 核心引擎，负责驱动统一的 Plan→Act→Observe 循环。

    关键特性：
    - 单循环：LLM 在一次循环中完成计划、执行、反思，直到主动终止。
    - 数据驱动：上下文、工具调用、回复均通过 Prompt 契约自描述，工程层无业务逻辑。
    - 可观测：每一轮的上下文状态、计划、执行结果都会写入结构化日志。
    """

    def __init__(self) -> None:
        """初始化核心依赖（LLM、上下文管理器、缓存等）。"""
        self.llm = LLMClient()
        self.mcp_client = None
        self.mcp_url = os.getenv("MCP_SERVER_URL", "http://faa-mcp:8000")
        self._http_client: Optional[httpx.AsyncClient] = None

        self.message_processor = MessageProcessor()
        self.context_manager = ContextManager(self)

        self._tool_calls_by_trace: Dict[str, List[Dict[str, Any]]] = {}
        self._emb_cache_by_trace: Dict[str, Dict[str, List[float]]] = {}
        self._emb_cache_global: Dict[str, Tuple[List[float], float]] = {}
        self._emb_cache_global_max_items = 1000
        self._emb_cache_global_ttl = 3600.0

        self.agent_max_turns = getattr(settings, "AGENT_MAX_TURNS", 3)

    async def process_message(self, content: str, user_id: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        主入口：处理用户消息。

        步骤：
        1. 预处理消息并记录日志。
        2. 初始化 `AgentState` 与基础上下文。
        3. 运行 Plan→Act 循环获取最终响应。
        4. 按需写入记忆并记录实验数据。
        """
        trace_id = str(uuid.uuid4())
        start_time = asyncio.get_event_loop().time()
        try:
            self._init_trace(trace_id, user_id, context)
            processed_content = await self._preprocess_message(content, context)
            logger.info(
                "agent.step.preprocess",
                trace_id=trace_id,
                original_length=len(content or ""),
                processed_length=len(processed_content),
                has_attachments=bool(context and context.get("attachments")),
            )

            prompt_version = self._get_experiment_version(user_id, context)
            logger.debug("agent.prompt_version", trace_id=trace_id, version=prompt_version)

            thread_id = (context or {}).get("thread_id")
            channel = (context or {}).get("channel")
            shared_thread = bool((context or {}).get("shared_thread"))

            state = AgentState(
                user_id=user_id,
                thread_id=thread_id,
                channel=channel,
                trace_id=trace_id,
                user_message=processed_content,
            )

            base_context = await self.context_manager.get_basic_context(
                user_id=user_id,
                thread_id=thread_id,
                shared_thread=shared_thread,
                channel=channel,
            )
            state.raw_context.update(base_context)
            request_meta = self._build_request_meta(
                state=state,
                base_context=base_context,
                incoming_context=context,
                prompt_version=prompt_version,
            )
            if request_meta:
                state.raw_context["request_meta"] = request_meta

            final_response = await self._run_agent_loop(
                state=state,
                context=context,
                prompt_version=prompt_version,
            )

            reply_text = final_response.reply.strip() if final_response.reply else "抱歉，我需要更多时间来处理。"
            await self._store_conversation_turn(
                user_id=user_id,
                thread_id=thread_id,
                trace_id=trace_id,
                user_message=processed_content,
                assistant_message=reply_text,
                memory_record=final_response.memory_record,
                context=context,
            )

            self._record_experiment_result(
                user_id=user_id,
                context=context,
                trace_id=trace_id,
                state=state,
                final_response=final_response,
            )

            logger.info(
                "agent.process.completed",
                trace_id=trace_id,
                total_duration_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
                steps=state.step_count,
                status=final_response.status,
            )
            return reply_text
        except Exception as exc:
            logger.exception("agent.process.failed", trace_id=trace_id, error=str(exc))
            error_response = await self._handle_error(exc, trace_id, user_id)
            return error_response
        finally:
            self._cleanup_trace(trace_id)

    async def _run_agent_loop(
        self,
        *,
        state: AgentState,
        context: Optional[Dict[str, Any]],
        prompt_version: str,
    ) -> AgentFinalResponseModel:
        """
        驱动单轮 Plan→Act→Observe 循环。

        - 每轮根据 `context_round` 生成预算化上下文。
        - 调用 LLM 获取行动计划并解析为 `AgentActionModel`。
        - 执行动作、记录 observation，并根据 stop/terminate 决定是否退出循环。
        - 若耗尽回合仍未终止，则以 `max_turns` 状态结束。
        """
        max_turns = max(1, self.agent_max_turns)
        for turn_index in range(max_turns):
            state.context_round += 1
            # 中文注释：为每轮记录耗时与关键事件，帮助定位性能瓶颈
            turn_metrics: Dict[str, Any] = {
                "turn": turn_index + 1,
                "context_round": state.context_round,
            }
            context_start = time.perf_counter()
            plan_view = self.context_manager.build_plan_view(state.raw_context, state.context_round)
            turn_metrics["context_build_ms"] = int((time.perf_counter() - context_start) * 1000)
            manifest = plan_view.get("manifest", {})
            logger.debug(
                "agent.loop.context_snapshot",
                trace_id=state.trace_id,
                turn=turn_index + 1,
                context_round=state.context_round,
                light=len(plan_view.get("light_context", [])),
                household_members=manifest.get("household_members_total"),
                dynamic_selected=manifest.get("selected_dynamic_keys"),
            )
            turn_metrics["dynamic_selected"] = manifest.get("selected_dynamic_keys")
            planning_payload = state.build_planning_payload(context_view=plan_view, max_turns=max_turns)
            planning_prompt = await prompt_manager.get_planning_prompt_with_tools(prompt_version)
            system_prompt = await prompt_manager.get_system_prompt_with_tools(prompt_version)

            user_prompt = "\n\n".join(
                [
                    planning_prompt,
                    "输入数据：",
                    json.dumps(planning_payload, ensure_ascii=False, default=str),
                    "请严格按照契约输出 JSON。",
                ]
            )

            logger.info(
                "agent.loop.request",
                trace_id=state.trace_id,
                turn=turn_index + 1,
                remaining=planning_payload["meta"]["remaining_turns"],
            )

            try:
                llm_start = time.perf_counter()
                raw_plan = await self.llm.chat_json(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.2,
                    max_tokens=800,
                )
                turn_metrics["planning_llm_ms"] = int((time.perf_counter() - llm_start) * 1000)
            except Exception as exc:
                logger.error("agent.loop.llm_failed", trace_id=state.trace_id, error=str(exc))
                turn_metrics["llm_error"] = str(exc)
                state.metadata.setdefault("timings", []).append(turn_metrics)
                return await self._generate_final_output(
                    state=state,
                    context=context,
                    prompt_version=prompt_version,
                    status="llm_plan_error",
                    reason=str(exc),
                )

            try:
                action = AgentActionModel(**raw_plan)
                turn_metrics["planned_action"] = action.action
                logger.info(
                    "agent.loop.plan_parsed",
                    trace_id=state.trace_id,
                    turn=turn_index + 1,
                    action=action.action,
                    tool=action.tool,
                    expected_outcome=action.expected_outcome,
                    stop=action.stop,
                )
            except ValidationError as exc:
                logger.error("agent.loop.plan_validation_failed", trace_id=state.trace_id, error=str(exc), raw=raw_plan)
                logger.error(f"raw_plan: {raw_plan}")
                observation = {
                    "success": False,
                    "summary": "计划解析失败，进入回退流程",
                    "type": "system",
                    "error": str(exc),
                }
                fallback_action = AgentActionModel(action="no_op", thought="计划解析失败", input={})
                state.add_step(fallback_action, observation)
                turn_metrics["planned_action"] = "validation_error"
                turn_metrics["validation_error"] = str(exc)
                state.metadata.setdefault("timings", []).append(turn_metrics)
                return await self._generate_final_output(
                    state=state,
                    context=context,
                    prompt_version=prompt_version,
                    status="invalid_plan",
                    reason=str(exc),
                )

            observation = await self._execute_action(
                action=action,
                state=state,
                context=context,
                prompt_version=prompt_version,
            )
            state.add_step(action, observation)
            logger.debug(
                "agent.loop.observation_recorded",
                trace_id=state.trace_id,
                turn=turn_index + 1,
                success=observation.get("success"),
                summary=observation.get("summary"),
                obs_type=observation.get("type"),
                terminate=observation.get("terminate"),
            )
            turn_metrics["observation_type"] = observation.get("type")
            turn_metrics["observation_success"] = bool(observation.get("success"))
            turn_metrics["terminate_flag"] = bool(observation.get("terminate"))

            if observation.get("update_context"):
                updated = observation.get("update_context")
                if isinstance(updated, dict):
                    for key, value in updated.items():
                        if value is not None:
                            state.raw_context[key] = value
            if observation.get("data"):
                turn_metrics["observation_has_data"] = True

            state.metadata.setdefault("timings", []).append(turn_metrics)

            inline_final = state.metadata.get("inline_final")
            if inline_final:
                turn_metrics["inline_final"] = True
                final_payload = state.metadata.pop("inline_final")
                logger.info(
                    "agent.loop.inline_final",
                    trace_id=state.trace_id,
                    turn=turn_index + 1,
                    action=action.action,
                )
                return AgentFinalResponseModel(
                    reply=final_payload.get("reply") or "（缺少最终回复）",
                    memory_record=final_payload.get("memory_record") or {},
                    followups=final_payload.get("followups") or [],
                    status=final_payload.get("status") or "success",
                )

            if action.stop or action.action in {"respond", "finalize"}:
                logger.info("agent.loop.stop_signal", trace_id=state.trace_id, turn=turn_index + 1)
                return await self._generate_final_output(
                    state=state,
                    context=context,
                    prompt_version=prompt_version,
                    status="completed",
                    reason="agent_stop",
                )

            if observation.get("terminate"):
                logger.info(
                    "agent.loop.terminate_flag",
                    trace_id=state.trace_id,
                    turn=turn_index + 1,
                    reason=observation.get("summary"),
                )
                return await self._generate_final_output(
                    state=state,
                    context=context,
                    prompt_version=prompt_version,
                    status="terminated",
                    reason=observation.get("summary"),
                )

        logger.warning("agent.loop.max_turns_reached", trace_id=state.trace_id)
        return await self._generate_final_output(
            state=state,
            context=context,
            prompt_version=prompt_version,
            status="max_turns",
            reason="Reached maximum agent turns",
        )

    async def _execute_action(
        self,
        *,
        action: AgentActionModel,
        state: AgentState,
        context: Optional[Dict[str, Any]],
        prompt_version: str,
    ) -> Dict[str, Any]:
        """
        执行单个行动并返回观测结果。

        支持：
        - `call_tool`：调用 MCP 工具并记录成功 / 失败。
        - `fetch_context`：解析上下文请求并更新 `state.raw_context`。
        - `respond` / `finalize` / `clarify`：控制型动作，指示循环退出或提问。
        - 未知动作会直接返回错误并触发终止，防止状态机失控。
        """
        trace_id = state.trace_id
        normalized_input = action.normalized_input()

        if action.action == "call_tool":
            tool_name = action.tool or normalized_input.get("tool") or action.metadata.get("tool")
            if not tool_name:
                summary = "缺少工具名称，无法执行调用"
                logger.warning("agent.tool.missing_name", trace_id=trace_id)
                return {"success": False, "summary": summary, "type": "tool", "error": "missing_tool_name"}
            params = normalized_input.get("args") if isinstance(normalized_input.get("args"), dict) else normalized_input
            params = dict(params or {})
            try:
                result = await self._call_mcp_tool(tool_name, trace_id=trace_id, **params)
                summary = self._summarize_tool_result(tool_name, result)
                logger.info("agent.tool.success", trace_id=trace_id, tool=tool_name)
                context_update = self.context_manager.prepare_tool_context_update(
                    tool_name=tool_name,
                    params=params,
                    result=result,
                )
                return {
                    "success": True,
                    "summary": summary,
                    "type": "tool",
                    "tool": tool_name,
                    "data": result,
                    "update_context": context_update or None,
                }
            except Exception as exc:
                logger.error("agent.tool.failed", trace_id=trace_id, tool=tool_name, error=str(exc))
                return {
                    "success": False,
                    "summary": f"工具 {tool_name} 调用失败: {exc}",
                    "type": "tool",
                    "tool": tool_name,
                    "error": str(exc),
                }

        if action.action == "fetch_context":
            requests = []
            if "requests" in normalized_input and isinstance(normalized_input["requests"], list):
                requests = normalized_input["requests"]
            elif isinstance(action.input, list):
                requests = action.input
            else:
                requests = [normalized_input]
            try:
                extra_context = await self.context_manager.resolve_context_requests(
                    context_requests=requests,
                    understanding={"original_content": state.original_user_message},
                    user_id=state.user_id,
                    thread_id=state.thread_id,
                    shared_thread=bool((context or {}).get("shared_thread")),
                    channel=state.channel,
                    trace_id=trace_id,
                    existing_context=state.raw_context,
                    agent_state=state,
                )
                summary = f"Fetched context keys: {list(extra_context.keys())}"
                logger.info("agent.context.fetched", trace_id=trace_id, keys=list(extra_context.keys()))
                return {
                    "success": True,
                    "summary": summary,
                    "type": "context",
                    "data": extra_context,
                    "update_context": extra_context,
                }
            except Exception as exc:
                logger.error("agent.context.failed", trace_id=trace_id, error=str(exc))
                return {
                    "success": False,
                    "summary": f"获取上下文失败: {exc}",
                    "type": "context",
                    "error": str(exc),
                    "terminate": True,
                }

        if action.action in {"respond", "finalize"}:
            inline_reply = normalized_input.get("reply") or action.metadata.get("reply")
            inline_memory = normalized_input.get("memory_record") or action.metadata.get("memory_record")
            inline_followups = normalized_input.get("followups") or action.metadata.get("followups")
            inline_status = normalized_input.get("status") or action.metadata.get("status") or "success"
            inline_data = None
            summary = "LLM 请求立即生成最终回复"
            if inline_reply:
                summary = "Inline final reply ready"
                inline_data = {
                    "inline_reply": inline_reply,
                    "memory_record": inline_memory,
                    "followups": inline_followups,
                    "status": inline_status,
                }
                state.metadata["inline_final"] = {
                    "reply": inline_reply,
                    "memory_record": inline_memory or {},
                    "followups": inline_followups or [],
                    "status": inline_status,
                }
            logger.info("agent.control.respond", trace_id=trace_id, inline=bool(inline_reply))
            observation_payload = {
                "success": True,
                "summary": summary,
                "type": "control",
                "terminate": True,
            }
            if inline_data:
                observation_payload["data"] = inline_data
            return observation_payload

        if action.action == "clarify":
            question = normalized_input.get("question") or action.metadata.get("question")
            summary = question or "需要澄清信息"
            return {
                "success": True,
                "summary": summary,
                "type": "clarify",
                "terminate": True,
            }

        logger.warning("agent.action.unknown", trace_id=trace_id, action=action.action)
        return {
            "success": False,
            "summary": f"未知的行动类型: {action.action}",
            "type": "system",
            "error": "unknown_action",
            "terminate": True,
        }

    async def _generate_final_output(
        self,
        *,
        state: AgentState,
        context: Optional[Dict[str, Any]],
        prompt_version: str,
        status: str,
        reason: Optional[str],
    ) -> AgentFinalResponseModel:
        """
        调用 LLM 生成最终回复。

        - 组装 `state.build_final_payload` 返回的上下文。
        - 调用响应 prompt 输出契约 JSON。
        - 若解析失败，降级到固定的兜底文本。
        """
        plan_view = self.context_manager.build_plan_view(state.raw_context, max(1, state.context_round))
        payload = state.build_final_payload(context_view=plan_view, status=status, reason=reason)
        response_prompt = prompt_manager.get_response_prompt(prompt_version)
        system_prompt = await prompt_manager.get_system_prompt_with_tools(prompt_version)
        user_prompt = "\n\n".join(
            [
                response_prompt,
                "输入：",
                json.dumps(payload, ensure_ascii=False, default=str),
                "请返回契约 JSON。",
            ]
        )
        logger.info(
            "agent.final.request",
            trace_id=state.trace_id,
            status=status,
            reason=reason,
            steps=len(state.steps),
        )
        try:
            final_result = await self.llm.chat_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=900,
            )
            try:
                model = AgentFinalResponseModel(**final_result)
                model.status = status or model.status
                logger.info(
                    "agent.final.success",
                    trace_id=state.trace_id,
                    reply_length=len(model.reply or ""),
                    status=model.status,
                    followups=len(model.followups),
                    should_store=model.memory_record.get("should_store", True),
                )
                return model
            except ValidationError as exc:
                logger.error("agent.final.validation_failed", trace_id=state.trace_id, error=str(exc), raw=final_result)
        except Exception as exc:
            logger.error("agent.final.llm_failed", trace_id=state.trace_id, error=str(exc))
        # 中文注释：回退策略，确保用户始终收到回复
        fallback_text = "抱歉，我暂时无法完整处理该请求，但已经记录您的需求，会尽快完善。"
        return AgentFinalResponseModel(reply=fallback_text, status="error", memory_record={})

    def _summarize_tool_result(self, tool_name: str, result: Any) -> str:
        """将工具返回值压缩为可读摘要，便于写入日志或步骤记录。"""
        if isinstance(result, dict):
            preview = json.dumps(result, ensure_ascii=False, default=str)
        elif isinstance(result, list):
            preview = json.dumps(result[:3], ensure_ascii=False, default=str)
        else:
            preview = str(result)
        if len(preview) > 240:
            preview = f"{preview[:240]}..."
        return f"{tool_name} 完成，返回：{preview}"

    # ------------------------------------------------------------------
    # 基础设施：Trace、错误、缓存
    # ------------------------------------------------------------------

    def _init_trace(self, trace_id: str, user_id: str, context: Optional[Dict[str, Any]]) -> None:
        """初始化追踪信息并准备 per-trace 缓存。"""
        thread_id = (context or {}).get("thread_id")
        channel = (context or {}).get("channel")
        preview = (context or {}).get("content", "")[:50]
        logger.info(
            "message.received",
            trace_id=trace_id,
            user_id=user_id,
            thread_id=thread_id,
            channel=channel,
            preview=preview,
            has_attachments=bool(context and context.get("attachments")),
        )
        self._tool_calls_by_trace[trace_id] = []
        self._emb_cache_by_trace[trace_id] = {}

    async def _preprocess_message(self, content: str, context: Optional[Dict[str, Any]]) -> str:
        """合并附件文本，返回处理后的消息。"""
        attachments = (context or {}).get("attachments") if context else None
        return self.message_processor.merge_attachment_texts(content, attachments)

    def _build_request_meta(
        self,
        *,
        state: AgentState,
        base_context: Dict[str, Any],
        incoming_context: Optional[Dict[str, Any]],
        prompt_version: str,
    ) -> Dict[str, Any]:
        """构建本次请求的实时元数据，供 Prompt 使用。"""
        tz_name = self._determine_timezone(base_context, incoming_context)
        zone = self._safe_zoneinfo(tz_name)
        now_local = datetime.now(zone)
        now_utc = datetime.now(ZoneInfo("UTC"))
        month_last_day = calendar.monthrange(now_local.year, now_local.month)[1]
        month_start = datetime(now_local.year, now_local.month, 1, tzinfo=zone)
        month_end = datetime(
            now_local.year,
            now_local.month,
            month_last_day,
            23,
            59,
            59,
            tzinfo=zone,
        )
        days_remaining = max(0, month_last_day - now_local.day)

        message_sent_iso = None
        message_sent_utc = None
        message_timestamp = None
        webhook_received_iso = None
        webhook_received_utc = None
        if incoming_context:
            message_sent_iso = incoming_context.get("message_sent_at_iso")
            message_sent_utc = incoming_context.get("message_sent_at_utc")
            message_timestamp = incoming_context.get("timestamp")
            webhook_received_iso = incoming_context.get("webhook_received_at_iso")
            webhook_received_utc = incoming_context.get("webhook_received_at_utc")

        clock_section = {
            "now_local_iso": now_local.isoformat(),
            "now_utc_iso": now_utc.isoformat(),
            "timezone": tz_name,
            "today": now_local.date().isoformat(),
            "weekday_cn": self._weekday_cn(now_local.weekday()),
            "weekday_en": now_local.strftime("%A"),
            "time_hm": now_local.strftime("%H:%M"),
        }
        period_section = {
            "month_label": now_local.strftime("%Y-%m"),
            "month_start_iso": month_start.isoformat(),
            "month_end_iso": month_end.isoformat(),
            "days_into_month": now_local.day,
            "days_remaining": days_remaining,
        }
        message_section = {
            "channel": state.channel,
            "thread_id": state.thread_id,
            "message_sent_at_iso": message_sent_iso,
            "message_sent_at_utc": message_sent_utc,
            "webhook_received_at_iso": webhook_received_iso,
            "webhook_received_at_utc": webhook_received_utc,
            "raw_timestamp": message_timestamp,
        }
        runtime_section = {
            "engine": "AIEngineV2",
            "prompt_version": prompt_version,
            "agent_max_turns": self.agent_max_turns,
            "trace_id": state.trace_id,
            "user_id": state.user_id,
            "shared_thread": bool((incoming_context or {}).get("shared_thread")),
        }

        message_section = {k: v for k, v in message_section.items() if v is not None}
        runtime_section = {k: v for k, v in runtime_section.items() if v is not None}

        return {
            "clock": clock_section,
            "period": period_section,
            "message": message_section,
            "runtime": runtime_section,
        }

    def _determine_timezone(
        self,
        base_context: Optional[Dict[str, Any]],
        incoming_context: Optional[Dict[str, Any]],
    ) -> str:
        """按优先级选择当前会话应使用的时区。"""
        if incoming_context:
            for key in ("timezone", "user_timezone", "preferred_timezone"):
                candidate = incoming_context.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
            raw_webhook = incoming_context.get("raw_webhook")
            if isinstance(raw_webhook, dict):
                candidate = raw_webhook.get("timezone")
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
        household_context = (base_context or {}).get("household")
        if isinstance(household_context, dict):
            households = household_context.get("households") or []
            for entry in households:
                config = entry.get("config") or {}
                candidate = config.get("timezone")
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
        return getattr(settings, "DEFAULT_TIMEZONE", "Asia/Shanghai")

    @staticmethod
    def _safe_zoneinfo(tz_name: str) -> ZoneInfo:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            return ZoneInfo("UTC")

    @staticmethod
    def _weekday_cn(index: int) -> str:
        labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        try:
            return labels[index % 7]
        except Exception:
            return "周?"

    def _get_experiment_version(self, user_id: str, context: Optional[Dict[str, Any]]) -> str:
        """根据用户与渠道获取当前使用的 prompt 版本（兼容 A/B 测试）。"""
        channel = (context or {}).get("channel") if context else None
        return get_experiment_version(user_id=user_id, channel=channel, default_version="v5_unified")

    async def _handle_error(self, error: Exception, trace_id: str, user_id: str) -> str:
        """统一错误处理，记录日志并返回用户友好的提示。"""
        logger.error(
            "message.process.error",
            trace_id=trace_id,
            user_id=user_id,
            error_type=type(error).__name__,
            error=str(error),
        )
        if isinstance(error, (ContextResolutionError, ToolExecutionError, LLMError)):
            return get_user_friendly_message(error)
        return "抱歉，处理您的消息时出现了问题，请稍后重试。"

    def _cleanup_trace(self, trace_id: str) -> None:
        """清理与 trace 相关的缓存数据。"""
        self._tool_calls_by_trace.pop(trace_id, None)
        self._emb_cache_by_trace.pop(trace_id, None)

    # ------------------------------------------------------------------
    # MCP 调用与缓存
    # ------------------------------------------------------------------

    async def _call_mcp_tool(self, tool_name: str, trace_id: Optional[str] = None, **kwargs) -> Any:
        """
        调用 MCP 工具并自动记录成功 / 失败。

        - 所有参数以 JSON 形式透传。
        - 成功 / 失败都会写入 `_tool_calls_by_trace`，便于追踪一次会话的工具调用链路。
        """
        if self._http_client is None:
            self._http_client = httpx.AsyncClient()
        try:
            response = await self._http_client.post(
                f"{self.mcp_url}/tool/{tool_name}",
                json=kwargs,
                timeout=10.0,
            )
            response.raise_for_status()
            result = response.json()
            if trace_id:
                self._tool_calls_by_trace.setdefault(trace_id, []).append(
                    {"tool": tool_name, "success": True, "timestamp": time.time()}
                )
            return result
        except Exception as exc:
            if trace_id:
                self._tool_calls_by_trace.setdefault(trace_id, []).append(
                    {"tool": tool_name, "success": False, "error": str(exc), "timestamp": time.time()}
                )
            raise ToolExecutionError(
                f"工具 {tool_name} 调用失败: {exc}",
                trace_id=trace_id,
                context={"tool_name": tool_name},
                cause=exc,
            )

    async def _store_conversation_turn(
        self,
        *,
        user_id: str,
        thread_id: Optional[str],
        trace_id: str,
        user_message: str,
        assistant_message: str,
        memory_record: Dict[str, Any],
        context: Optional[Dict[str, Any]],
    ) -> None:
        """将本轮对话及线程工作记忆写入 MCP，便于后续上下文引用。"""
        try:
            common = {
                "type": "chat_turn",
                "thread_id": thread_id,
                "trace_id": trace_id,
                "channel": (context or {}).get("channel"),
                "timestamp": datetime.now().isoformat(),
            }

            should_store = True
            intent = None
            entities: Dict[str, Any] = {}
            extra_payload: Dict[str, Any] = {}
            structured_summary: Optional[Dict[str, Any]] = None
            scratchpad: Optional[Dict[str, Any]] = None
            confidence = None

            if isinstance(memory_record, dict):
                should_store = memory_record.get("should_store", True)
                intent = memory_record.get("intent")
                if should_store:
                    entities = memory_record.get("entities", {}) or {}
                confidence = memory_record.get("confidence")
                extra_payload = memory_record.get("extra", {}) or {}
                scratchpad = extra_payload.get("thread_scratchpad")
                structured_summary = extra_payload.get("structured_summary")

            speaker_identifier = (
                (context or {}).get("speaker")
                or (context or {}).get("sender_id")
                or (context or {}).get("author_id")
                or (context or {}).get("nickname")
                or (context or {}).get("from")
                or extra_payload.get("speaker")
                or user_id
            )
            speaker_display = (
                (context or {}).get("nickname")
                or extra_payload.get("speaker")
                or speaker_identifier
            )

            assistant_name = getattr(settings, "ASSISTANT_NAME", "FAA Assistant")
            assistant_speaker = extra_payload.get("assistant_speaker") or assistant_name

            user_ai = {
                **common,
                "role": "user",
                "intent": intent,
                **entities,
                "speaker": speaker_identifier,
                "speaker_display": speaker_display,
            }
            assistant_ai = {
                **common,
                "role": "assistant",
                "intent": intent,
                **entities,
                "speaker": assistant_speaker,
                "speaker_display": assistant_name,
            }
            if confidence is not None:
                user_ai["confidence"] = confidence
                assistant_ai["confidence"] = confidence
            if extra_payload:
                user_ai["extra"] = extra_payload
                assistant_ai["extra"] = extra_payload

            if should_store:
                memories = [
                    {"content": user_message, "ai_data": user_ai, "user_id": user_id},
                    {"content": assistant_message, "ai_data": assistant_ai, "user_id": user_id},
                ]
                await self._call_mcp_tool("batch_store", memories=memories, trace_id=trace_id)
            else:
                logger.debug("store_conversation.skipped", trace_id=trace_id)

            if thread_id and isinstance(scratchpad, dict):
                try:
                    summary_content = scratchpad.get("conversation_focus") or json.dumps(
                        scratchpad, ensure_ascii=False
                    )
                    summary_ai_data = {
                        "type": "thread_summary",
                        "thread_id": thread_id,
                        "thread_scratchpad": scratchpad,
                        "structured_summary": structured_summary,
                        "conversation_focus": scratchpad.get("conversation_focus"),
                        "updated_at": datetime.now().isoformat(),
                        "intent": intent,
                        "speaker": speaker_identifier,
                        "confidence": confidence,
                    }
                    await self._call_mcp_tool(
                        "store",
                        content=summary_content or "(thread summary)",
                        ai_data=summary_ai_data,
                        user_id=user_id,
                        external_key=f"thread_summary:{thread_id}",
                        trace_id=trace_id,
                    )
                    logger.debug(
                        "store.thread_summary.upserted",
                        trace_id=trace_id,
                        thread_id=thread_id,
                        focus=scratchpad.get("conversation_focus"),
                    )
                except Exception as summary_exc:
                    logger.warning(
                        "store.thread_summary.failed",
                        trace_id=trace_id,
                        thread_id=thread_id,
                        error=str(summary_exc),
                    )
        except Exception as exc:
            logger.error("store_conversation.failed", trace_id=trace_id, error=str(exc))

    def _record_experiment_result(
        self,
        *,
        user_id: str,
        context: Optional[Dict[str, Any]],
        trace_id: str,
        state: AgentState,
        final_response: AgentFinalResponseModel,
    ) -> None:
        """若存在实验配置，记录本次对话的指标数据（工具次数、回复长度等）。"""
        try:
            active_experiments = ab_testing_manager.list_active_experiments()
            if not active_experiments:
                return
            channel = (context or {}).get("channel", "unknown")
            for experiment in active_experiments:
                variant, _ = ab_testing_manager.get_variant_for_user(user_id, experiment["id"], channel=channel)
                if variant == "control":
                    continue
                result = ExperimentResult(
                    user_id=user_id,
                    experiment_id=experiment["id"],
                    variant=variant,
                    trace_id=trace_id,
                    channel=channel,
                    timestamp=time.time(),
                    response_time_ms=0,
                    success=final_response.status == "success",
                    need_clarification=False,
                    tool_calls_count=state.step_count,
                    response_length=len(final_response.reply or ""),
                )
                ab_testing_manager.record_result(result)
        except Exception as exc:
            logger.warning("experiment_result.record.failed", error=str(exc))

    # ------------------------------------------------------------------
    # Reminders 与其他业务辅助 - 直接沿用上一版逻辑
    # ------------------------------------------------------------------

    async def check_and_send_reminders(self, send_func):
        """检查所有用户的待发提醒并调用 `send_func` 派发。"""
        try:
            all_users = await self._get_all_active_users()
            if not all_users:
                logger.debug("reminder.no_users")
                return
            total_reminders = 0
            for user_id in all_users:
                try:
                    user_reminders = await self._call_mcp_tool("get_pending_reminders", user_id=user_id)
                    if not user_reminders or not isinstance(user_reminders, list):
                        continue
                    total_reminders += len(user_reminders)
                    for reminder in user_reminders:
                        await self._process_single_reminder(reminder, user_id, send_func)
                except Exception as exc:
                    logger.error("reminder.user_check_failed", user_id=user_id, error=str(exc))
            if total_reminders > 0:
                logger.info("reminder.check_completed", total_found=total_reminders)
        except Exception as exc:
            logger.error("reminder.check_failed", error=str(exc))

    async def _get_all_active_users(self) -> List[str]:
        """结合家庭配置与提醒表推断需要派发提醒的 user_id 列表。"""
        try:
            household_context = await household_service.get_context()
            family_scope = household_context.get("family_scope", {}) if household_context else {}
            candidate_ids = set(family_scope.get("user_ids", []) or [])
            reminder_users = await self._get_users_from_reminders()
            candidate_ids.update(reminder_users)
            if candidate_ids:
                logger.debug(
                    "reminder.users_from_union",
                    family_count=len(family_scope.get("user_ids", []) or []),
                    reminder_only=len(candidate_ids - set(family_scope.get("user_ids", []) or [])),
                )
                return list(candidate_ids)
            logger.info("reminder.no_candidates_found")
            return []
        except Exception as exc:
            logger.warning("get_active_users.failed", error=str(exc))
            return []

    async def _get_users_from_reminders(self) -> List[str]:
        """从提醒表获取仍有待发提醒的用户集合。"""
        try:
            result = await self._call_mcp_tool("list_reminder_user_ids")
            if isinstance(result, dict) and result.get("success"):
                return [uid for uid in result.get("user_ids", []) if uid]
        except Exception as exc:
            logger.debug("reminder.users_from_reminders.failed", error=str(exc))
        return []

    async def _process_single_reminder(self, reminder: dict, user_id: str, send_func):
        """发送单条提醒并在成功后标记状态，必要时排下一次提醒。"""
        try:
            reminder_id = reminder.get("reminder_id")
            memory_id = reminder.get("memory_id")
            content = reminder.get("content", "")
            ai_understanding = reminder.get("ai_understanding", {})
            payload = reminder.get("payload") or {}
            if not reminder_id:
                logger.warning("reminder.missing_id", reminder=reminder)
                return
            reminder_text = await self._format_reminder_message(
                content,
                ai_understanding,
                payload if isinstance(payload, dict) else {},
                user_id,
            )
            success = await send_func(user_id, reminder_text)
            if success:
                await self._call_mcp_tool("mark_reminder_sent", reminder_id=reminder_id)
                await self._schedule_next_occurrence_if_needed(
                    memory_id=memory_id,
                    current_reminder=reminder,
                    payload=payload,
                )
                logger.info("reminder.sent", reminder_id=reminder_id, user_id=user_id)
            else:
                logger.warning("reminder.send_failed", reminder_id=reminder_id, user_id=user_id)
        except Exception as exc:
            logger.error(
                "reminder.process_single_failed",
                reminder_id=reminder.get("reminder_id"),
                memory_id=reminder.get("memory_id"),
                user_id=user_id,
                error=str(exc),
            )

    async def _format_reminder_message(
        self,
        content: str,
        ai_understanding: Dict[str, Any],
        payload: Dict[str, Any],
        user_id: str,
    ) -> str:
        """根据提醒类型和人员信息生成用户可读的提醒文案。"""
        try:
            reminder_type = ai_understanding.get("reminder_type")
            person = ai_understanding.get("person_display") or payload.get("person_display")
            if reminder_type == "vaccination":
                if person:
                    return f"🏥 提醒：该给{person}打疫苗了！\n\n详情：{content}"
                return f"🏥 疫苗提醒：{content}"
            if reminder_type == "medication":
                if person:
                    return f"💊 用药提醒：记得给{person}吃药\n\n详情：{content}"
                return f"💊 用药提醒：{content}"
            if reminder_type == "appointment":
                return f"📅 预约提醒：{content}"
            if reminder_type == "task":
                return f"✅ 任务提醒：{content}"
            return f"⏰ 提醒：{content}"
        except Exception:
            return f"⏰ 提醒：{content}"

    async def _schedule_next_occurrence_if_needed(
        self,
        *,
        memory_id: Optional[str],
        current_reminder: Dict[str, Any],
        payload: Dict[str, Any],
    ) -> None:
        """按照重复规则为循环提醒排下一次执行时间。"""
        try:
            if not memory_id or not isinstance(payload, dict):
                return
            rule = payload.get("repeat_rule")
            if not isinstance(rule, dict):
                return
            remind_at = current_reminder.get("remind_at")
            if not isinstance(remind_at, str):
                return
            next_dt = self._compute_next_remind_at(remind_at, rule, payload)
            if next_dt is None:
                return
            next_payload = dict(payload)
            next_payload["last_triggered_at"] = remind_at
            args = {
                "memory_id": memory_id,
                "remind_at": next_dt.isoformat(),
                "payload": next_payload,
            }
            ext_key = next_payload.get("external_key") or payload.get("external_key")
            if isinstance(ext_key, str) and ext_key.strip():
                args["external_key"] = ext_key.strip()
            await self._call_mcp_tool("schedule_reminder", **args)
        except Exception as exc:
            logger.warning("reminder.reschedule_failed", memory_id=memory_id, error=str(exc))

    def _compute_next_remind_at(
        self,
        previous_remind_at: str,
        rule: Dict[str, Any],
        payload: Dict[str, Any],
    ) -> Optional[datetime]:
        """根据重复规则计算下一次提醒时间。"""
        base_dt = self._parse_reminder_time(previous_remind_at, payload.get("timezone"))
        if base_dt is None:
            return None
        interval = rule.get("interval", 1)
        try:
            interval = max(1, int(interval))
        except Exception:
            interval = 1
        frequency = (rule.get("frequency") or "").lower()
        tz = payload.get("timezone") or rule.get("timezone")
        zone = None
        if isinstance(tz, str):
            try:
                zone = ZoneInfo(tz)
            except Exception:
                zone = None
        if zone and base_dt.tzinfo is None:
            base_dt = base_dt.replace(tzinfo=zone)
        elif base_dt.tzinfo is None:
            base_dt = base_dt.replace(tzinfo=ZoneInfo("UTC"))
        if frequency == "daily":
            next_dt = base_dt + timedelta(days=interval)
            return self._apply_time_override(next_dt, rule)
        if frequency == "weekly":
            weekdays = self._normalize_weekdays(rule.get("weekday") or rule.get("weekdays"))
            next_dt = base_dt + timedelta(days=1)
            searched = 0
            while searched < 14 * interval:
                if weekdays and next_dt.weekday() in weekdays:
                    break
                if not weekdays and (next_dt - base_dt).days % interval == 0:
                    break
                next_dt += timedelta(days=1)
                searched += 1
            return self._apply_time_override(next_dt, rule)
        if frequency == "monthly":
            target_day = rule.get("day")
            try:
                target_day = int(target_day)
            except Exception:
                target_day = base_dt.day
            year = base_dt.year
            month = base_dt.month + interval
            year += (month - 1) // 12
            month = ((month - 1) % 12) + 1
            last_day = calendar.monthrange(year, month)[1]
            day = min(max(1, target_day), last_day)
            next_dt = base_dt.replace(year=year, month=month, day=day)
            return self._apply_time_override(next_dt, rule)
        return None

    def _parse_reminder_time(self, value: str, fallback_tz: Optional[str]) -> Optional[datetime]:
        """解析提醒时间字符串，尽量补齐时区信息。"""
        if not value:
            return None
        candidate = value.strip()
        if not candidate:
            return None
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(candidate)
        except Exception:
            return None
        if dt.tzinfo is None and isinstance(fallback_tz, str):
            try:
                dt = dt.replace(tzinfo=ZoneInfo(fallback_tz))
            except Exception:
                dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt

    def _apply_time_override(self, dt: datetime, rule: Dict[str, Any]) -> datetime:
        """在重复规则中手动覆盖提醒时间（hour/minute）。"""
        time_str = rule.get("time")
        if isinstance(time_str, str) and time_str:
            parts = time_str.split(":")
            try:
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
                dt = dt.replace(hour=hour % 24, minute=minute % 60, second=0, microsecond=0)
            except Exception:
                pass
        return dt

    def _normalize_weekdays(self, value: Any) -> List[int]:
        """将星期描述统一映射为 int（0=Monday）。"""
        if value is None:
            return []
        if isinstance(value, int):
            return [value % 7]
        name_to_num = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        results: List[int] = []
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, int):
                results.append(item % 7)
            elif isinstance(item, str):
                key = item.strip().lower()
                if key.isdigit():
                    results.append(int(key) % 7)
                elif key in name_to_num:
                    results.append(name_to_num[key])
        return results

    # ------------------------------------------------------------------
    # 媒体工具（沿用）
    # ------------------------------------------------------------------

    async def generate_signed_url(self, file_key: str, expires_in: int = 3600) -> str:
        """生成带有效期的媒体访问地址。"""
        try:
            return await make_signed_url(file_key, expires_in=expires_in)
        except Exception as exc:
            logger.error("media.signed_url.failed", error=str(exc))
            raise AIEngineError("生成签名地址失败", cause=exc)


# 保持旧的别名
AIEngine = AIEngineV2
ai_engine = AIEngineV2()
ai_engine_v2 = ai_engine
