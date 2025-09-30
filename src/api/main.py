from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import structlog
import asyncio

from ..core.config import settings
from ..services.media_service import verify_signature
import base64
import os
from ..core.logging import get_logger
from ..db.database import init_db, close_db
from ..services.engine_provider import (
    ai_engine,
    initialize_ai_engine,
    shutdown_ai_engine,
)
from .threema_webhook import router as threema_router, send_to_threema_user

logger = get_logger(__name__)

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


async def financial_analysis_task():
    """月度财务分析任务
    
    功能：
    - 每天00:05检查是否为月初第一天
    - 如果是，为所有活跃用户生成上月财务分析报告
    - 通过 Threema 发送报告
    
    设计理念：
    - AI主导：报告内容完全由AI根据数据生成
    - 简单直接：只提供触发机制，不预设报告格式
    - 保持泛化：可以扩展为周报、季报等
    """
    from datetime import datetime, timedelta
    
    # 等待启动后的初始延迟（避免启动时立即执行）
    await asyncio.sleep(60)
    
    last_check_date = None  # 记录上次检查的日期，避免重复执行
    
    while True:
        try:
            now = datetime.now()
            today = now.date()
            
            # 检查是否为月初第一天（且未执行过）
            is_first_day = now.day == 1
            not_checked_today = last_check_date != today
            is_morning = now.hour == 0 and now.minute < 10  # 凌晨00:00-00:10之间
            
            if is_first_day and not_checked_today and is_morning:
                logger.info(
                    "financial_analysis.trigger",
                    date=today.isoformat(),
                    time=now.strftime("%H:%M")
                )
                
                # 标记为已检查
                last_check_date = today
                
                # 获取所有活跃用户
                active_users = await ai_engine._get_all_active_users()
                
                if not active_users:
                    logger.warning("financial_analysis.no_users")
                else:
                    # 计算上月日期范围
                    last_month = now.replace(day=1) - timedelta(days=1)
                    month_start = last_month.replace(day=1)
                    month_str = last_month.strftime("%Y年%m月")
                    
                    logger.info(
                        "financial_analysis.start",
                        month=month_str,
                        users_count=len(active_users)
                    )
                    
                    # 为每个用户生成报告
                    for user_id in active_users:
                        try:
                            # 构造分析请求（让AI自主生成报告）
                            analysis_request = f"请生成{month_str}的财务分析报告，包括收支总览、分类明细、异常提醒和改进建议"
                            
                            # 调用AI引擎生成报告
                            report = await ai_engine.process_message(
                                content=analysis_request,
                                user_id=str(user_id),
                                context={
                                    "channel": "system",
                                    "thread_id": f"financial_report_{last_month.strftime('%Y%m')}",
                                    "auto_analysis": True
                                }
                            )
                            
                            # 发送报告
                            if report and len(report.strip()) > 10:
                                await send_to_threema_user(str(user_id), report)
                                
                                logger.info(
                                    "financial_analysis.sent",
                                    user_id=str(user_id),
                                    month=month_str,
                                    report_length=len(report)
                                )
                            else:
                                logger.warning(
                                    "financial_analysis.empty_report",
                                    user_id=str(user_id),
                                    month=month_str
                                )
                        
                        except Exception as e:
                            logger.error(
                                "financial_analysis.user_failed",
                                user_id=str(user_id),
                                month=month_str,
                                error=str(e)
                            )
                    
                    logger.info(
                        "financial_analysis.complete",
                        month=month_str,
                        users_count=len(active_users)
                    )
            
        except Exception as e:
            logger.error("financial_analysis.task_error", error=str(e))
        
        # 每5分钟检查一次（避免错过时间窗口）
        await asyncio.sleep(300)


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
    await initialize_ai_engine()
    
    # 启动后台任务
    reminder_task_handle = asyncio.create_task(reminder_task())
    financial_task_handle = asyncio.create_task(financial_analysis_task())
    
    logger.info("background_tasks.started", 
                tasks=["reminder_task", "financial_analysis_task"])
    
    yield
    
    # 关闭时
    logger.info("Shutting down 阿福 (Family AI Assistant)")
    
    # 取消后台任务
    reminder_task_handle.cancel()
    financial_task_handle.cancel()
    
    try:
        await reminder_task_handle
    except asyncio.CancelledError:
        pass
    
    try:
        await financial_task_handle
    except asyncio.CancelledError:
        pass
    
    logger.info("background_tasks.stopped")
    
    # 关闭AI引擎
    await shutdown_ai_engine()
    
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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """更详细的 422 日志与响应，便于排障。"""
    logger.warning(
        "api.request.validation_error",
        path=str(request.url),
        method=request.method,
        client=(request.client.host if request.client else None),
        errors=[e for e in exc.errors()],
    )
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": "请求参数校验失败",
            "details": exc.errors(),
        },
    )


@app.post("/message")
async def handle_message(req: Request, response: Response, payload: MessageRequest):
    """处理消息 - 核心端点（用于测试或直接API调用）"""
    # 生成本次请求的 request_id 以便端到端回溯
    import uuid
    request_id = str(uuid.uuid4())

    # 记录请求到达
    try:
        logger.info(
            "api.message.in",
            path=str(req.url),
            method=req.method,
            client=(req.client.host if req.client else None),
            user_id=payload.user_id,
            thread_id=(payload.thread_id or payload.user_id),
            request_id=request_id,
            content_preview=(payload.content[:200] if isinstance(payload.content, str) else None),
        )
    except Exception:
        pass

    # 处理消息 - 通过 API 调用的消息没有特定渠道
    ai_reply = await ai_engine.process_message(
        content=payload.content,
        user_id=payload.user_id,
        context={
            "channel": "api",
            "thread_id": payload.thread_id or payload.user_id,
            "message_id": request_id,
        }
    )

    # 设置回执头部，方便客户端与日志对齐
    try:
        resp_obj = {
        "success": True,
        "response": ai_reply,
        "message_id": request_id,
    }
        # 将 request_id 也放在响应头
        from fastapi.datastructures import Headers
        resp_headers = Headers({"X-Request-Id": request_id})
        # FastAPI Response 对象直接赋值 headers
        response_headers = dict(response.headers)
        response_headers.update(dict(resp_headers))
        response.headers.clear()
        for k, v in response_headers.items():
            try:
                response.headers[k] = v
            except Exception:
                pass
        return resp_obj
    except Exception:
        # 兜底返回
        return {
            "success": True,
            "response": ai_reply,
            "message_id": request_id,
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
