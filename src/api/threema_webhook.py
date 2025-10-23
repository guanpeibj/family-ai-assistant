"""
Threema Webhook 端点 - 极简实现
"""
from fastapi import APIRouter, Form, HTTPException, UploadFile, File
from typing import Optional, List, Dict, Any
import os
import hashlib
import uuid
from datetime import datetime
import asyncio
import structlog
from zoneinfo import ZoneInfo

from src.services.threema_service import threema_service
from src.services.engine_provider import ai_engine
from src.db.database import get_db
from src.db.models import UserChannel
from src.core.config import settings

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhooks"])


@router.post("/threema")
async def receive_threema_message(
    from_: str = Form(..., alias="from"),
    to: str = Form(...),
    messageId: str = Form(...),
    date: str = Form(...),
    nonce: str = Form(...),
    box: str = Form(...),
    mac: str = Form(...),
    nickname: Optional[str] = Form(None),
    attachments: Optional[List[UploadFile]] = None,
):
    """
    接收 Threema 消息的 webhook
    
    完全由 AI 驱动的处理流程：
    1. 解密消息
    2. 让 AI 理解并决定如何处理
    3. 发送 AI 生成的回复
    """
    try:
        # 1. 解密消息
        webhook_data = {
            'from': from_,
            'to': to,
            'messageId': messageId,
            'date': date,
            'nonce': nonce,
            'box': box,
            'mac': mac,
            'nickname': nickname
        }
        
        decrypted = await threema_service.receive_message(webhook_data)
        logger.info(f"Received message from {from_}", extra=decrypted)
        # 处理附件（如果网关通过 webhook 转发 multipart，则保存到本地并注入上下文）
        saved_attachments: List[Dict[str, Any]] = []
        try:
            if attachments:
                media_root = settings.MEDIA_ROOT
                now = datetime.now()
                base_dir = os.path.join(media_root, now.strftime("%Y"), now.strftime("%m"))
                os.makedirs(base_dir, exist_ok=True)
                for up in attachments:
                    data = await up.read()
                    sha = hashlib.sha256(data).hexdigest()[:16]
                    ext = os.path.splitext(up.filename or '')[1] or ''
                    fname = f"{uuid.uuid4()}_{sha}{ext}"
                    fpath = os.path.join(base_dir, fname)
                    with open(fpath, 'wb') as f:
                        f.write(data)
                    saved_attachments.append({
                        'type': 'file',
                        'mime': up.content_type or 'application/octet-stream',
                        'path': fpath,
                        'size': len(data),
                        'original_name': up.filename,
                    })
        except Exception as e:
            logger.error(f"attachments.save.failed: {e}")
        
        # 2. 识别或创建用户
        async with get_db() as db:
            # 查找用户
            user_channel = await db.fetch_one(
                "SELECT user_id FROM user_channels WHERE channel = 'threema' AND channel_user_id = :channel_user_id",
                {"channel_user_id": from_}
            )
            
            if user_channel:
                user_id = str(user_channel['user_id'])
            else:
                # 创建新用户
                import uuid
                user_id = str(uuid.uuid4())
                
                # 创建用户记录
                await db.execute(
                    "INSERT INTO users (id, created_at) VALUES (:id, NOW())",
                    {"id": user_id}
                )
                
                # 创建渠道绑定
                await db.execute(
                    """
                    INSERT INTO user_channels (user_id, channel, channel_user_id, channel_data, is_primary, created_at)
                    VALUES (:user_id, 'threema', :channel_user_id, :channel_data, true, NOW())
                    """,
                    {
                        "user_id": user_id,
                        "channel_user_id": from_,
                        "channel_data": {"nickname": nickname} if nickname else {}
                    }
                )
                
                logger.info(f"Created new user {user_id} for Threema ID {from_}")
        
        # 3. AI 处理消息
        # 使用发送者 ID 作为 thread_id，形成稳定线程
        context = dict(decrypted)
        context['thread_id'] = decrypted.get('sender_id') or from_
        if saved_attachments:
            context['attachments'] = saved_attachments
        tz_name = getattr(settings, "DEFAULT_TIMEZONE", "Asia/Shanghai")
        try:
            local_zone = ZoneInfo(tz_name)
        except Exception:
            local_zone = ZoneInfo("UTC")
        received_utc = datetime.now(ZoneInfo("UTC"))
        context['webhook_received_at_utc'] = received_utc.isoformat()
        context['webhook_received_at_iso'] = received_utc.astimezone(local_zone).isoformat()
        response = await ai_engine.process_message(
            content=context.get('raw_content', ''),
            user_id=user_id,
            context=context  # 把所有信息都给 AI
        )

        if saved_attachments:
            from src.services.media_service import derive_for_attachments

            async def _derive_and_update(target_user_id: str, thread_id: str, attachments_payload: List[Dict[str, Any]]):
                try:
                    derived = await derive_for_attachments(attachments_payload)
                    text = "; ".join([
                        (a.get('transcription', {}) or {}).get('text')
                        or a.get('ocr_text')
                        or a.get('vision_summary')
                        or ''
                        for a in derived
                    ])
                    try:
                        embs = await ai_engine.llm.embed([text]) if text else None
                    except Exception:
                        embs = None
                    ai_data = {
                        'type': 'attachment_derivation',
                        'thread_id': thread_id,
                        'attachments': derived,
                        'occurred_at': datetime.now().isoformat(),
                    }
                    await ai_engine._call_mcp_tool(
                        'store',
                        content=text or '(附件衍生完成)',
                        ai_data=ai_data,
                        user_id=target_user_id,
                        embedding=(embs[0] if embs else None),
                    )
                except Exception as e:
                    logger.error(f"attachments.derive.failed: {e}")

            asyncio.create_task(
                _derive_and_update(
                    user_id,
                    context.get('thread_id'),
                    saved_attachments,
                )
            )

        # 4. 发送回复
        send_result = await threema_service.send_message(from_, response)
        
        if not send_result['success']:
            logger.error(f"Failed to send reply: {send_result}")
        
        # 返回 200 避免 Threema 重试
        return {"status": "ok", "processed": True}
        
    except Exception as e:
        logger.error(f"Error processing Threema webhook: {e}")
        # 仍然返回 200 避免重试
        return {"status": "error", "message": str(e)}


async def send_to_threema_user(user_id: str, content: str) -> bool:
    """
    发送消息给 Threema 用户（用于提醒等）
    """
    try:
        async with get_db() as db:
            # 查找用户的 Threema ID
            user_channel = await db.fetch_one(
                """
                SELECT channel_user_id 
                FROM user_channels 
                WHERE user_id = :user_id AND channel = 'threema'
                """,
                {"user_id": user_id}
            )
            
            if not user_channel:
                logger.warning(f"No Threema channel found for user {user_id}")
                return False
        
        threema_id = user_channel['channel_user_id']
        send_result = await threema_service.send_message(threema_id, content)
        
        return send_result['success']
        
    except Exception as e:
        logger.error(f"Error sending to Threema user: {e}")
        return False 


async def send_to_threema_group(user_id: str, content: str) -> bool:
    """
    发送消息到家庭群，如群不可用则回退至单聊
    """
    try:
        group_result = await threema_service.send_group_message(content)
        if group_result.get('success'):
            return True
        logger.warning(
            "threema.group_send_failed",
            error=group_result.get('error'),
            fallback_user=user_id
        )
    except Exception as e:
        logger.error("threema.group_send.exception", error=str(e))
    
    if user_id:
        return await send_to_threema_user(user_id, content)
    return False
