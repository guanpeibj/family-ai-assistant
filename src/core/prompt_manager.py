"""
Prompt版本管理器 - 支持动态加载和切换prompt版本
"""
import yaml
import os
from typing import Dict, Any, Optional, List
import json
import structlog
import httpx
import asyncio

logger = structlog.get_logger(__name__)


class PromptManager:
    """管理不同版本的AI提示词"""
    
    def __init__(self, prompt_file: str = "prompts/family_assistant_prompts.yaml", mcp_url: str = None):
        self.prompt_file = prompt_file
        self.prompts: Dict[str, Any] = {}
        self.current_version: str = "v1_basic"
        self.mcp_url = mcp_url or os.getenv('MCP_SERVER_URL', 'http://faa-mcp:8000')
        self._cached_tools: Optional[List[Dict[str, Any]]] = None
        self._load_prompts()
    
    def _load_prompts(self):
        """从YAML文件加载prompts（支持 blocks/inherits/vars 拼装）。"""
        try:
            # 获取项目根目录
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            prompt_path = os.path.join(project_root, self.prompt_file)
            
            if not os.path.exists(prompt_path):
                logger.warning(f"Prompt file not found: {prompt_path}, using defaults")
                self._use_defaults()
                return
            
            with open(prompt_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}

            raw_prompts = data.get('prompts', {}) or {}
            current = data.get('current', 'v1_basic')
            vars_map = data.get('vars', {}) or {}
            blocks = data.get('blocks', {}) or {}

            def _assemble_text(block_keys: list[str] | None, fallback_key: str | None = None) -> str:
                if block_keys and isinstance(block_keys, list):
                    parts: list[str] = []
                    for k in block_keys:
                        txt = blocks.get(k, '')
                        if txt:
                            parts.append(str(txt).strip())
                    return "\n\n".join(parts).strip()
                if fallback_key and blocks.get(fallback_key):
                    return str(blocks[fallback_key]).strip()
                return ''

            def _interpolate(text: str) -> str:
                # 极简模板替换：{{KEY}} -> vars_map[KEY]
                if not text:
                    return text
                out = text
                for k, v in vars_map.items():
                    out = out.replace(f"{{{{{k}}}}}", str(v))
                return out

            assembled: dict[str, dict[str, str]] = {}
            # 先浅复制原 prompts，用于兼容旧结构
            for name, cfg in raw_prompts.items():
                assembled[name] = {
                    'system': cfg.get('system', ''),
                    'understanding': cfg.get('understanding', ''),
                    'response_generation': cfg.get('response_generation', ''),
                    'response_clarification': cfg.get('response_clarification', ''),
                    'response_normal': cfg.get('response_normal', ''),
                    'tool_planning': cfg.get('tool_planning', ''),
                }
            # 处理 blocks/inherits 结构
            for name, cfg in raw_prompts.items():
                parent = cfg.get('inherits')
                base = dict(assembled.get(parent, {})) if parent else {}
                # 按 blocks 列表拼接
                sys_txt = _assemble_text(cfg.get('system_blocks'), None)
                und_txt = _assemble_text(cfg.get('understanding_blocks'), None)
                rsp_txt = _assemble_text(cfg.get('response_blocks'), None)
                rsp_clar_txt = _assemble_text(cfg.get('response_clarification_blocks'), None)
                rsp_norm_txt = _assemble_text(cfg.get('response_normal_blocks'), None)
                tpl_txt = _assemble_text(cfg.get('tool_planning_blocks'), None)
                if sys_txt:
                    base['system'] = sys_txt
                if und_txt:
                    base['understanding'] = und_txt
                if rsp_txt:
                    base['response_generation'] = rsp_txt
                if rsp_clar_txt:
                    base['response_clarification'] = rsp_clar_txt
                if rsp_norm_txt:
                    base['response_normal'] = rsp_norm_txt
                if tpl_txt:
                    base['tool_planning'] = tpl_txt
                # 模板变量替换
                for k in list(base.keys()):
                    base[k] = _interpolate(base.get(k, ''))
                assembled[name] = base

            self.prompts = assembled
            self.current_version = current if current in self.prompts else 'v1_basic'
            if self.current_version != current:
                logger.warning(f"Current version {current} not found, fallback to v1_basic")
            logger.info(f"Loaded prompt version: {self.current_version}")
            logger.info(f"current prompts: {self.prompts}")

        except Exception as e:
            logger.error(f"Error loading prompts: {e}")
            self._use_defaults()
    
    def _use_defaults(self):
        """当YAML文件不可用时，使用最小化的兜底prompts"""
        logger.warning("Using minimal fallback prompts - YAML configuration recommended")
        self.prompts = {
            'v1_basic': {
                'name': '兜底版本',
                'system': '你是一个家庭AI助手，帮助管理家庭事务。请查阅数据库获取家庭成员信息。',
                'understanding': '',
                'response_generation': '',
                'tool_planning': '根据理解结果决定使用哪些工具。输出 JSON: {"steps": [{"tool": "store", "args": {...}}]}',
            }
        }
        self.current_version = 'v1_basic'
    
    def get_system_prompt(self) -> str:
        """获取当前版本的系统提示词"""
        current = self.prompts.get(self.current_version, {})
        return current.get('system', self.prompts['v1_basic']['system'])
    
    def get_understanding_prompt(self) -> str:
        """获取消息理解的提示词"""
        current = self.prompts.get(self.current_version, {})
        return current.get('understanding', '')
    
    def get_response_prompt(self) -> str:
        """获取回复生成的提示词"""
        current = self.prompts.get(self.current_version, {})
        return current.get('response_generation', '')
    
    def get_response_clarification_prompt(self) -> str:
        """获取澄清询问专用提示词（如定义）"""
        current = self.prompts.get(self.current_version, {})
        return current.get('response_clarification', '')
    
    def get_response_normal_prompt(self) -> str:
        """获取正常回复专用提示词（如定义）"""
        current = self.prompts.get(self.current_version, {})
        return current.get('response_normal', '')
    
    def get_tool_planning_prompt(self) -> str:
        """获取工具编排提示词"""
        current = self.prompts.get(self.current_version, {})
        return current.get('tool_planning', '')
    
    def get_dynamic_prompt(self, prompt_name: str, **kwargs) -> str:
        """获取动态格式化的提示词"""
        # 从 blocks 中获取指定的 prompt 模板
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            prompt_path = os.path.join(project_root, self.prompt_file)
            
            if not os.path.exists(prompt_path):
                return ""
            
            with open(prompt_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            
            blocks = data.get('blocks', {}) or {}
            template = blocks.get(prompt_name, '')
            
            if template and kwargs:
                return template.format(**kwargs)
            return template
            
        except Exception as e:
            logger.error(f"Error getting dynamic prompt {prompt_name}: {e}")
            return ""
    
    def get_message_understanding_prompt(self, **kwargs) -> str:
        """获取消息理解提示词"""
        return self.get_dynamic_prompt('message_understanding', **kwargs)
    
    def get_clarification_task_prompt(self, **kwargs) -> str:
        """获取澄清任务提示词"""
        return self.get_dynamic_prompt('clarification_response_task', **kwargs)
    
    def get_clarification_user_prompt(self, **kwargs) -> str:
        """获取澄清用户提示词"""
        return self.get_dynamic_prompt('clarification_user_prompt', **kwargs)
    
    def get_normal_task_prompt(self, **kwargs) -> str:
        """获取正常回复任务提示词"""
        return self.get_dynamic_prompt('normal_response_task', **kwargs)
    
    def get_normal_user_prompt(self, **kwargs) -> str:
        """获取正常回复用户提示词"""
        return self.get_dynamic_prompt('normal_response_user_prompt', **kwargs)

    def get_followup_classifier_prompts(self, *, payload: dict) -> tuple[str, str]:
        """获取跟进分类器的 system/user 提示词。"""
        system = self.get_dynamic_prompt('followup_classifier_system')
        # 将 payload 序列化注入 user prompt
        user = self.get_dynamic_prompt('followup_classifier_user', payload=json.dumps(payload, ensure_ascii=False))
        return system, user
    
    async def _fetch_mcp_tools(self) -> List[Dict[str, Any]]:
        """从 MCP server 获取可用工具列表"""
        if self._cached_tools is not None:
            return self._cached_tools
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.mcp_url}/tools", timeout=5.0)
                response.raise_for_status()
                data = response.json()
                tools = data.get('tools', [])
                self._cached_tools = tools
                logger.info(f"Fetched {len(tools)} tools from MCP server")
                return tools
        except Exception as e:
            logger.warning(f"Failed to fetch tools from MCP server: {e}")
            return []
    
    def _format_tool_list(self, tools: List[Dict[str, Any]]) -> str:
        """格式化工具列表为 prompt 文本"""
        if not tools:
            return (
                "工具列表获取失败，请检查 MCP server 连接。\n"
                "降级指引：\n"
                "- 查询：尽量使用 filters.limit + 日期范围；无法获取向量则退化到 trigram 或时间排序。\n"
                "- 统计：优先尝试 aggregate；报错时使用 search 拉取样本给出定性总结。\n"
                "- 存储/提醒：确保关键信息齐全后再调用，缺失即先澄清。"
            )
        
        lines = []
        for tool in tools:
            name = tool.get('name', 'unknown')
            desc = tool.get('description', '')
            params = tool.get('parameters', [])
            latency = tool.get('x_latency_hint')
            time_budget = tool.get('x_time_budget')
            idempotent = (tool.get('x_capabilities') or {}).get('idempotent')
            
            # 格式化参数列表
            if params:
                param_str = ', '.join(params)
                meta = []
                if latency:
                    meta.append(f"延迟:{latency}")
                if isinstance(time_budget, (int, float)):
                    meta.append(f"预算:{time_budget}s")
                if idempotent is not None:
                    meta.append(f"幂等:{'是' if idempotent else '否'}")
                meta_str = f" [{' | '.join(meta)}]" if meta else ''
                lines.append(f"- {name}: {desc} (参数: {param_str}){meta_str}")
            else:
                lines.append(f"- {name}: {desc}")
        
        return '\n'.join(lines)
    
    def _format_tool_specification(self, tools: List[Dict[str, Any]]) -> str:
        """格式化详细的工具规格说明"""
        if not tools:
            return "工具规格获取失败，请检查 MCP server 连接"
        
        lines = []
        for tool in tools:
            name = tool.get('name', 'unknown')
            params = tool.get('parameters', [])
            failures = tool.get('x_common_failures') or []
            notes = tool.get('x_notes')
            
            if params:
                param_str = '{' + ', '.join(params) + '}'
                lines.append(f"- {name}(args: {param_str})")
            else:
                lines.append(f"- {name}()")
            if failures:
                lines.append(f"  常见失败: {', '.join(failures)}")
            if notes:
                lines.append(f"  说明: {notes}")
        
        return '\n'.join(lines)
    
    async def get_system_prompt_with_tools(self) -> str:
        """获取包含动态工具信息的系统提示词"""
        base_prompt = self.get_system_prompt()
        
        # 获取工具信息
        tools = await self._fetch_mcp_tools()
        tool_list = self._format_tool_list(tools)
        
        # 替换工具列表占位符
        if '{{DYNAMIC_TOOLS}}' in base_prompt:
            return base_prompt.replace('{{DYNAMIC_TOOLS}}', tool_list)
        
        # 如果没有占位符，直接在末尾添加
        return base_prompt + f"\n\n你有以下工具可以使用：\n{tool_list}"
    
    async def get_tool_planning_prompt_with_tools(self) -> str:
        """获取包含动态工具信息的工具编排提示词"""
        base_prompt = self.get_tool_planning_prompt()
        
        # 获取工具信息
        tools = await self._fetch_mcp_tools()
        tool_spec = self._format_tool_specification(tools)
        
        # 替换工具规格占位符
        if '{{DYNAMIC_TOOL_SPECS}}' in base_prompt:
            return base_prompt.replace('{{DYNAMIC_TOOL_SPECS}}', tool_spec)
        
        # 如果没有占位符，直接在开头添加
        return f"可用工具：\n{tool_spec}\n\n{base_prompt}"
    
    def clear_tools_cache(self):
        """清除工具缓存，强制重新获取"""
        self._cached_tools = None
        logger.info("Cleared tools cache")
    
    def switch_version(self, version: str) -> bool:
        """切换到指定版本的prompt"""
        if version in self.prompts:
            self.current_version = version
            logger.info(f"Switched to prompt version: {version}")
            return True
        else:
            logger.warning(f"Prompt version not found: {version}")
            return False
    
    def list_versions(self) -> Dict[str, Dict[str, str]]:
        """列出所有可用的prompt版本"""
        return {
            version: {
                'name': data.get('name', version),
                'description': data.get('description', '')
            }
            for version, data in self.prompts.items()
        }
    
    def reload(self):
        """重新加载prompt配置"""
        logger.info("Reloading prompt configuration")
        self._load_prompts()


# 全局实例
prompt_manager = PromptManager() 