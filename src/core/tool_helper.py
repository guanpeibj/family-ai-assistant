"""
MCP 工具辅助模块

将工具相关的复杂逻辑从 AI 引擎中分离出来，提高代码的可维护性。
这个模块专注于工具的元数据管理、能力判断、参数处理等。

设计原则：
1. 工具无关性 - 不依赖具体的工具实现
2. 元数据驱动 - 完全依赖 MCP 工具的元数据进行判断
3. 缓存优化 - 减少对 MCP 服务的频繁调用
"""
import time
import uuid
from typing import Dict, Any, List, Optional, Set, Tuple
import structlog

from .exceptions import ToolNotFoundError, ToolExecutionError, MCPToolError, create_error_context

logger = structlog.get_logger(__name__)


def _looks_like_uuid(value: Optional[str]) -> bool:
    """检查字符串是否为有效的 UUID 格式"""
    if not value or not isinstance(value, str):
        return False
    try:
        uuid.UUID(value)
        return True
    except Exception:
        return False


class ToolCapabilityAnalyzer:
    """工具能力分析器
    
    负责分析和判断 MCP 工具的各种能力和特性，
    避免在主引擎中硬编码工具特性。
    """
    
    def __init__(self):
        # 工具规格缓存
        self._tool_specs_cache: Dict[str, Any] = {
            "data": None, 
            "ts": 0.0, 
            "ttl": 1200.0  # 20分钟缓存
        }
        
    async def get_tool_specs(self, http_client, mcp_url: str) -> Dict[str, Any]:
        """获取 MCP 工具规格并缓存"""
        now = time.time()
        cache = self._tool_specs_cache
        
        # 检查缓存是否有效
        if cache.get('data') and now - float(cache.get('ts', 0)) < cache['ttl']:
            return cache['data']
            
        # 从 MCP 服务获取最新规格
        try:
            resp = await http_client.get(f"{mcp_url}/tools", timeout=3.0)
            resp.raise_for_status()
            data = resp.json()
            
            # 更新缓存
            self._tool_specs_cache = {"data": data, "ts": now, "ttl": cache['ttl']}
            logger.info("tool_specs.updated", tools_count=len(data.get('tools', [])))
            return data
            
        except Exception as e:
            logger.warning("tool_specs.fetch_failed", error=str(e))
            # 返回旧缓存或空结构
            return cache.get('data') or {"tools": []}
    
    async def get_tool_names(self, http_client, mcp_url: str) -> List[str]:
        """获取所有可用工具的名称列表"""
        specs = await self.get_tool_specs(http_client, mcp_url)
        tools = specs.get('tools', [])
        return [tool.get('name') for tool in tools if tool.get('name')]
    
    async def requires_user_id(self, tool_name: str, http_client, mcp_url: str) -> bool:
        """智能判断工具是否需要 user_id 参数
        
        判断依据：
        1. 工具 schema 中是否包含 user_id 字段
        2. 工具能力标识是否包含 uses_database 或 user_scoped
        3. 回退到已知需要 user_id 的工具列表
        """
        try:
            specs = await self.get_tool_specs(http_client, mcp_url)
            tools = specs.get('tools', [])
            
            for tool in tools:
                if tool.get('name') != tool_name:
                    continue
                    
                # 检查输入 schema 中是否有 user_id
                input_schema = tool.get('x_input_schema', {})
                if isinstance(input_schema, dict):
                    properties = input_schema.get('properties', {})
                    if 'user_id' in properties:
                        return True
                
                # 检查能力标识
                capabilities = tool.get('x_capabilities', {})
                if capabilities.get('uses_database') or capabilities.get('user_scoped'):
                    return True
                    
                return False
                
        except Exception:
            pass
        
        # 回退策略：已知需要 user_id 的工具
        known_user_scoped = {
            "store", "search", "aggregate", "get_pending_reminders", 
            "batch_store", "batch_search", "update_memory_fields", "soft_delete"
        }
        return tool_name in known_user_scoped
    
    async def supports_embedding(self, tool_name: str, http_client, mcp_url: str) -> bool:
        """判断工具是否支持向量嵌入"""
        try:
            specs = await self.get_tool_specs(http_client, mcp_url)
            tools = specs.get('tools', [])
            
            for tool in tools:
                if tool.get('name') == tool_name:
                    capabilities = tool.get('x_capabilities', {})
                    return (capabilities.get('uses_vector', False) or 
                           capabilities.get('supports_embedding', False))
                           
        except Exception:
            pass
            
        # 回退策略
        return tool_name in {"store", "search"}
    
    async def get_time_budget(self, tool_name: str, http_client, mcp_url: str) -> float:
        """获取工具的时间预算（秒）"""
        try:
            specs = await self.get_tool_specs(http_client, mcp_url)
            tools = specs.get('tools', [])
            
            for tool in tools:
                if tool.get('name') == tool_name:
                    budget = tool.get('x_time_budget')
                    if isinstance(budget, (int, float)):
                        return float(budget)
                        
        except Exception:
            pass
            
        # 默认时间预算
        defaults = {
            'store': 2.0, 'search': 3.0, 'aggregate': 3.0,
            'schedule_reminder': 2.0, 'get_pending_reminders': 3.0,
            'mark_reminder_sent': 2.0, 'batch_store': 5.0,
            'batch_search': 5.0, 'update_memory_fields': 2.0,
            'soft_delete': 2.0, 'reembed_memories': 5.0,
            'render_chart': 6.0,
        }
        return defaults.get(tool_name, 3.0)
    
    async def get_output_type(self, tool_name: str, http_client, mcp_url: str) -> str:
        """智能判断工具的输出类型"""
        try:
            specs = await self.get_tool_specs(http_client, mcp_url)
            tools = specs.get('tools', [])
            
            for tool in tools:
                if tool.get('name') == tool_name:
                    output_schema = tool.get('x_output_schema', {})
                    if isinstance(output_schema, dict):
                        properties = output_schema.get('properties', {})
                        
                        # 根据输出字段判断类型
                        if 'id' in properties:
                            return 'entity_with_id'
                        elif 'result' in properties or 'groups' in properties:
                            return 'aggregation'
                        elif 'total_amount' in properties or 'category_breakdown' in properties:
                            return 'summary'
                        elif len(properties) > 3:
                            return 'complex'
                        else:
                            return 'simple'
                            
        except Exception:
            pass
            
        # 回退策略
        if tool_name == 'store':
            return 'entity_with_id'
        elif tool_name == 'aggregate':
            return 'aggregation'
        elif 'summary' in tool_name:
            return 'summary'
        else:
            return 'simple'
    
    async def is_simple_operation(self, steps: List[Dict[str, Any]], http_client, mcp_url: str) -> bool:
        """基于工具元数据智能判断是否为简单操作
        
        简单操作的特征：
        1. 时间预算 <= 2.5秒
        2. 延迟等级为 low
        3. 不具备复杂能力标识
        """
        if not steps:
            return True
        
        try:
            specs = await self.get_tool_specs(http_client, mcp_url)
            tools = specs.get('tools', [])
            tool_info = {tool['name']: tool for tool in tools}
        except Exception:
            # 回退策略：保守判断
            known_complex = {"search", "aggregate", "render_chart"}
            return all((s or {}).get('tool') not in known_complex for s in steps)
        
        # 基于元数据智能判断
        for step in steps:
            tool_name = (step or {}).get('tool')
            if not tool_name or tool_name not in tool_info:
                continue
                
            tool = tool_info[tool_name]
            
            # 判断条件（任一满足即为复杂操作）
            
            # 1. 延迟等级为 medium/high
            latency = tool.get('x_latency_hint')
            if latency in ['medium', 'high']:
                return False
                
            # 2. 时间预算 > 2.5秒
            time_budget = tool.get('x_time_budget')
            if isinstance(time_budget, (int, float)) and time_budget > 2.5:
                return False
                
            # 3. 具备复杂能力标识
            capabilities = tool.get('x_capabilities', {})
            complex_capabilities = [
                'supports_group_by', 'supports_filters', 'database_optimized',
                'trend_analysis', 'universal_aggregation'
            ]
            if any(capabilities.get(cap) for cap in complex_capabilities):
                return False
                
        return True


