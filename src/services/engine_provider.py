"""统一的 AIEngine 实例与生命周期管理"""
from __future__ import annotations

import asyncio
from typing import Optional

from ..ai_engine import AIEngine

_startup_lock = asyncio.Lock()
_initialized = False

ai_engine = AIEngine()


async def initialize_ai_engine() -> None:
    """确保 AIEngine 初始化一次，包括 MCP 连接与向量热身"""
    global _initialized
    if _initialized:
        return
    async with _startup_lock:
        if _initialized:
            return
        await ai_engine.initialize_mcp()
        await ai_engine.initialize_embedding_warmup()
        _initialized = True


async def shutdown_ai_engine() -> None:
    """关闭底层资源"""
    global _initialized
    if not _initialized:
        return
    await ai_engine.close()
    _initialized = False
