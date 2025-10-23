from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, List

import yaml
import structlog

from .config import settings

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class DynamicKeyPolicy:
    """动态上下文键的裁剪策略配置。"""

    mode: str
    item_limit: Optional[int]
    char_limit: Optional[int]
    preview_chars: int
    priority: int


class ContextPolicy:
    """
    上下文策略加载器：负责从 YAML 中读取 token 预算与动态裁剪策略。

    中文注释：通过策略文件，我们可以将“日志预览”与“真实上下文”解耦，
    针对关键信息（如 expense_category_config）提供 lossless 模式，确保 LLM 可按需获取完整数据。
    """

    def __init__(self, policy_file: str | None = None) -> None:
        self.policy_file = policy_file or getattr(settings, "CONTEXT_POLICY_FILE", "config/context_policy.yaml")
        self._data: Dict[str, Any] = {}
        self._dynamic_defaults: Dict[str, Any] = {}
        self._dynamic_policies: Dict[str, DynamicKeyPolicy] = {}
        self._load()

    # ------------------------------------------------------------------
    # 配置加载与解析
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """中文注释：从 YAML 读取策略，若文件缺失则回退到内置默认值。"""
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            root_path = os.path.dirname(project_root)
            policy_path = os.path.join(root_path, self.policy_file)
            if not os.path.exists(policy_path):
                logger.warning("Context policy file missing, using defaults", path=policy_path)
                self._use_defaults()
                return
            with open(policy_path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            self._data = data
            self._dynamic_defaults = data.get("dynamic_defaults", {}) or {}
            raw_dynamic = data.get("dynamic_keys", {}) or {}
            parsed: Dict[str, DynamicKeyPolicy] = {}
            for key, payload in raw_dynamic.items():
                if not isinstance(payload, dict):
                    continue
                parsed[key] = DynamicKeyPolicy(
                    mode=str(payload.get("mode", self._dynamic_defaults.get("mode", "summary"))),
                    item_limit=self._maybe_int(payload.get("item_limit", self._dynamic_defaults.get("item_limit"))),
                    char_limit=self._maybe_int(payload.get("char_limit", self._dynamic_defaults.get("char_limit"))),
                    preview_chars=self._maybe_int(payload.get("preview_chars", self._dynamic_defaults.get("preview_chars", 200))) or 200,
                    priority=self._maybe_int(payload.get("priority", 100)) or 100,
                )
            self._dynamic_policies = parsed
            logger.info(
                "context_policy.loaded",
                file=self.policy_file,
                dynamic_keys=list(self._dynamic_policies.keys()),
            )
        except Exception as exc:
            logger.error("context_policy.load_failed", file=self.policy_file, error=str(exc))
            self._use_defaults()

    def _use_defaults(self) -> None:
        """中文注释：兜底策略，确保即使没有配置文件也能运行。"""
        self._data = {
            "budgets": {
                "base_token_budget": 1600,
                "per_round_increment": 500,
                "max_token_budget": 4800,
            },
            "light_context": {"limit": 5, "char_limit": 200},
            "household": {"members_limit": 5, "tag_limit": 3},
        }
        self._dynamic_defaults = {
            "mode": "summary",
            "item_limit": 3,
            "char_limit": 200,
            "preview_chars": 200,
        }
        self._dynamic_policies = {
            "expense_category_config": DynamicKeyPolicy(
                mode="lossless",
                item_limit=None,
                char_limit=None,
                preview_chars=220,
                priority=0,
            )
        }

    @staticmethod
    def _maybe_int(value: Any) -> Optional[int]:
        """尝试将配置值转换为整数。"""
        try:
            if value is None:
                return None
            return int(value)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # 公共访问接口
    # ------------------------------------------------------------------

    @property
    def budgets(self) -> Dict[str, int]:
        """中文注释：返回 token 预算配置。"""
        defaults = {"base_token_budget": 1600, "per_round_increment": 500, "max_token_budget": 4800}
        raw = self._data.get("budgets") or {}
        return {
            "base_token_budget": self._maybe_int(raw.get("base_token_budget")) or defaults["base_token_budget"],
            "per_round_increment": self._maybe_int(raw.get("per_round_increment")) or defaults["per_round_increment"],
            "max_token_budget": self._maybe_int(raw.get("max_token_budget")) or defaults["max_token_budget"],
        }

    @property
    def light_context(self) -> Dict[str, int]:
        """中文注释：获取轻量记忆的裁剪配置。"""
        defaults = {"limit": 5, "char_limit": 200}
        raw = self._data.get("light_context") or {}
        return {
            "limit": self._maybe_int(raw.get("limit")) or defaults["limit"],
            "char_limit": self._maybe_int(raw.get("char_limit")) or defaults["char_limit"],
        }

    @property
    def household(self) -> Dict[str, int]:
        """中文注释：获取家庭摘要的裁剪配置。"""
        defaults = {"members_limit": 5, "tag_limit": 3}
        raw = self._data.get("household") or {}
        return {
            "members_limit": self._maybe_int(raw.get("members_limit")) or defaults["members_limit"],
            "tag_limit": self._maybe_int(raw.get("tag_limit")) or defaults["tag_limit"],
        }

    def get_dynamic_policy(self, key: str) -> DynamicKeyPolicy:
        """中文注释：返回指定动态键的策略，若不存在则使用默认策略。"""
        payload = self._dynamic_policies.get(key)
        if payload:
            return payload
        return DynamicKeyPolicy(
            mode=str(self._dynamic_defaults.get("mode", "summary")),
            item_limit=self._maybe_int(self._dynamic_defaults.get("item_limit")),
            char_limit=self._maybe_int(self._dynamic_defaults.get("char_limit")),
            preview_chars=self._maybe_int(self._dynamic_defaults.get("preview_chars")) or 200,
            priority=100,
        )

    def sorted_dynamic_keys(self, keys: list[str]) -> list[str]:
        """中文注释：按照策略优先级对动态键排序。"""
        return sorted(keys, key=lambda k: (self.get_dynamic_policy(k).priority, k))

    def known_dynamic_keys(self) -> List[str]:
        """中文注释：返回策略文件中声明的动态键，供 manifest 合并使用。"""
        return list(self._dynamic_policies.keys())

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def estimate_tokens(payload: Any) -> int:
        """
        估算 payload 所占用的 token 数。
        中文注释：粗略使用 json 序列化长度 / 4 作为 token 估计，避免额外依赖。
        """
        try:
            serialized = json.dumps(payload, ensure_ascii=False, default=str)
        except TypeError:
            serialized = str(payload)
        # 英文日志：粗略估计即可，主要用于预算门控，故限制在 >=1
        return max(1, len(serialized) // 4)
