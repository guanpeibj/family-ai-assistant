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

# 初始化MCP服务器
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
            'mark_reminder_sent': mcp_server._mark_reminder_sent
        }
        
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
    return {
        "tools": [
            {
                "name": "store",
                "description": "存储任何 AI 认为需要记住的信息",
                "parameters": ["content", "ai_data", "user_id"]
            },
            {
                "name": "search",
                "description": "搜索相关记忆，支持语义和精确查询",
                "parameters": ["query", "user_id", "filters"]
            },
            {
                "name": "aggregate",
                "description": "对数据进行聚合统计",
                "parameters": ["user_id", "operation", "field", "filters"]
            },
            {
                "name": "schedule_reminder",
                "description": "为某个记忆设置提醒",
                "parameters": ["memory_id", "remind_at"]
            },
            {
                "name": "get_pending_reminders",
                "description": "获取待发送的提醒",
                "parameters": ["user_id"]
            },
            {
                "name": "mark_reminder_sent",
                "description": "标记提醒为已发送",
                "parameters": ["reminder_id"]
            }
        ]
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port) 