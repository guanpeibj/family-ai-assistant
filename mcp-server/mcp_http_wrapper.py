#!/usr/bin/env python3
"""
MCP HTTP 包装器 - 提供HTTP接口来调用MCP工具
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
import os
import sys

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from generic_mcp_server import GenericMCPServer

app = FastAPI(title="MCP HTTP Wrapper")

# 初始化MCP服务器（HTTP模式不需要 MCP 的 Server/tool 装饰器）
mcp_server = GenericMCPServer()


class ToolCallRequest(BaseModel):
    """工具调用请求模型"""
    # 动态参数，由具体工具决定
    class Config:
        extra = "allow"


@app.on_event("startup")
async def startup_event():
    """启动时初始化MCP服务器"""
    await mcp_server.initialize()


@app.on_event("shutdown")
async def shutdown_event():
    """关闭时清理资源"""
    await mcp_server.close()


@app.get("/health")
async def health():
    """健康检查端点"""
    return {"status": "healthy", "service": "mcp-http-wrapper"}


@app.post("/tool/{tool_name}")
async def call_tool(tool_name: str, request: Dict[str, Any]):
    """调用MCP工具"""
    try:
        # 获取工具处理函数
        tool_handlers = {
            'store': mcp_server._store,
            'search': mcp_server._search,
            'aggregate': mcp_server._aggregate,
            'schedule_reminder': mcp_server._schedule_reminder,
            'get_pending_reminders': mcp_server._get_pending_reminders,
            'mark_reminder_sent': mcp_server._mark_reminder_sent,
            'batch_store': mcp_server._batch_store,
            'batch_search': mcp_server._batch_search,
            'update_memory_fields': mcp_server._update_memory_fields,
            'soft_delete': mcp_server._soft_delete,
            'reembed_memories': mcp_server._reembed_memories
        }
        
        # 动态扩展：render_chart
        if tool_name == 'render_chart':
            return await mcp_server._render_chart(**request)
        if tool_name not in tool_handlers:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
        
        # 调用工具
        handler = tool_handlers[tool_name]
        result = await handler(**request)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tools")
async def list_tools():
    """列出可用的工具"""
    from datetime import datetime
    version = os.getenv("MCP_TOOLS_VERSION", "v1.1")
    generated_at = datetime.utcnow().isoformat() + "Z"
    return {
        "version": version,
        "generated_at": generated_at,
        "tools": [
            {
                "name": "store",
                "description": "存储任何 AI 认为需要记住的信息（可选 embedding 向量）",
                "parameters": [
                    "content",        # 原始内容
                    "ai_data",        # AI 理解的所有结构化信息（JSON）
                    "user_id",        # 用户标识（UUID或任意字符串，将稳定映射UUID）
                    "embedding"       # 可选，内容向量（list[float]或"[x,y,...]")
                ],
                "x_parameters_detail": [
                    {"name": "content", "type": "string", "required": True, "description": "原始文本内容", "examples": ["今天买菜花了50元"]},
                    {"name": "ai_data", "type": "object", "required": True, "description": "AI理解的结构化JSON（可包含 intent/entities/occurred_at 等）"},
                    {"name": "user_id", "type": "string", "required": True, "description": "用户标识；非UUID会被稳定映射为UUID"},
                    {"name": "embedding", "type": "array|string", "required": False, "description": "内容向量；list[float] 或已格式化的 \"[x,y,...]\" 文本"}
                ],
                "x_input_schema": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "ai_data": {"type": "object"},
                        "user_id": {"type": "string"},
                        "embedding": {"oneOf": [{"type": "array", "items": {"type": "number"}}, {"type": "string"}]}
                    },
                    "required": ["content", "ai_data", "user_id"]
                },
                "x_output_schema": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean"},
                        "id": {"type": "string"},
                        "message": {"type": "string"},
                        "error": {"type": "string"}
                    }
                },
                "x_capabilities": {"uses_vector": True, "idempotent": False, "batch_supported": True},
                "x_latency_hint": "low",
                "x_time_budget": 2.0,
                "x_common_failures": ["db_unavailable", "invalid_embedding_format"],
                "x_limits": {"notes": "embedding维度需与数据库向量维度一致"},
                "x_examples": {"request": {"content": "今天买菜花了50元", "ai_data": {"intent": "record_expense", "amount": 50}, "user_id": "userA"}}
            },
            {
                "name": "search",
                "description": "搜索相关记忆，支持语义（向量）与精确过滤。当无向量时降级为 trigram 相似匹配或时间排序。",
                "parameters": [
                    "query",           # 查询文本（可选，用于 trigram）
                    "user_id",         # 用户标识
                    "filters",         # 可选: date_from/date_to/min_amount/max_amount/thread_id/type/channel/limit/jsonb_equals
                    "query_embedding"  # 可选，查询向量（list[float]或"[x,y,...]")
                ],
                "x_parameters_detail": [
                    {"name": "query", "type": "string", "required": False, "description": "查询文本；未提供向量时用于trigram相似匹配"},
                    {"name": "user_id", "type": "string", "required": True, "description": "用户标识"},
                    {"name": "filters", "type": "object", "required": False, "description": "过滤条件：date_from/date_to/min_amount/max_amount/thread_id/type/channel/limit/jsonb_equals"},
                    {"name": "query_embedding", "type": "array|string", "required": False, "description": "查询向量；提供则执行向量相似检索"}
                ],
                "x_input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "user_id": {"type": "string"},
                        "filters": {"type": "object", "properties": {
                            "date_from": {"type": "string"},
                            "date_to": {"type": "string"},
                            "min_amount": {"type": "number"},
                            "max_amount": {"type": "number"},
                            "thread_id": {"type": "string"},
                            "type": {"type": "string"},
                            "channel": {"type": "string"},
                            "limit": {"type": "integer"},
                            "jsonb_equals": {"type": "object"},
                            "shared_thread": {"type": "boolean"}
                        }},
                        "query_embedding": {"oneOf": [{"type": "array", "items": {"type": "number"}}, {"type": "string"}]}
                    },
                    "required": ["user_id"]
                },
                "x_output_schema": {
                    "type": "array",
                    "items": {"type": "object"}
                },
                "x_notes": "返回数组最后包含 _meta 对象，含 used_vector/used_trigram/limit/applied_filters/shared_thread_mode/returned。shared_thread 模式必须提供 thread_id，且 limit 会被强制上限（30）。jsonb_equals 走 JSONB 包含 @> 查询。",
                "x_capabilities": {"uses_vector": True, "supports_trigram": True, "supports_filters": True, "batch_supported": True},
                "x_latency_hint": "medium",
                "x_time_budget": 3.0,
                "x_common_failures": ["invalid_filter", "db_unavailable", "timeout"],
                "x_limits": {"limit_max": 200},
                "x_error_codes": ["invalid_filter", "db_unavailable"],
                "x_examples": {"request": {"query": "餐饮 本月", "user_id": "userA", "filters": {"date_from": "2025-01-01T00:00:00", "date_to": "2025-01-31T23:59:59"}}}
            },
            {
                "name": "aggregate",
                "description": "对数据进行聚合统计，支持时间分组与按任意 ai_understanding 字段分组",
                "parameters": [
                    "user_id",          # 用户标识
                    "operation",        # sum/count/avg/min/max
                    "field",            # 对于 count 可为 null
                    "filters"           # 可选: date_from/date_to/jsonb_equals/group_by(day|week|month)/group_by_ai_field
                ],
                "x_parameters_detail": [
                    {"name": "user_id", "type": "string", "required": True},
                    {"name": "operation", "type": "string", "enum": ["sum", "count", "avg", "min", "max"], "required": True},
                    {"name": "field", "type": "string|null", "required": False, "description": "count 可为 null；其他需指定列名，如 amount"},
                    {"name": "filters", "type": "object", "required": False, "description": "支持 group_by 与 group_by_ai_field"}
                ],
                "x_output_schema": {
                    "type": "object",
                    "properties": {
                        "operation": {"type": "string"},
                        "field": {"type": ["string", "null"]},
                        "result": {"type": "number"},
                        "groups": {"type": "array"},
                        "_meta": {"type": "object"}
                    }
                },
                "x_capabilities": {"supports_group_by": True},
                "x_latency_hint": "medium",
                "x_time_budget": 3.0,
                "x_common_failures": ["invalid_filter", "field_missing", "db_unavailable", "timeout"],
                "x_examples": {"request": {"user_id": "userA", "operation": "sum", "field": "amount", "filters": {"group_by": "month"}}}
            },
            {
                "name": "schedule_reminder",
                "description": "为某个记忆设置提醒",
                "parameters": ["memory_id", "remind_at"],
                "x_latency_hint": "low",
                "x_time_budget": 2.0,
                "x_common_failures": ["invalid_memory_id", "time_format_error", "db_unavailable"]
            },
            {
                "name": "get_pending_reminders",
                "description": "获取待发送的提醒",
                "parameters": ["user_id"],
                "x_latency_hint": "low",
                "x_time_budget": 3.0,
                "x_common_failures": ["db_unavailable"]
            },
            {
                "name": "mark_reminder_sent",
                "description": "标记提醒为已发送",
                "parameters": ["reminder_id"],
                "x_latency_hint": "low",
                "x_time_budget": 2.0,
                "x_common_failures": ["invalid_reminder_id", "db_unavailable"]
            },
            {
                "name": "render_chart",
                "description": "渲染图表为PNG，返回文件路径（M2）",
                "parameters": [
                    "type",     # line/bar/pie
                    "title",
                    "x",        # 类目或时间字符串数组
                    "series",   # [{name, y: number[]}] 
                    "style"     # 可选主题/颜色/尺寸
                ],
                "x_parameters_detail": [
                    {"name": "type", "type": "string", "enum": ["line", "bar", "pie"], "required": True},
                    {"name": "title", "type": "string", "required": False},
                    {"name": "x", "type": "array", "required": True},
                    {"name": "series", "type": "array", "required": True},
                    {"name": "style", "type": "object", "required": False}
                ],
                "x_latency_hint": "high",
                "x_time_budget": 6.0,
                "x_common_failures": ["matplotlib_error", "fs_unwritable"]
            },
            {
                "name": "batch_store",
                "description": "批量存储记忆。每项: {content, ai_data, user_id, embedding?}",
                "parameters": ["memories"],
                "x_parameters_detail": [
                    {"name": "memories", "type": "array", "required": True, "description": "数组元素为 store 的输入对象"}
                ],
                "x_capabilities": {"batch_supported": True, "uses_vector": True},
                "x_latency_hint": "medium",
                "x_time_budget": 5.0,
                "x_common_failures": ["db_unavailable", "invalid_embedding_format"]
            },
            {
                "name": "batch_search",
                "description": "批量搜索。每项: {query, user_id, filters?, query_embedding?}",
                "parameters": ["queries"],
                "x_parameters_detail": [
                    {"name": "queries", "type": "array", "required": True, "description": "数组元素为 search 的输入对象"}
                ],
                "x_capabilities": {"batch_supported": True},
                "x_latency_hint": "medium",
                "x_time_budget": 5.0,
                "x_common_failures": ["invalid_filter", "db_unavailable", "timeout"]
            },
            {
                "name": "update_memory_fields",
                "description": "更新记忆的部分字段：content/amount/occurred_at/embedding/ai_understanding(浅合并)",
                "parameters": ["memory_id", "fields"],
                "x_parameters_detail": [
                    {"name": "memory_id", "type": "string", "required": True},
                    {"name": "fields", "type": "object", "required": True}
                ],
                "x_latency_hint": "low",
                "x_time_budget": 2.0,
                "x_common_failures": ["invalid_memory_id", "invalid_field", "db_unavailable"]
            },
            {
                "name": "soft_delete",
                "description": "软删除记忆（ai_understanding.deleted=true）",
                "parameters": ["memory_id"],
                "x_parameters_detail": [
                    {"name": "memory_id", "type": "string", "required": True}
                ],
                "x_latency_hint": "low",
                "x_time_budget": 2.0,
                "x_common_failures": ["invalid_memory_id", "db_unavailable"]
            },
            {
                "name": "reembed_memories",
                "description": "列出需要重嵌的记忆（由引擎生成向量后再回填）",
                "parameters": ["filters"],
                "x_parameters_detail": [
                    {"name": "filters", "type": "object", "required": False, "description": "embedding_missing/date_from/date_to/jsonb_equals/limit"}
                ],
                "x_capabilities": {"uses_vector": False, "batch_supported": False},
                "x_latency_hint": "low",
                "x_time_budget": 5.0,
                "x_common_failures": ["db_unavailable"]
            }
        ]
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port) 