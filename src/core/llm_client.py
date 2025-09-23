"""
统一的 LLM 客户端抽象：支持多厂商切换

当前支持：
- openai_compatible：任意 OpenAI 兼容接口（含 OpenAI、Grok、Qwen、Moonshot、GLM 等）
- anthropic：Claude 系列（可选安装 anthropic 依赖）
"""
from __future__ import annotations

from typing import Any, Dict, Optional
import json
import asyncio
import time
from collections import deque

from ..core.config import settings


class LLMClient:
    """统一封装不同厂商的 Chat 能力。"""

    def __init__(self) -> None:
        self.provider: str = settings.AI_PROVIDER

        # OpenAI 兼容初始化（默认）
        self._openai_client = None
        self._openai_model = settings.OPENAI_MODEL
        self._openai_base_url = settings.OPENAI_BASE_URL or None
        self._openai_api_key = settings.OPENAI_API_KEY
        self._openai_embedding_model = getattr(settings, "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        # 本地 fastembed 初始化（延迟）
        self._embed_provider: str = getattr(settings, "EMBED_PROVIDER", "local_fastembed")
        self._fastembed_model_name: str = getattr(settings, "FASTEMBED_MODEL", "BAAI/bge-small-zh-v1.5")
        self._fastembed_model = None

        # Anthropic 初始化（可选）
        self._anthropic_client = None
        self._anthropic_model = getattr(settings, "ANTHROPIC_MODEL", "claude-3-7-sonnet-latest")
        self._anthropic_api_key = getattr(settings, "ANTHROPIC_API_KEY", "")

        # 全局限流器（类级共享）
        if not hasattr(LLMClient, "_rate_lock"):
            LLMClient._rate_lock = asyncio.Lock()
        if not hasattr(LLMClient, "_call_timestamps"):
            LLMClient._call_timestamps = deque()
        if not hasattr(LLMClient, "_semaphore"):
            try:
                LLMClient._semaphore = asyncio.Semaphore(max(1, int(settings.LLM_CONCURRENCY)))
            except Exception:
                LLMClient._semaphore = asyncio.Semaphore(1)

        if self.provider == "openai_compatible":
            try:
                from openai import AsyncOpenAI

                self._openai_client = AsyncOpenAI(
                    api_key=self._openai_api_key,
                    base_url=self._openai_base_url,
                    max_retries=0,
                )
            except Exception as _:
                self._openai_client = None
        elif self.provider == "anthropic":
            try:
                from anthropic import AsyncAnthropic

                self._anthropic_client = AsyncAnthropic(api_key=self._anthropic_api_key)
            except Exception as _:
                self._anthropic_client = None

        # 轻量结果缓存（去重相同请求，在TTL内命中）
        self._cache_enabled: bool = bool(getattr(settings, "LLM_ENABLE_CACHE", True))
        self._cache_ttl: float = float(getattr(settings, "LLM_CACHE_TTL_SECONDS", 10.0))
        self._cache_max: int = int(getattr(settings, "LLM_CACHE_MAX_ITEMS", 256))
        if not hasattr(LLMClient, "_resp_cache"):
            LLMClient._resp_cache: Dict[str, tuple[float, Any]] = {}
        if not hasattr(LLMClient, "_cooldown_until"):
            LLMClient._cooldown_until = 0.0
        
        # 预加载标记
        self._embedding_preloaded = False
        
        # 检查模型是否已经预下载到缓存目录
        if self._embed_provider == "local_fastembed":
            import os
            cache_path = os.environ.get('FASTEMBED_CACHE_PATH', '/data/fastembed_cache')
            model_cache_dir = os.path.join(cache_path, 'models')
            if os.path.exists(model_cache_dir):
                # 检查是否有模型文件
                import glob
                model_files = glob.glob(os.path.join(model_cache_dir, '**', '*'), recursive=True)
                if len(model_files) > 5:  # 如果缓存目录有足够的文件，认为模型已预下载
                    self._embedding_preloaded = True
                    logger = getattr(self, '_logger', None)
                    if logger:
                        logger.info(f"FastEmbed model cache detected with {len(model_files)} files, skipping download")

    async def warmup_embedding_model(self) -> bool:
        """预热embedding模型，避免首次请求时的下载延迟"""
        if self._embedding_preloaded:
            return True
            
        if self._embed_provider == "local_fastembed":
            # 检查模型是否已经加载
            if self._fastembed_model is not None:
                self._embedding_preloaded = True
                return True
                
            # 尝试多次加载模型，包含重试机制
            for attempt in range(3):  # 最多重试3次
                try:
                    import asyncio
                    # 在线程池中加载模型，避免阻塞主线程
                    loop = asyncio.get_event_loop()
                    
                    def _load_model():
                        from fastembed import TextEmbedding
                        self._fastembed_model = TextEmbedding(model_name=self._fastembed_model_name)
                        return True
                    
                    # 异步执行模型加载
                    success = await loop.run_in_executor(None, _load_model)
                    self._embedding_preloaded = True
                    return success
                    
                except Exception as e:
                    logger = getattr(self, '_logger', None) 
                    if logger:
                        logger.warning(f"Failed to preload embedding model (attempt {attempt + 1}): {e}")
                    
                    if attempt < 2:  # 如果不是最后一次，等待后重试
                        await asyncio.sleep(3 + attempt * 2)  # 3s, 5s, 7s
                        continue
                    
                    # 模型加载失败，但不影响应用启动
                    logger = getattr(self, '_logger', None)
                    if logger:
                        logger.warning(f"FastEmbed model preload failed after all retries. Will fallback to runtime loading or OpenAI embedding.")
                    return False
        
        # 非fastembed模式，无需预热
        self._embedding_preloaded = True
        return True

    async def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> Dict[str, Any]:
        """生成 JSON 响应。如果无法严格 JSON，则尝试解析文本中的 JSON。"""
        cache_key = None
        if self._cache_enabled:
            cache_key = f"cj::{self.provider}::{getattr(self, '_openai_model', '')}::{hash(system_prompt)}::{hash(user_prompt)}::{temperature}::{max_tokens}"
            hit = self._cache_get(cache_key)
            if hit is not None:
                return hit

        if self.provider == "openai_compatible" and self._openai_client is not None:
            attempts = max(1, int(getattr(settings, 'LLM_MAX_RETRIES', 1)))
            for attempt in range(attempts):
                await self._acquire_rate_slot()
                try:
                    response = await self._openai_client.chat.completions.create(
                        model=self._openai_model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        response_format={"type": "json_object"},
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    content = response.choices[0].message.content
                    parsed = self._safe_json_loads(content)
                    self._cache_put(cache_key, parsed)
                    return parsed
                except Exception as e:
                    if self._is_retryable_error(e):
                        if self._is_rate_limit_error(e):
                            try:
                                LLMClient._cooldown_until = time.monotonic() + float(getattr(settings, "LLM_COOLDOWN_SECONDS", 20.0))
                            except Exception:
                                LLMClient._cooldown_until = time.monotonic() + 20.0
                        await self._backoff_sleep(attempt)
                        continue
                    raise
                finally:
                    self._release_rate_slot()

        if self.provider == "anthropic" and self._anthropic_client is not None:
            # Anthropic 支持 JSON 输出，但不同模型行为略有差异，这里做稳健解析
            attempts = max(1, int(getattr(settings, 'LLM_MAX_RETRIES', 1)))
            for attempt in range(attempts):
                await self._acquire_rate_slot()
                try:
                    msg = await self._anthropic_client.messages.create(
                        model=self._anthropic_model,
                        system=system_prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        messages=[{"role": "user", "content": user_prompt}],
                    )
                    text_chunks = []
                    for block in msg.content:
                        if hasattr(block, "text"):
                            text_chunks.append(block.text)
                        elif isinstance(block, dict) and block.get("type") == "text":
                            text_chunks.append(block.get("text", ""))
                    content = "".join(text_chunks)
                    parsed = self._safe_json_loads(content)
                    self._cache_put(cache_key, parsed)
                    return parsed
                except Exception as e:
                    if self._is_retryable_error(e):
                        if self._is_rate_limit_error(e):
                            try:
                                LLMClient._cooldown_until = time.monotonic() + float(getattr(settings, "LLM_COOLDOWN_SECONDS", 20.0))
                            except Exception:
                                LLMClient._cooldown_until = time.monotonic() + 20.0
                        await self._backoff_sleep(attempt)
                        continue
                    raise
                finally:
                    self._release_rate_slot()

        raise RuntimeError(
            "LLM provider not properly configured or SDK missing. Check AI_PROVIDER and API keys."
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """生成嵌入向量列表。优先使用本地 fastembed；可回退到 openai 兼容端。"""
        # 本地 fastembed（默认）
        if self._embed_provider == "local_fastembed":
            if self._fastembed_model is None:
                # 尝试多次加载模型，包含重试机制
                for attempt in range(3):  # 最多重试3次
                    try:
                        from fastembed import TextEmbedding
                        # 如果没有预热过，这里会下载模型文件（可能耗时较长）
                        # 建议在应用启动时调用 warmup_embedding_model() 预热
                        self._fastembed_model = TextEmbedding(model_name=self._fastembed_model_name)
                        break
                    except Exception as e:
                        # 记录错误但继续重试
                        logger = getattr(self, '_logger', None)
                        if logger:
                            logger.warning(f"FastEmbed model loading attempt {attempt + 1} failed: {e}")
                        
                        if attempt < 2:  # 如果不是最后一次，等待后重试
                            await asyncio.sleep(2 ** attempt)  # 指数退避：1s, 2s
                            continue
                        
                        # 最后一次重试失败，回退到 openai 兼容
                        if logger:
                            logger.warning("FastEmbed model loading failed after all retries, falling back to OpenAI embedding")
                        self._fastembed_model = None
                        break
                        
            if self._fastembed_model is not None:
                # fastembed 同步接口，放在线程池可能更稳，这里小规模直接调用
                try:
                    vectors: list[list[float]] = []
                    for emb in self._fastembed_model.embed(texts):
                        # emb 可能是 numpy.ndarray(float32)；需转为 Python float 以便 JSON 序列化
                        try:
                            vectors.append([float(x) for x in emb])
                        except Exception:
                            vectors.append([float(x) for x in list(emb)])
                    return vectors
                except Exception as e:
                    # 嵌入生成失败，清空模型实例并回退
                    logger = getattr(self, '_logger', None)
                    if logger:
                        logger.warning(f"FastEmbed embedding generation failed: {e}, falling back to OpenAI")
                    self._fastembed_model = None
                    
        # 回退：openai 兼容
        if self.provider == "openai_compatible" and self._openai_client is not None:
            attempts = max(1, int(getattr(settings, 'LLM_MAX_RETRIES', 1)))
            for attempt in range(attempts):
                await self._acquire_rate_slot()
                try:
                    resp = await self._openai_client.embeddings.create(
                        model=self._openai_embedding_model,
                        input=texts,
                    )
                    return [[float(x) for x in d.embedding] for d in resp.data]
                except Exception as e:
                    if self._is_retryable_error(e):
                        if self._is_rate_limit_error(e):
                            try:
                                LLMClient._cooldown_until = time.monotonic() + float(getattr(settings, "LLM_COOLDOWN_SECONDS", 20.0))
                            except Exception:
                                LLMClient._cooldown_until = time.monotonic() + 20.0
                        await self._backoff_sleep(attempt)
                        continue
                    raise
                finally:
                    self._release_rate_slot()
        # 最后兜底：返回空或抛出异常
        logger = getattr(self, '_logger', None)
        if logger:
            logger.error("All embedding methods failed, unable to generate embeddings")
        return []

    async def chat_text(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """生成文本回复。"""
        if self.provider == "openai_compatible" and self._openai_client is not None:
            cache_key = None
            if self._cache_enabled:
                cache_key = f"ct::{self.provider}::{getattr(self, '_openai_model', '')}::{hash(system_prompt)}::{hash(user_prompt)}::{temperature}::{max_tokens}"
                hit = self._cache_get(cache_key)
                if hit is not None:
                    return hit
            attempts = max(1, int(getattr(settings, 'LLM_MAX_RETRIES', 1)))
            for attempt in range(attempts):
                await self._acquire_rate_slot()
                try:
                    response = await self._openai_client.chat.completions.create(
                        model=self._openai_model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    text = response.choices[0].message.content
                    self._cache_put(cache_key, text)
                    return text
                except Exception as e:
                    if self._is_retryable_error(e):
                        if self._is_rate_limit_error(e):
                            try:
                                LLMClient._cooldown_until = time.monotonic() + float(getattr(settings, "LLM_COOLDOWN_SECONDS", 20.0))
                            except Exception:
                                LLMClient._cooldown_until = time.monotonic() + 20.0
                        await self._backoff_sleep(attempt)
                        continue
                    raise
                finally:
                    self._release_rate_slot()

        if self.provider == "anthropic" and self._anthropic_client is not None:
            cache_key = None
            if self._cache_enabled:
                cache_key = f"ct::{self.provider}::{getattr(self, '_anthropic_model', '')}::{hash(system_prompt)}::{hash(user_prompt)}::{temperature}::{max_tokens}"
                hit = self._cache_get(cache_key)
                if hit is not None:
                    return hit
            attempts = max(1, int(getattr(settings, 'LLM_MAX_RETRIES', 1)))
            for attempt in range(attempts):
                await self._acquire_rate_slot()
                try:
                    msg = await self._anthropic_client.messages.create(
                        model=self._anthropic_model,
                        system=system_prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        messages=[{"role": "user", "content": user_prompt}],
                    )
                    text_chunks = []
                    for block in msg.content:
                        if hasattr(block, "text"):
                            text_chunks.append(block.text)
                        elif isinstance(block, dict) and block.get("type") == "text":
                            text_chunks.append(block.get("text", ""))
                    text = "".join(text_chunks)
                    self._cache_put(cache_key, text)
                    return text
                except Exception as e:
                    if self._is_retryable_error(e):
                        if self._is_rate_limit_error(e):
                            try:
                                LLMClient._cooldown_until = time.monotonic() + float(getattr(settings, "LLM_COOLDOWN_SECONDS", 20.0))
                            except Exception:
                                LLMClient._cooldown_until = time.monotonic() + 20.0
                        await self._backoff_sleep(attempt)
                        continue
                    raise
                finally:
                    self._release_rate_slot()

        raise RuntimeError(
            "LLM provider not properly configured or SDK missing. Check AI_PROVIDER and API keys."
        )

    @staticmethod
    def _safe_json_loads(text: str) -> Dict[str, Any]:
        """稳健解析 JSON：优先直接解析，失败则提取第一个 {...} 或 [...] 片段。"""
        try:
            return json.loads(text)
        except Exception:
            pass

        # 尝试提取 JSON 片段
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                pass
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                pass
        # 最后退回空对象，避免崩溃
        return {}

    # --- 简易结果缓存（进程内） ---
    def _cache_get(self, key: Optional[str]) -> Optional[Any]:
        if not self._cache_enabled or not key:
            return None
        try:
            cache: Dict[str, tuple[float, Any]] = getattr(LLMClient, "_resp_cache")
            now = time.monotonic()
            item = cache.get(key)
            if not item:
                return None
            ts, value = item
            if (now - ts) > self._cache_ttl:
                cache.pop(key, None)
                return None
            return value
        except Exception:
            return None

    def _cache_put(self, key: Optional[str], value: Any) -> None:
        if not self._cache_enabled or not key:
            return
        try:
            cache: Dict[str, tuple[float, Any]] = getattr(LLMClient, "_resp_cache")
            # 简单容量控制：移除最旧项
            if len(cache) >= self._cache_max:
                oldest_key = None
                oldest_ts = float("inf")
                for k, (ts, _) in cache.items():
                    if ts < oldest_ts:
                        oldest_key, oldest_ts = k, ts
                if oldest_key:
                    cache.pop(oldest_key, None)
            cache[key] = (time.monotonic(), value)
        except Exception:
            pass

    def _is_retryable_error(self, e: Exception) -> bool:
        text = str(e).lower()
        if "429" in text or "rate limit" in text:
            return True
        for code in ("500", "502", "503", "504"):
            if code in text:
                return True
        if "temporarily unavailable" in text or "timeout" in text:
            return True
        return False

    def _is_rate_limit_error(self, e: Exception) -> bool:
        text = str(e).lower()
        return "429" in text or "rate limit" in text

    async def _backoff_sleep(self, attempt: int) -> None:
        base = float(getattr(settings, "LLM_BACKOFF_BASE_SECONDS", 1.0))
        # 简易抖动：使用单调时钟的小数部分
        frac = time.monotonic() % 1.0
        jitter = 0.25 * frac
        delay = min(5.0, base * (2 ** attempt) + jitter)
        await asyncio.sleep(delay)

    async def _acquire_rate_slot(self) -> None:
        """基于全局并发与 RPM 的限流。"""
        # 若处于冷却窗口，先等待（小步睡眠，避免长阻塞）
        try:
            while time.monotonic() < float(getattr(LLMClient, "_cooldown_until", 0.0)):
                await asyncio.sleep(0.2)
        except Exception:
            pass
        # 并发限制
        sem: asyncio.Semaphore = getattr(LLMClient, "_semaphore")
        await sem.acquire()
        # RPM 限制
        limit = max(1, int(getattr(settings, "LLM_RPM_LIMIT", 3)))
        lock: asyncio.Lock = getattr(LLMClient, "_rate_lock")
        q: deque = getattr(LLMClient, "_call_timestamps")
        while True:
            now = time.monotonic()
            async with lock:
                # 清理 60s 之前的记录
                cutoff = now - 60.0
                while q and q[0] < cutoff:
                    q.popleft()
                if len(q) < limit:
                    q.append(now)
                    return
                # 需要等待直到最老的一条过期
                wait_secs = max(0.01, (q[0] + 60.0) - now)
            # 分片等待，避免长 await 阻塞
            await asyncio.sleep(min(wait_secs, 0.5))

    def _release_rate_slot(self) -> None:
        """释放并发信号量。RPM 计数按进入时记录，不回滚。"""
        try:
            sem: asyncio.Semaphore = getattr(LLMClient, "_semaphore")
            sem.release()
        except Exception:
            pass

    @classmethod
    def in_cooldown(cls) -> bool:
        try:
            return time.monotonic() < float(getattr(cls, "_cooldown_until", 0.0))
        except Exception:
            return False


