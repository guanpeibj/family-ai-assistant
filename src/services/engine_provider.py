"""统一的 AIEngine 实例与生命周期管理"""
from __future__ import annotations

import asyncio
from typing import Optional

from ..ai_engine import ai_engine

_startup_lock = asyncio.Lock()
_initialized = False

# 使用全局单例实例


async def initialize_ai_engine() -> None:
    """确保 AIEngine 初始化一次"""
    global _initialized
    if _initialized:
        return
    async with _startup_lock:
        if _initialized:
            return
        # AIEngineV2 在 __init__ 中已完成初始化
        _initialized = True


async def shutdown_ai_engine() -> None:
    """关闭底层资源"""
    global _initialized
    if not _initialized:
        return
    # AIEngineV2 不需要显式关闭
    _initialized = False
