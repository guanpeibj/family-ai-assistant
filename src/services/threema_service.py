"""
Threema Gateway 服务 - 极简实现
只负责消息的加解密和发送，所有理解和决策交给 AI
"""
import aiohttp
import nacl.secret
import nacl.utils
from nacl.public import PrivateKey, PublicKey, Box
from nacl.encoding import HexEncoder
from typing import Optional, Dict, Any
import hashlib
import hmac
from datetime import datetime
from zoneinfo import ZoneInfo

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class ThreemaService:
    """Threema Gateway E2E 模式服务"""
    
    def __init__(self):
        self.gateway_id = settings.THREEMA_GATEWAY_ID
        self.secret = settings.THREEMA_SECRET
        self.api_base = "https://msgapi.threema.ch"
        
        # 加载私钥
        if settings.THREEMA_PRIVATE_KEY:
            self.private_key = PrivateKey(
                settings.THREEMA_PRIVATE_KEY.encode(), 
                encoder=HexEncoder
            )
        else:
            # 生成新的密钥对（首次使用）
            self.private_key = PrivateKey.generate()
            logger.info(
                f"Generated new key pair. Public key: {self.private_key.public_key.encode(HexEncoder).decode()}"
            )
        
        # 公钥缓存（避免重复查询）
        self._public_key_cache = {}
    
    async def receive_message(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        接收并解密 Threema 消息
        返回原始数据，让 AI 自己理解
        """
        # 1. 验证 MAC
        if not self._verify_mac(webhook_data):
            raise ValueError("Invalid MAC")
        
        # 2. 解密消息
        try:
            sender_id = webhook_data['from']
            nonce = bytes.fromhex(webhook_data['nonce'])
            box_data = bytes.fromhex(webhook_data['box'])
            timestamp_raw = webhook_data.get('date')
            timestamp_value: Optional[int] = None
            message_utc_iso = None
            message_local_iso = None
            if timestamp_raw is not None:
                try:
                    ts_int = int(timestamp_raw)
                    timestamp_value = ts_int
                    utc_dt = datetime.fromtimestamp(ts_int, tz=ZoneInfo("UTC"))
                    message_utc_iso = utc_dt.isoformat()
                    tz_name = getattr(settings, "DEFAULT_TIMEZONE", "Asia/Shanghai")
                    try:
                        local_zone = ZoneInfo(tz_name)
                    except Exception:
                        local_zone = ZoneInfo("UTC")
                    message_local_iso = utc_dt.astimezone(local_zone).isoformat()
                except Exception:
                    pass
            
            # 获取发送者公钥
            sender_public_key = await self._get_public_key(sender_id)
            
            # 解密
            box = Box(self.private_key, PublicKey(sender_public_key, encoder=HexEncoder))
            decrypted = box.decrypt(box_data, nonce)
            
            # 返回所有信息，让 AI 理解
            return {
                'channel': 'threema',
                'sender_id': sender_id,
                'nickname': webhook_data.get('nickname'),
                'timestamp': timestamp_value,
                'message_sent_at_iso': message_local_iso,
                'message_sent_at_utc': message_utc_iso,
                'raw_content': decrypted.decode('utf-8', errors='replace'),
                'message_id': webhook_data['messageId'],
                # AI 可能需要的其他信息都保留
                'raw_webhook': webhook_data
            }
            
        except Exception as e:
            get_logger(__name__).error(f"Failed to decrypt message: {e}")
            # 即使解密失败，也返回能返回的信息
            return {
                'channel': 'threema',
                'sender_id': webhook_data.get('from'),
                'error': str(e),
                'raw_webhook': webhook_data
            }
    
    async def send_message(self, to_id: str, content: str) -> Dict[str, Any]:
        """
        发送消息到 Threema
        AI 决定发什么，这里只负责发送
        """
        try:
            # 获取接收者公钥
            recipient_public_key = await self._get_public_key(to_id)
            
            # 加密消息
            box = Box(self.private_key, PublicKey(recipient_public_key, encoder=HexEncoder))
            nonce = nacl.utils.random(Box.NONCE_SIZE)
            encrypted = box.encrypt(content.encode('utf-8'), nonce)
            
            # 发送
            async with aiohttp.ClientSession() as session:
                data = {
                    'from': self.gateway_id,
                    'to': to_id,
                    'nonce': nonce.hex(),
                    'box': encrypted.ciphertext.hex(),
                    'secret': self.secret
                }
                
                async with session.post(f"{self.api_base}/send_e2e", data=data) as resp:
                    if resp.status == 200:
                        message_id = await resp.text()
                        return {
                            'success': True,
                            'message_id': message_id,
                            'channel': 'threema',
                            'to': to_id
                        }
                    else:
                        error = await resp.text()
                        return {
                            'success': False,
                            'error': f"HTTP {resp.status}: {error}",
                            'channel': 'threema',
                            'to': to_id
                        }
                        
        except Exception as e:
            get_logger(__name__).error(f"Failed to send message: {e}")
            return {
                'success': False,
                'error': str(e),
                'channel': 'threema',
                'to': to_id
            }

    async def send_group_message(self, content: str) -> Dict[str, Any]:
        """发送消息到预配置的家庭群"""
        group_id = settings.THREEMA_FAMILY_GROUP_ID
        if not group_id:
            logger.warning("threema.group_id_missing")
            return {'success': False, 'error': 'group_id_not_configured'}
        return await self.send_message(group_id, content)

    async def send_file(self, to_id: str, file_bytes: bytes, filename: str, content_type: str) -> Dict[str, Any]:
        """
        发送文件到 Threema（回退实现：发送签名链接或简短说明）。
        说明：Threema Gateway E2E 媒体发送需要专用端点与加密流程，此处先提供占位与回退方案，
        后续替换为真实媒体端点调用。
        """
        try:
            # 回退：暂不实现直传，返回不支持，交由上层转为链接
            return {
                'success': False,
                'error': 'Media send not implemented in gateway fallback',
                'channel': 'threema',
                'to': to_id
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'channel': 'threema',
                'to': to_id
            }

    async def send_image(self, to_id: str, image_bytes: bytes, filename: str = "image.png") -> Dict[str, Any]:
        return await self.send_file(to_id, image_bytes, filename, content_type="image/png")

    async def send_image_link(self, to_id: str, url: str, title: str | None = None) -> Dict[str, Any]:
        """发送图片链接（回退方案）。"""
        prefix = f"{title}\n" if title else ""
        text = f"{prefix}图片：{url}"
        return await self.send_message(to_id, text)
    
    async def _get_public_key(self, threema_id: str) -> bytes:
        """获取用户公钥（带缓存）"""
        if threema_id in self._public_key_cache:
            return self._public_key_cache[threema_id]
        
        async with aiohttp.ClientSession() as session:
            url = f"{self.api_base}/pubkeys/{threema_id}"
            params = {'from': self.gateway_id, 'secret': self.secret}
            
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    public_key_hex = await resp.text()
                    self._public_key_cache[threema_id] = bytes.fromhex(public_key_hex)
                    return self._public_key_cache[threema_id]
                else:
                    raise ValueError(f"Failed to get public key for {threema_id}")
    
    def _verify_mac(self, webhook_data: Dict[str, Any]) -> bool:
        """验证 webhook MAC"""
        # 构建待验证的数据
        mac_data = (
            webhook_data['from'] +
            webhook_data['to'] +
            webhook_data['messageId'] +
            webhook_data['date'] +
            webhook_data['nonce'] +
            webhook_data['box']
        ).encode('utf-8')
        
        # 计算 MAC
        expected_mac = hmac.new(
            self.secret.encode('utf-8'),
            mac_data,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_mac, webhook_data['mac'])


# 全局实例
threema_service = ThreemaService() 