class ToolArgumentProcessor:
    """工具参数处理器
    
    负责处理工具调用的参数准备、上下文引用解析、占位符替换等。
    """
    
    @staticmethod
    def resolve_args_with_context(
        value: Any,
        *,
        context_data: Dict[str, Any],
        last_store_id: Optional[str] = None,
        last_aggregate_result: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """解析工具参数中的上下文引用
        
        支持的引用格式：
        - {"use_context": "context_name", "path": "field.subfield"}
        - "$LAST_STORE_ID" - 上一个存储操作的ID
        - "$LAST_AGGREGATION" - 上一个聚合操作的结果
        """
        if isinstance(value, dict):
            if 'use_context' in value:
                return ToolArgumentProcessor._resolve_context_reference(value, context_data)
            return {
                k: ToolArgumentProcessor.resolve_args_with_context(
                    v, 
                    context_data=context_data,
                    last_store_id=last_store_id,
                    last_aggregate_result=last_aggregate_result
                )
                for k, v in value.items()
            }
        
        if isinstance(value, list):
            return [
                ToolArgumentProcessor.resolve_args_with_context(
                    item,
                    context_data=context_data,
                    last_store_id=last_store_id,
                    last_aggregate_result=last_aggregate_result
                )
                for item in value
            ]
        
        if isinstance(value, str):
            if value == '$LAST_STORE_ID':
                return last_store_id
            if value == '$LAST_AGGREGATION':
                return last_aggregate_result
        
        return value
    
    @staticmethod
    def _resolve_context_reference(ref: Dict[str, Any], context_data: Dict[str, Any]) -> Any:
        """解析上下文引用"""
        context_name = ref.get('use_context')
        if not context_name:
            return ref
            
        source = context_data.get(context_name)
        if source is None:
            return ref.get('fallback')
            
        path = ref.get('path')
        value = ToolArgumentProcessor._extract_from_path(source, path)
        
        return value if value is not None else ref.get('fallback')
    
    @staticmethod
    def _extract_from_path(data: Any, path: Optional[str]) -> Any:
        """从数据中提取指定路径的值"""
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


class ToolExecutionMonitor:
    """工具执行监控器
    
    负责监控工具调用的性能、成功率等指标。
    """
    
    def __init__(self):
        self._call_stats: Dict[str, Dict[str, Any]] = {}
    
    def record_call(self, tool_name: str, duration_ms: int, success: bool):
        """记录工具调用统计"""
        if tool_name not in self._call_stats:
            self._call_stats[tool_name] = {
                'total_calls': 0,
                'success_calls': 0,
                'total_duration_ms': 0,
                'max_duration_ms': 0,
                'min_duration_ms': float('inf')
            }
        
        stats = self._call_stats[tool_name]
        stats['total_calls'] += 1
        if success:
            stats['success_calls'] += 1
        
        stats['total_duration_ms'] += duration_ms
        stats['max_duration_ms'] = max(stats['max_duration_ms'], duration_ms)
        stats['min_duration_ms'] = min(stats['min_duration_ms'], duration_ms)
    
    def get_tool_stats(self, tool_name: str) -> Dict[str, Any]:
        """获取工具统计信息"""
        stats = self._call_stats.get(tool_name, {})
        if not stats:
            return {}
        
        success_rate = stats['success_calls'] / stats['total_calls'] if stats['total_calls'] > 0 else 0
        avg_duration = stats['total_duration_ms'] / stats['total_calls'] if stats['total_calls'] > 0 else 0
        
        return {
            'tool_name': tool_name,
            'total_calls': stats['total_calls'],
            'success_rate': round(success_rate, 3),
            'avg_duration_ms': round(avg_duration, 2),
            'max_duration_ms': stats['max_duration_ms'],
            'min_duration_ms': stats['min_duration_ms'] if stats['min_duration_ms'] != float('inf') else 0
        }
    
    def get_all_stats(self) -> List[Dict[str, Any]]:
        """获取所有工具的统计信息"""
        return [self.get_tool_stats(tool_name) for tool_name in self._call_stats.keys()]
