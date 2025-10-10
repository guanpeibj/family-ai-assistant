"""
媒体服务：签名URL、附件衍生信息（占位）、路径安全
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from src.core.config import settings


def _relativize_path(abs_path: str) -> str:
    root = settings.MEDIA_ROOT.rstrip('/')
    ap = os.path.abspath(abs_path)
    if not ap.startswith(os.path.abspath(root) + os.sep):
        raise ValueError("Path not under MEDIA_ROOT")
    return ap[len(os.path.abspath(root)) + 1 :]


def _sign(payload: str) -> str:
    key = (settings.SIGNING_SECRET or "").encode('utf-8')
    return hmac.new(key, payload.encode('utf-8'), hashlib.sha256).hexdigest()


def make_signed_url(abs_path: str, expires_in_seconds: int = 3600) -> str:
    """
    生成带签名的媒体访问URL（通过后端 /media/get 提供）。
    如果配置了 MEDIA_PUBLIC_BASE_URL，可直接拼接公开URL（不推荐在内网）。
    """
    rel = _relativize_path(abs_path)
    exp = int((datetime.utcnow() + timedelta(seconds=expires_in_seconds)).timestamp())
    payload = f"{rel}:{exp}"
    sig = _sign(payload)
    # 使用 base64 对路径进行可读编码
    p = base64.urlsafe_b64encode(rel.encode('utf-8')).decode('utf-8')
    return f"/media/get?p={p}&exp={exp}&sig={sig}"


def verify_signature(rel_path: str, exp: int, sig: str) -> bool:
    if exp < int(datetime.utcnow().timestamp()):
        return False
    payload = f"{rel_path}:{exp}"
    expected = _sign(payload)
    return hmac.compare_digest(expected, sig)


async def derive_for_attachments(attachments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    为附件生成衍生文本：
    - audio: transcription.text （M1：占位，后续接入 Whisper）
    - image: ocr_text 或 vision_summary（M1：占位）
    返回新的列表，不修改入参引用。
    """
    derived: List[Dict[str, Any]] = []
    for att in attachments:
        a = dict(att)
        mime = a.get('mime') or ''
        ftype = a.get('type') or 'file'
        # 类型归一
        if not ftype or ftype == 'file':
            if isinstance(mime, str) and mime.startswith('image/'):
                ftype = 'image'
            elif isinstance(mime, str) and mime.startswith('audio/'):
                ftype = 'audio'
            a['type'] = ftype
        # STT（OpenAI 兼容）
        if ftype == 'audio' and settings.ENABLE_STT and os.path.exists(a.get('path','')):
            try:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, base_url=(settings.OPENAI_BASE_URL or None))
                # 读取文件并上传转写
                import aiofiles
                async with aiofiles.open(a['path'], 'rb') as f:
                    file_bytes = await f.read()
                # Whisper 兼容接口（部分兼容端点需使用不同方法，这里使用 Chat Completions 兼容STT接口会不通，改用 audio.transcriptions）
                try:
                    tr = await client.audio.transcriptions.create(
                        model=settings.OPENAI_STT_MODEL,
                        file=(os.path.basename(a['path']), file_bytes, a.get('mime') or 'audio/ogg')
                    )
                    text = getattr(tr, 'text', None) or (tr.get('text') if isinstance(tr, dict) else None)
                    if text:
                        a.setdefault('transcription', {"text": text})
                except Exception:
                    # 兼容部分供应商没有 audio.transcriptions，降级占位
                    a.setdefault('transcription', {"text": "(语音已接收，待转写)"})
            except Exception:
                a.setdefault('transcription', {"text": "(语音已接收，待转写)"})
        # OCR（轻量占位，可替换为 tesseract/easyocr）或 Vision
        if ftype == 'image' and os.path.exists(a.get('path','')):
            # 优先 Vision 摘要
            if settings.ENABLE_VISION:
                try:
                    from openai import AsyncOpenAI
                    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, base_url=(settings.OPENAI_BASE_URL or None))
                    # 将图片以 data URL 形式发送（小图可行；大图建议外链）。
                    with open(a['path'], 'rb') as imgf:
                        b64 = base64.b64encode(imgf.read()).decode('utf-8')
                    # 优化的 Vision prompt：针对支付截图识别
                    user_content = [
                        {"type": "text", "text": """请分析这张图片，识别以下信息：

**如果是支付信息（支付截图、小票、账单）**：
- 金额（必填，仅数字）
- 日期时间（格式：YYYY-MM-DD HH:mm）
- 商家/收款方名称
- 支付方式（支付宝/微信/银行卡/现金）
- 商品/服务类别（从以下选择：餐饮、交通、医疗、教育、娱乐、居住、服饰、日用、其他）

**如果是其他类型图片**：
- 简要描述图片内容
- 提取关键信息（人物、地点、物品等）

请以简洁的自然语言输出，例如：
"支付宝支付，星巴克，78元，餐饮类，2025-10-10 14:30"
或
"家庭照片，三个孩子在公园玩耍"
"""},
                        {"type": "image_url", "image_url": {"url": f"data:{a.get('mime','image/png')};base64,{b64}"}}
                    ]
                    # 兼容 openai-vision 的 chat.completions 风格
                    try:
                        resp = await client.chat.completions.create(
                            model=settings.OPENAI_VISION_MODEL,
                            messages=[{"role": "user", "content": user_content}]
                        )
                        summary = resp.choices[0].message.content
                        if summary:
                            a.setdefault('vision_summary', summary[:2000])
                    except Exception:
                        # 降级占位
                        a.setdefault('ocr_text', "(图片已接收，待识别)")
                except Exception:
                    a.setdefault('ocr_text', "(图片已接收，待识别)")
            elif settings.ENABLE_OCR:
                try:
                    # 简易 OCR 占位；如需真实 OCR，请接入 tesseract/easyocr。
                    a.setdefault('ocr_text', "(图片已接收，待识别)")
                except Exception:
                    a.setdefault('ocr_text', "(图片已接收，待识别)")
        derived.append(a)
    return derived


