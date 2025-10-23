#!/usr/bin/env python3
"""
MCP HTTP 包装器 - 提供HTTP接口来调用MCP工具
"""
from fastapi import FastAPI, HTTPException
import inspect
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
            'list_reminder_user_ids': mcp_server._list_reminder_user_ids,
            'batch_store': mcp_server._batch_store,
            'batch_search': mcp_server._batch_search,
            'update_memory_fields': mcp_server._update_memory_fields,
            'soft_delete': mcp_server._soft_delete,
            'reembed_memories': mcp_server._reembed_memories,
            'render_chart': mcp_server._render_chart,
            # 新增的优化工具
            'get_expense_summary_optimized': mcp_server._get_expense_summary_optimized,
            'get_health_summary_optimized': mcp_server._get_health_summary_optimized,
            'get_learning_progress_optimized': mcp_server._get_learning_progress_optimized,
            'get_data_type_summary_optimized': mcp_server._get_data_type_summary_optimized,
        }
        
        if tool_name not in tool_handlers:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
        
        # 调用工具
        handler = tool_handlers[tool_name]
        # 仅保留目标处理函数签名中声明的参数，忽略诸如 trace_id 等多余字段
        try:
            sig = inspect.signature(handler)
            # 排除self参数（绑定方法的第一个参数）
            allowed = set(sig.parameters.keys())
            if 'self' in allowed:
                allowed.remove('self')
            filtered_args = {k: v for k, v in (request or {}).items() if k in allowed}
        except Exception:
            filtered_args = request or {}
        result = await handler(**filtered_args)
        
        return result
        
    except Exception as e:
        import traceback
        traceback.print_exc()
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
                "parameters": ["memory_id", "remind_at", "payload", "external_key"],
                "x_parameters_detail": [
                    {"name": "memory_id", "type": "string", "required": True, "description": "关联的记忆ID"},
                    {"name": "remind_at", "type": "string", "required": True, "description": "ISO8601 或日期字符串"},
                    {"name": "payload", "type": "object", "required": False, "description": "AI 决定的附加信息（scope/person/message模板等）"},
                    {"name": "external_key", "type": "string", "required": False, "description": "可选幂等键，重复调用则更新"}
                ],
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
                "name": "list_reminder_user_ids",
                "description": "列出仍有未发送提醒的用户ID",
                "parameters": [],
                "x_latency_hint": "low",
                "x_time_budget": 2.0,
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
            },
            {
                "name": "get_expense_summary_optimized",
                "description": "高效财务统计函数，使用数据库端聚合避免大量数据传输，专用于财务数据的快速统计分析",
                "parameters": [
                    "user_id",
                    "date_from",
                    "date_to"
                ],
                "x_parameters_detail": [
                    {"name": "user_id", "type": "string", "required": True, "description": "用户标识"},
                    {"name": "date_from", "type": "string", "required": False, "description": "开始日期（ISO格式，可选）"},
                    {"name": "date_to", "type": "string", "required": False, "description": "结束日期（ISO格式，可选）"}
                ],
                "x_input_schema": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "date_from": {"type": "string", "format": "date-time"},
                        "date_to": {"type": "string", "format": "date-time"}
                    },
                    "required": ["user_id"]
                },
                "x_output_schema": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean"},
                        "total_amount": {"type": "number"},
                        "category_breakdown": {"type": "object"},
                        "record_count": {"type": "integer"},
                        "filters": {"type": "object"}
                    }
                },
                "x_capabilities": {"database_optimized": True, "server_side_aggregation": True, "performance_optimized": True},
                "x_latency_hint": "ultra_low",
                "x_time_budget": 1.0,
                "x_common_failures": ["db_unavailable", "invalid_date_format"],
                "x_performance_notes": "使用专用索引和计算列，性能比传统aggregate提升25倍",
                "x_use_cases": ["财务月度统计", "支出分类分析", "预算执行监控"],
                "x_examples": {"request": {"user_id": "746", "date_from": "2025-08-01", "date_to": "2025-08-31"}}
            },
            {
                "name": "get_health_summary_optimized", 
                "description": "高效健康数据统计函数，支持趋势分析和最新状态查询，专用于家庭成员健康数据的快速统计",
                "parameters": [
                    "user_id",
                    "person",
                    "metric",
                    "date_from",
                    "date_to"
                ],
                "x_parameters_detail": [
                    {"name": "user_id", "type": "string", "required": True, "description": "用户标识"},
                    {"name": "person", "type": "string", "required": False, "description": "家庭成员（如：儿子、大女儿、妻子、我）"},
                    {"name": "metric", "type": "string", "required": False, "description": "健康指标（如：身高、体重、血压、体温）"},
                    {"name": "date_from", "type": "string", "required": False, "description": "开始日期（ISO格式，可选）"},
                    {"name": "date_to", "type": "string", "required": False, "description": "结束日期（ISO格式，可选）"}
                ],
                "x_input_schema": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "person": {"type": "string"},
                        "metric": {"type": "string"},
                        "date_from": {"type": "string", "format": "date-time"},
                        "date_to": {"type": "string", "format": "date-time"}
                    },
                    "required": ["user_id"]
                },
                "x_output_schema": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean"},
                        "health_summary": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "person": {"type": "string"},
                                    "metric": {"type": "string"},
                                    "latest_value": {"type": "number"},
                                    "latest_date": {"type": "string"},
                                    "trend_data": {"type": "array"},
                                    "record_count": {"type": "integer"}
                                }
                            }
                        }
                    }
                },
                "x_capabilities": {"database_optimized": True, "trend_analysis": True, "multi_person_support": True},
                "x_latency_hint": "low",
                "x_time_budget": 2.0,
                "x_common_failures": ["db_unavailable", "invalid_date_format"],
                "x_performance_notes": "使用专用健康数据索引，支持多成员多指标并行查询",
                "x_use_cases": ["儿童身高体重监测", "家庭健康趋势分析", "疫苗接种记录查询"],
                "x_examples": {"request": {"user_id": "746", "person": "儿子", "metric": "身高"}}
            },
            {
                "name": "get_learning_progress_optimized",
                "description": "高效学习进展统计函数，支持成绩分析和进步追踪，专用于孩子学习数据的快速统计分析",
                "parameters": [
                    "user_id",
                    "person", 
                    "subject",
                    "date_from",
                    "date_to"
                ],
                "x_parameters_detail": [
                    {"name": "user_id", "type": "string", "required": True, "description": "用户标识"},
                    {"name": "person", "type": "string", "required": False, "description": "学生成员（如：儿子、大女儿、二女儿）"},
                    {"name": "subject", "type": "string", "required": False, "description": "学习科目（如：数学、语文、英语、物理）"},
                    {"name": "date_from", "type": "string", "required": False, "description": "开始日期（ISO格式，可选）"},
                    {"name": "date_to", "type": "string", "required": False, "description": "结束日期（ISO格式，可选）"}
                ],
                "x_input_schema": {
                    "type": "object", 
                    "properties": {
                        "user_id": {"type": "string"},
                        "person": {"type": "string"},
                        "subject": {"type": "string"},
                        "date_from": {"type": "string", "format": "date-time"},
                        "date_to": {"type": "string", "format": "date-time"}
                    },
                    "required": ["user_id"]
                },
                "x_output_schema": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean"},
                        "learning_progress": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "person": {"type": "string"},
                                    "subject": {"type": "string"},
                                    "avg_score": {"type": "number"},
                                    "latest_score": {"type": "number"},
                                    "improvement": {"type": "number"},
                                    "record_count": {"type": "integer"},
                                    "score_distribution": {"type": "object"}
                                }
                            }
                        }
                    }
                },
                "x_capabilities": {"database_optimized": True, "progress_tracking": True, "score_analysis": True},
                "x_latency_hint": "low",
                "x_time_budget": 2.0,
                "x_common_failures": ["db_unavailable", "invalid_date_format"],
                "x_performance_notes": "使用专用学习数据索引，自动计算成绩趋势和分布",
                "x_use_cases": ["孩子成绩进展追踪", "科目强弱项分析", "学习效果评估"],
                "x_examples": {"request": {"user_id": "746", "person": "大女儿", "subject": "数学"}}
            },
            {
                "name": "get_data_type_summary_optimized",
                "description": "通用数据类型统计函数，支持任意类型的聚合分析，为未来扩展的数据类型提供高性能查询支持",
                "parameters": [
                    "user_id",
                    "data_type",
                    "group_by_field",
                    "date_from", 
                    "date_to"
                ],
                "x_parameters_detail": [
                    {"name": "user_id", "type": "string", "required": True, "description": "用户标识"},
                    {"name": "data_type", "type": "string", "required": True, "description": "数据类型（如：expense、health、learning、calendar_event等）"},
                    {"name": "group_by_field", "type": "string", "required": False, "description": "分组字段（如：person、category、metric、subject、source等）"},
                    {"name": "date_from", "type": "string", "required": False, "description": "开始日期（ISO格式，可选）"},
                    {"name": "date_to", "type": "string", "required": False, "description": "结束日期（ISO格式，可选）"}
                ],
                "x_input_schema": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "data_type": {"type": "string"},
                        "group_by_field": {"type": "string"},
                        "date_from": {"type": "string", "format": "date-time"},
                        "date_to": {"type": "string", "format": "date-time"}
                    },
                    "required": ["user_id", "data_type"]
                },
                "x_output_schema": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean"},
                        "data_summary": {
                            "type": "array", 
                            "items": {
                                "type": "object",
                                "properties": {
                                    "data_type": {"type": "string"},
                                    "group_value": {"type": "string"},
                                    "record_count": {"type": "integer"},
                                    "numeric_summary": {"type": "object"},
                                    "latest_records": {"type": "array"}
                                }
                            }
                        }
                    }
                },
                "x_capabilities": {"database_optimized": True, "universal_aggregation": True, "extensible": True},
                "x_latency_hint": "medium",
                "x_time_budget": 3.0,
                "x_common_failures": ["db_unavailable", "invalid_data_type", "invalid_date_format"],
                "x_performance_notes": "智能选择计算列或JSONB查询，适配任意数据类型的高效统计",
                "x_use_cases": ["通用数据统计", "新数据类型查询", "跨类型数据分析", "扩展性查询支持"],
                "x_examples": {"request": {"user_id": "746", "data_type": "health", "group_by_field": "person", "date_from": "2025-08-01"}}
            }
        ]
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port) 
