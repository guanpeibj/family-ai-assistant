"""
Threema Webhook 端点 - 极简实现
"""
from fastapi import APIRouter, Form, HTTPException
from typing import Optional
import structlog

from src.services.threema_service import threema_service
from src.ai_engine import AIEngine
from src.db.database import get_db
from src.db.models import UserChannel

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhooks"])

# AI Engine 实例
ai_engine = AIEngine()


@router.post("/threema")
async def receive_threema_message(
    from_: str = Form(..., alias="from"),
    to: str = Form(...),
    messageId: str = Form(...),
    date: str = Form(...),
    nonce: str = Form(...),
    box: str = Form(...),
    mac: str = Form(...),
    nickname: Optional[str] = Form(None)
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
        response = await ai_engine.process_message(
            content=decrypted.get('raw_content', ''),
            user_id=user_id,
            context=decrypted  # 把所有信息都给 AI
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