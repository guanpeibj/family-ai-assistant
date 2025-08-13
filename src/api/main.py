from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
import structlog
import asyncio

from ..core.config import settings
from ..services.media_service import verify_signature
import base64
import os
from ..core.logging import get_logger
from ..db.database import init_db, close_db
from ..ai_engine import AIEngine
from .threema_webhook import router as threema_router, send_to_threema_user

logger = get_logger(__name__)

# 全局AI引擎实例
ai_engine = AIEngine()

# 请求模型
class MessageRequest(BaseModel):
    content: str
    user_id: str
    thread_id: str | None = None


# 后台任务
async def reminder_task():
    """简单的提醒检查任务"""
    while True:
        try:
            # 使用 Threema 作为默认提醒渠道
            await ai_engine.check_and_send_reminders(send_to_threema_user)
        except Exception as e:
            logger.error(f"Reminder task error: {e}")
        # 每分钟检查一次
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("Starting 阿福 (Family AI Assistant)", 
                app_name=settings.APP_NAME,
                environment=settings.APP_ENV)
    
    # 初始化数据库
    await init_db()
    
    # 初始化AI引擎
    await ai_engine.initialize_mcp()
    
    # 启动后台任务
    reminder_task_handle = asyncio.create_task(reminder_task())
    
    yield
    
    # 关闭时
    logger.info("Shutting down 阿福 (Family AI Assistant)")
    
    # 取消后台任务
    reminder_task_handle.cancel()
    try:
        await reminder_task_handle
    except asyncio.CancelledError:
        pass
    
    # 关闭AI引擎
    await ai_engine.close()
    
    # 关闭数据库
    await close_db()


# 创建FastAPI应用
app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="AI-powered assistant for family management",
    lifespan=lifespan,
    debug=settings.DEBUG,
)

# 配置CORS（如果需要）
if settings.DEBUG:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# 注册路由
app.include_router(threema_router)


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV,
    }


@app.post("/message")
async def handle_message(request: MessageRequest):
    """处理消息 - 核心端点（用于测试或直接API调用）"""
    # 处理消息 - 通过 API 调用的消息没有特定渠道
    response = await ai_engine.process_message(
        content=request.content,
        user_id=request.user_id,
        context={"channel": "api", "thread_id": request.thread_id or request.user_id}
    )
    
    return {
        "success": True,
        "response": response
    }


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "Welcome to 阿福 (Family AI Assistant)",
        "version": "0.1.0",
        "endpoints": {
            "health": "/health",
            "message": "/message (POST)",
            "docs": "/docs"
        }
    }


@app.get("/media/get")
async def get_media(p: str = Query(...), exp: int = Query(...), sig: str = Query(...)):
    """
    签名媒体访问端点（回退方案）。
    注意：仅用于 Threema 不支持媒体直发的回退；生产建议使用对象存储签名URL。
    """
    try:
        rel = base64.urlsafe_b64decode(p.encode('utf-8')).decode('utf-8')
        if not verify_signature(rel, exp, sig):
            raise HTTPException(status_code=403, detail="Invalid signature or expired")
        abs_path = os.path.join(settings.MEDIA_ROOT, rel)
        if not os.path.exists(abs_path):
            raise HTTPException(status_code=404, detail="File not found")
        from fastapi.responses import FileResponse
        return FileResponse(abs_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))