"""
Prompt版本管理器 - 支持动态加载、profile 覆写与工具信息注入
"""
from __future__ import annotations

import asyncio
import json
import os
from copy import deepcopy
from typing import Any, Dict, List, Optional

import httpx
import structlog
import yaml

logger = structlog.get_logger(__name__)


FIELD_MAP = {
    'system_blocks': 'system',
    'understanding_blocks': 'understanding',
    'dynamic_tools_intro': 'system',
    'plan_blocks': 'planning',
    'planning_tool_specs': 'planning',
    'reflection_blocks': 'reflection',
    'response_blocks': 'response_generation',
    'response_clarification_blocks': 'response_clarification',
    'response_normal_blocks': 'response_normal',
    'tool_planning_blocks': 'tool_planning',
    'response_ack_blocks': 'response_ack',
}

DIRECT_FIELDS = {
    'system',
    'understanding',
    'planning',
    'reflection',
    'response_generation',
    'response_clarification',
    'response_normal',
    'tool_planning',
    'response_ack',
}

REQUIRED_FIELDS = {
    'system': '',
    'understanding': '',
    'planning': '',
    'reflection': '',
    'response_generation': '',
    'response_clarification': '',
    'response_normal': '',
    'tool_planning': '',
    'response_ack': '',
}


class PromptManager:
    """管理不同版本的 AI 提示词配置。"""

    def __init__(self, prompt_file: str = "prompts/family_assistant_prompts.yaml", mcp_url: str | None = None) -> None:
        self.prompt_file = prompt_file
        self.mcp_url = mcp_url or os.getenv('MCP_SERVER_URL', 'http://faa-mcp:8000')
        self.prompts: Dict[str, Dict[str, Any]] = {}
        self.current_version: str = 'v1_basic'
        self._blocks: Dict[str, str] = {}
        self._cached_tools: Optional[List[Dict[str, Any]]] = None
        self._load_prompts()

    # ------------------------------------------------------------------
    # 加载与解析
    # ------------------------------------------------------------------
    def _load_prompts(self) -> None:
        """从 YAML 文件加载 prompt 配置，并处理 blocks 与 profile 覆写。"""
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            prompt_path = os.path.join(project_root, self.prompt_file)

            if not os.path.exists(prompt_path):
                logger.warning("Prompt file missing, falling back to defaults", path=prompt_path)
                self._use_defaults()
                return

            with open(prompt_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}

            raw_prompts = data.get('prompts', {}) or {}
            current = data.get('current', 'v1_basic')
            vars_map = data.get('vars', {}) or {}
            raw_blocks = data.get('blocks', {}) or {}

            def _interpolate(text: str) -> str:
                if not text:
                    return text
                out = text
                for k, v in vars_map.items():
                    out = out.replace(f"{{{{{k}}}}}", str(v))
                return out

            interpolated_blocks = {k: _interpolate(str(v)) for k, v in raw_blocks.items()}
            self._blocks = interpolated_blocks

            composed: Dict[str, Dict[str, Any]] = {}
            cache: Dict[str, Dict[str, str]] = {}

            def _assemble_text(keys: Optional[List[str]]) -> str:
                if not keys:
                    return ''
                parts: List[str] = []
                for key in keys:
                    block = interpolated_blocks.get(key, '').strip()
                    if block:
                        parts.append(block)
                return "\n\n".join(parts).strip()

            processing: set[str] = set()

            def _compose_components(name: str, cfg: Dict[str, Any]) -> Dict[str, str]:
                if name in cache:
                    return deepcopy(cache[name])
                if name in processing:
                    raise ValueError(f"Cyclic prompt inheritance detected: {name}")
                processing.add(name)

                base: Dict[str, str] = {}
                parent_name = cfg.get('inherits')
                if parent_name:
                    parent_cfg = raw_prompts.get(parent_name)
                    if parent_cfg:
                        base = _compose_components(parent_name, parent_cfg)

                base = deepcopy(base)

                for field in DIRECT_FIELDS:
                    if cfg.get(field):
                        base[field] = _interpolate(cfg[field])

                for block_key, field_name in FIELD_MAP.items():
                    block_list = cfg.get(block_key)
                    text = _assemble_text(block_list)
                    if text:
                        base[field_name] = _interpolate(text)

                for field, default in REQUIRED_FIELDS.items():
                    base.setdefault(field, default)

                cache[name] = deepcopy(base)
                processing.remove(name)
                return deepcopy(base)

            for prompt_name, cfg in raw_prompts.items():
                components = _compose_components(prompt_name, cfg)
                profiles_cfg = cfg.get('profiles') or {}
                profile_prompts: Dict[str, Dict[str, str]] = {}
                for profile_name, override_cfg in profiles_cfg.items():
                    override_components = deepcopy(components)

                    for field in DIRECT_FIELDS:
                        if override_cfg.get(field):
                            override_components[field] = _interpolate(override_cfg[field])

                    for block_key, field_name in FIELD_MAP.items():
                        block_list = override_cfg.get(block_key)
                        text = _assemble_text(block_list)
                        if text:
                            override_components[field_name] = _interpolate(text)

                    profile_prompts[profile_name] = override_components

                composed[prompt_name] = {
                    'meta': {
                        'name': cfg.get('name', prompt_name),
                        'description': cfg.get('description', ''),
                    },
                    'components': components,
                    'profiles': profile_prompts,
                }

            if not composed:
                logger.warning("Prompt file has no valid prompt entries, using defaults")
                self._use_defaults()
                return

            self.prompts = composed
            if current in composed:
                self.current_version = current
            else:
                self.current_version = next(iter(composed.keys()))
                logger.warning("Requested prompt version not found, using %s", self.current_version)

            logger.info(
                "Loaded prompt configurations",
                available=list(self.prompts.keys()),
                current=self.current_version,
            )

        except Exception as exc:
            logger.error("Failed to load prompts, using defaults", error=str(exc))
            self._use_defaults()

    def _use_defaults(self) -> None:
        logger.warning("Using minimal fallback prompts - please provide YAML configuration")
        self.prompts = {
            'v1_basic': {
                'meta': {'name': 'fallback', 'description': 'minimal prompt'},
                'components': {
                    'system': '你是一个家庭 AI 助手，帮助记录和检索家庭信息。',
                    'understanding': '请分析用户需求并给出下一步动作。',
                    'planning': '根据上下文输出 {"thought": "...", "action": "...", "tool": "...", "input": {...}, "expected_outcome": "...", "stop": false}',
                    'reflection': '如果上一轮行动失败，请给出新的行动计划或终止理由。',
                    'response_generation': '根据执行结果生成简短确认回复。',
                    'response_clarification': '说明缺少的信息并提出一个问题。',
                    'response_normal': '用温和语气回复用户。',
                    'tool_planning': '根据理解结果给出需要执行的工具步骤，JSON 格式。',
                    'response_ack': '确认任务已完成。',
                },
                'profiles': {},
            }
        }
        self.current_version = 'v1_basic'

    # ------------------------------------------------------------------
    # Prompt 获取
    # ------------------------------------------------------------------
    def _current_entry(self) -> Dict[str, Any]:
        return self.prompts.get(self.current_version, {})

    def _components_for_profile(self, profile: Optional[str] = None) -> Dict[str, str]:
        entry = self._current_entry()
        base = entry.get('components', {})
        if profile:
            profile_map = entry.get('profiles', {}) or {}
            override = profile_map.get(profile)
            if override:
                return override
        return base

    def get_system_prompt(self, profile: Optional[str] = None) -> str:
        """获取系统提示词
        
        现在支持动态版本选择，可以根据 A/B 测试返回不同的 Prompt 版本。
        如果指定了版本（如 v4_experimental），会尝试使用该版本。
        """
        # 检查是否指定了特定版本
        if profile and profile in self.prompts:
            # 直接使用指定的版本
            components = self.prompts[profile].get('components', {})
            return components.get('system', '')
        
        # 使用原有逻辑
        components = self._components_for_profile(profile)
        fallback = self.prompts.get('v1_basic', {}).get('components', {}).get('system', '')
        return components.get('system') or fallback

    def get_understanding_prompt(self, profile: Optional[str] = None) -> str:
        """兼容旧接口，返回理解/规划提示词。"""
        if profile and profile in self.prompts:
            components = self.prompts[profile].get('components', {})
            return components.get('understanding') or components.get('planning', '')
        
        components = self._components_for_profile(profile)
        return components.get('understanding') or components.get('planning', '')

    def get_planning_prompt(self, profile: Optional[str] = None) -> str:
        """获取单回合规划提示词。"""
        if profile and profile in self.prompts:
            components = self.prompts[profile].get('components', {})
            return components.get('planning', '')

        components = self._components_for_profile(profile)
        return components.get('planning', '')

    async def get_planning_prompt_with_tools(self, profile: Optional[str] = None) -> str:
        """获取包含工具规格说明的规划提示词。"""
        base_prompt = self.get_planning_prompt(profile)
        if not base_prompt:
            return base_prompt

        tools = await self._fetch_mcp_tools()
        tool_spec = self._format_tool_spec(tools)
        if '{{DYNAMIC_TOOL_SPECS}}' in base_prompt:
            return base_prompt.replace('{{DYNAMIC_TOOL_SPECS}}', tool_spec)
        return f"{tool_spec}\n\n{base_prompt}" if tool_spec else base_prompt

    def get_reflection_prompt(self, profile: Optional[str] = None) -> str:
        """获取反思/验证提示词。"""
        if profile and profile in self.prompts:
            components = self.prompts[profile].get('components', {})
            return components.get('reflection', '')
        
        components = self._components_for_profile(profile)
        return components.get('reflection', '')

    def get_response_prompt(self, profile: Optional[str] = None) -> str:
        """获取响应生成提示词（支持版本选择）"""
        if profile and profile in self.prompts:
            components = self.prompts[profile].get('components', {})
            return components.get('response_generation', '')
        
        components = self._components_for_profile(profile)
        return components.get('response_generation', '')

    def get_response_clarification_prompt(self, profile: Optional[str] = None) -> str:
        """获取澄清回复提示词（支持版本选择）"""
        if profile and profile in self.prompts:
            components = self.prompts[profile].get('components', {})
            return components.get('response_clarification', '')
        
        components = self._components_for_profile(profile)
        return components.get('response_clarification', '')

    def get_response_normal_prompt(self, profile: Optional[str] = None) -> str:
        components = self._components_for_profile(profile)
        return components.get('response_normal', '')

    def get_tool_planning_prompt(self, profile: Optional[str] = None) -> str:
        """获取工具规划提示词（支持版本选择）"""
        if profile and profile in self.prompts:
            components = self.prompts[profile].get('components', {})
            return components.get('tool_planning', '')
        
        components = self._components_for_profile(profile)
        return components.get('tool_planning', '')

    def get_ack_prompt(self, profile: Optional[str] = None) -> str:
        """获取确认回复提示词（支持版本选择）"""
        if profile and profile in self.prompts:
            components = self.prompts[profile].get('components', {})
            return components.get('response_ack', '')
        
        components = self._components_for_profile(profile)
        return components.get('response_ack', '')

    def get_dynamic_block(self, block_name: str, **kwargs) -> str:
        template = self._blocks.get(block_name, '')
        if not template:
            return ''
        if kwargs:
            try:
                return template.format(**kwargs)
            except Exception as exc:
                logger.error("Failed to format block", block=block_name, error=str(exc))
                return template
        return template

    # ------------------------------------------------------------------
    # 工具信息注入
    # ------------------------------------------------------------------
    async def _fetch_mcp_tools(self) -> List[Dict[str, Any]]:
        if self._cached_tools is not None:
            return self._cached_tools
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.mcp_url}/tools", timeout=5.0)
                resp.raise_for_status()
                data = resp.json() or {}
                tools = data.get('tools', [])
                self._cached_tools = tools
                logger.info("Fetched tools metadata", count=len(tools))
                return tools
        except Exception as exc:
            logger.warning("Failed to fetch tools metadata", error=str(exc))
            return []

    @staticmethod
    def _format_tool_list(tools: List[Dict[str, Any]]) -> str:
        if not tools:
            return "(当前无法获取工具清单，继续按已有知识完成任务。)"
        lines = []
        for tool in tools:
            name = tool.get('name', 'unknown')
            desc = tool.get('description') or ''
            params = tool.get('parameters') or []
            detail = f"- {name}: {desc}".strip()
            if params:
                detail += f" (参数: {', '.join(params)})"
            lines.append(detail)
        return "\n".join(lines)

    @staticmethod
    def _format_tool_spec(tools: List[Dict[str, Any]]) -> str:
        if not tools:
            return "(暂无工具规格详情)"
        lines: List[str] = []
        for tool in tools:
            name = tool.get('name', 'unknown')
            params = tool.get('parameters') or []
            line = f"- {name}({', '.join(params)})" if params else f"- {name}()"
            notes = tool.get('x_notes')
            if notes:
                line += f"\n  提示: {notes}"
            lines.append(line)
        return "\n".join(lines)

    async def get_system_prompt_with_tools(self, profile: Optional[str] = None) -> str:
        base_prompt = self.get_system_prompt(profile)
        tools = await self._fetch_mcp_tools()
        tool_list = self._format_tool_list(tools)
        if '{{DYNAMIC_TOOLS}}' in base_prompt:
            return base_prompt.replace('{{DYNAMIC_TOOLS}}', tool_list)
        return f"{base_prompt}\n\n可用工具概览:\n{tool_list}" if base_prompt else tool_list

    async def get_tool_planning_prompt_with_tools(self, profile: Optional[str] = None) -> str:
        base_prompt = self.get_tool_planning_prompt(profile)
        tools = await self._fetch_mcp_tools()
        tool_spec = self._format_tool_spec(tools)
        if '{{DYNAMIC_TOOL_SPECS}}' in base_prompt:
            return base_prompt.replace('{{DYNAMIC_TOOL_SPECS}}', tool_spec)
        return f"可用工具规格:\n{tool_spec}\n\n{base_prompt}" if base_prompt else tool_spec

    def clear_tools_cache(self) -> None:
        self._cached_tools = None
        logger.info("Cleared MCP tool cache")

    # ------------------------------------------------------------------
    # 管理接口
    # ------------------------------------------------------------------
    def switch_version(self, version: str) -> bool:
        if version in self.prompts:
            self.current_version = version
            logger.info("Switched prompt version", version=version)
            return True
        logger.warning("Prompt version not found", version=version)
        return False

    def list_versions(self) -> Dict[str, Dict[str, str]]:
        return {
            version: dict(entry.get('meta') or {'name': version, 'description': ''})
            for version, entry in self.prompts.items()
        }

    def reload(self) -> None:
        logger.info("Reloading prompt configuration")
        self._cached_tools = None
        self._load_prompts()


prompt_manager = PromptManager()
