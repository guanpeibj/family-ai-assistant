"""
统一的 LLM 客户端抽象：支持多厂商切换

当前支持：
- openai_compatible：任意 OpenAI 兼容接口（含 OpenAI、Qwen、Moonshot、DeepSeek、Doubao 等）
- anthropic：Claude 系列（可选安装 anthropic 依赖）

特性：
- 自动从 provider 预配置中读取限流、成本信息
- 按 provider 的限流策略
- 成本追踪（记录 token 消耗和成本）
- Embedding 策略优化（local_first 优先本地，openai_only 仅用 OpenAI）
"""
from __future__ import annotations

from typing import Any, Dict, Optional, List
import json
import asyncio
import time
from collections import deque

from ..core.config import settings
from ..core.llm_providers import ProviderRegistry, UsageTracker

try:
    from ..core.logging import get_logger
    logger = get_logger(__name__)
except Exception:
    import logging
    logger = logging.getLogger(__name__)


class LLMClient:
    """统一封装不同厂商的 Chat 能力。"""

    # 全局使用量追踪器
    _usage_tracker: Optional[UsageTracker] = None
    _init_lock = asyncio.Lock()

    def __init__(
        self,
        provider_name: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None
    ) -> None:
        """
        初始化 LLM 客户端
        
        Args:
            provider_name: Provider 名称（qwen/kimi/doubao/deepseek/openai/anthropic），None则使用 settings.LLM_PROVIDER_NAME
            model: 模型名称，None 则使用 provider 预配置或 settings.OPENAI_MODEL
            base_url: API 地址，None 则使用 provider 预配置或 settings.OPENAI_BASE_URL
            api_key: API Key，None 则使用 settings.OPENAI_API_KEY
        """
        # 获取 provider 配置
        self._provider_name = provider_name or getattr(settings, "LLM_PROVIDER_NAME", "qwen")
        self._provider_config = ProviderRegistry.get_provider(self._provider_name)
        
        if not self._provider_config:
            logger.warning(f"Unknown provider: {self._provider_name}, using default config")
            self._provider_config = ProviderRegistry.get_provider("qwen")
        
        logger.info(f"Initializing LLM client with provider: {self._provider_name}")
        
        # 确定 provider 类型（openai_compatible 或 anthropic）
        self.provider = self._provider_config.provider_type
        
        # 限流配置（来自 provider 或环境变量覆盖）
        rpm_limit = getattr(settings, "LLM_RPM_LIMIT", 0)
        concurrency_limit = getattr(settings, "LLM_CONCURRENCY", 0)
        
        self._rpm_limit = rpm_limit if rpm_limit > 0 else self._provider_config.rpm_limit
        self._concurrency_limit = concurrency_limit if concurrency_limit > 0 else self._provider_config.concurrency_limit
        
        # Embedding 策略
        self._embedding_strategy = self._provider_config.embedding_strategy
        
        logger.debug(
            f"Provider config: rpm_limit={self._rpm_limit}, "
            f"concurrency={self._concurrency_limit}, "
            f"embedding_strategy={self._embedding_strategy}"
        )
        
        # OpenAI 兼容初始化
        self._openai_client = None
        self._openai_model = model or settings.OPENAI_MODEL or self._provider_config.default_model
        self._openai_base_url = base_url or settings.OPENAI_BASE_URL or self._provider_config.default_base_url
        self._openai_api_key = api_key or settings.OPENAI_API_KEY
        self._openai_embedding_model = getattr(settings, "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        
        # 本地 fastembed 初始化（延迟）
        self._embed_provider: str = getattr(settings, "EMBED_PROVIDER", "local_fastembed")
        self._fastembed_model_name: str = getattr(settings, "FASTEMBED_MODEL", "BAAI/bge-small-zh-v1.5")
        self._fastembed_model = None
        self._embedding_preloaded = False
        
        # Anthropic 初始化
        self._anthropic_client = None
        self._anthropic_model = getattr(settings, "ANTHROPIC_MODEL", "claude-3-7-sonnet-latest")
        self._anthropic_api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
        
        # 初始化 provider 特定的客户端
        self._init_provider_client()
        
        # 初始化限流器（每个 provider 独立的限流器）
        self._init_rate_limiter()
        
        # 缓存配置
        self._cache_enabled: bool = bool(getattr(settings, "LLM_ENABLE_CACHE", True))
        self._cache_ttl: float = float(getattr(settings, "LLM_CACHE_TTL_SECONDS", 30.0))
        self._cache_max: int = int(getattr(settings, "LLM_CACHE_MAX_ITEMS", 512))
        if not hasattr(LLMClient, "_resp_cache"):
            LLMClient._resp_cache: Dict[str, tuple[float, Any]] = {}
        
        # 冷却时间（全局共享，用于 rate limit）
        if not hasattr(LLMClient, "_cooldown_until"):
            LLMClient._cooldown_until = 0.0
        
        # 使用量追踪
        self._enable_usage_tracking = getattr(settings, "ENABLE_USAGE_TRACKING", True)
        if self._enable_usage_tracking and LLMClient._usage_tracker is None:
            LLMClient._usage_tracker = UsageTracker()
        
        # 检查 fastembed 缓存
        if self._embed_provider == "local_fastembed":
            self._check_fastembed_cache()

    def _init_provider_client(self) -> None:
        """初始化 provider 特定的客户端"""
        if self.provider == "openai_compatible":
            try:
                from openai import AsyncOpenAI
                
                self._openai_client = AsyncOpenAI(
                    api_key=self._openai_api_key,
                    base_url=self._openai_base_url,
                    max_retries=0,
                )
                logger.debug(f"OpenAI-compatible client initialized for {self._provider_name}")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                self._openai_client = None
        
        elif self.provider == "anthropic":
            try:
                from anthropic import AsyncAnthropic
                
                self._anthropic_client = AsyncAnthropic(api_key=self._anthropic_api_key)
                logger.debug("Anthropic client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Anthropic client: {e}")
                self._anthropic_client = None

    def _init_rate_limiter(self) -> None:
        """初始化限流器"""
        # 基于 provider 名称的限流器键
        rate_key = f"_rate_lock_{self._provider_name}"
        rpm_key = f"_call_timestamps_{self._provider_name}"
        sem_key = f"_semaphore_{self._provider_name}"
        
        if not hasattr(LLMClient, rate_key):
            setattr(LLMClient, rate_key, asyncio.Lock())
        if not hasattr(LLMClient, rpm_key):
            setattr(LLMClient, rpm_key, deque())
        if not hasattr(LLMClient, sem_key):
            setattr(LLMClient, sem_key, asyncio.Semaphore(max(1, self._concurrency_limit)))

    def _check_fastembed_cache(self) -> None:
        """检查 fastembed 模型缓存"""
        try:
            import os
            cache_path = os.environ.get('FASTEMBED_CACHE_PATH', '/data/fastembed_cache')
            model_cache_dir = os.path.join(cache_path, 'models')
            if os.path.exists(model_cache_dir):
                import glob
                model_files = glob.glob(os.path.join(model_cache_dir, '**', '*'), recursive=True)
                if len(model_files) > 5:
                    self._embedding_preloaded = True
                    logger.debug(f"FastEmbed cache found with {len(model_files)} files")
        except Exception as e:
            logger.debug(f"Error checking fastembed cache: {e}")

    async def warmup_embedding_model(self) -> bool:
        """预热 embedding 模型，避免首次请求时的下载延迟"""
        if self._embedding_preloaded:
            return True
        
        if self._embed_provider != "local_fastembed":
            self._embedding_preloaded = True
            return True
        
        if self._fastembed_model is not None:
            self._embedding_preloaded = True
            return True
        
        for attempt in range(3):
            try:
                loop = asyncio.get_event_loop()
                
                def _load_model():
                    from fastembed import TextEmbedding
                    self._fastembed_model = TextEmbedding(model_name=self._fastembed_model_name)
                    return True
                
                await loop.run_in_executor(None, _load_model)
                self._embedding_preloaded = True
                logger.info("FastEmbed model preloaded successfully")
                return True
            
            except Exception as e:
                logger.warning(f"FastEmbed preload attempt {attempt + 1}/3 failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(3 + attempt * 2)
                else:
                    logger.warning("FastEmbed preload failed, will use fallback strategy")
                    self._embedding_preloaded = True
                    return False
        
        return False

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
            cache_key = f"cj::{self._provider_name}::{self._openai_model}::{hash(system_prompt)}::{hash(user_prompt)}::{temperature}::{max_tokens}"
            hit = self._cache_get(cache_key)
            if hit is not None:
                return hit
        
        if self.provider == "openai_compatible" and self._openai_client is not None:
            result = await self._chat_json_openai(system_prompt, user_prompt, temperature, max_tokens, cache_key)
            return result
        
        if self.provider == "anthropic" and self._anthropic_client is not None:
            result = await self._chat_json_anthropic(system_prompt, user_prompt, temperature, max_tokens, cache_key)
            return result
        
        raise RuntimeError("LLM provider not properly configured or SDK missing")

    async def _chat_json_openai(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        cache_key: Optional[str],
    ) -> Dict[str, Any]:
        """OpenAI 兼容的 JSON 输出"""
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
                
                # 记录使用量
                if hasattr(response, 'usage'):
                    self._record_usage(
                        response.usage.prompt_tokens,
                        response.usage.completion_tokens,
                    )
                
                self._cache_put(cache_key, parsed)
                return parsed
            
            except Exception as e:
                if self._is_retryable_error(e):
                    if self._is_rate_limit_error(e):
                        LLMClient._cooldown_until = time.monotonic() + float(getattr(settings, "LLM_COOLDOWN_SECONDS", 20.0))
                    await self._backoff_sleep(attempt)
                    continue
                raise
            finally:
                self._release_rate_slot()

    async def _chat_json_anthropic(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        cache_key: Optional[str],
    ) -> Dict[str, Any]:
        """Anthropic Claude 的 JSON 输出"""
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
                
                # 记录使用量
                if hasattr(msg, 'usage'):
                    self._record_usage(
                        msg.usage.input_tokens,
                        msg.usage.output_tokens,
                    )
                
                self._cache_put(cache_key, parsed)
                return parsed
            
            except Exception as e:
                if self._is_retryable_error(e):
                    if self._is_rate_limit_error(e):
                        LLMClient._cooldown_until = time.monotonic() + float(getattr(settings, "LLM_COOLDOWN_SECONDS", 20.0))
                    await self._backoff_sleep(attempt)
                    continue
                raise
            finally:
                self._release_rate_slot()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """生成嵌入向量列表。根据 embedding 策略选择提供方。"""
        
        # local_first 策略：优先使用本地 embedding
        if self._embedding_strategy == "local_first":
            result = await self._embed_local(texts)
            if result:
                return result
            logger.debug(f"Local embedding failed for {self._provider_name}, falling back to OpenAI")
        
        # openai_only 策略 或 local_first 回退
        if self.provider == "openai_compatible" and self._openai_client is not None:
            result = await self._embed_openai(texts)
            if result:
                return result
        
        logger.error("All embedding methods failed")
        return []

    async def _embed_local(self, texts: List[str]) -> Optional[List[List[float]]]:
        """使用本地 fastembed 生成向量"""
        if self._embed_provider != "local_fastembed":
            return None
        
        if self._fastembed_model is None:
            for attempt in range(3):
                try:
                    from fastembed import TextEmbedding
                    loop = asyncio.get_event_loop()
                    
                    def _load():
                        self._fastembed_model = TextEmbedding(model_name=self._fastembed_model_name)
                    
                    await loop.run_in_executor(None, _load)
                    break
                except Exception as e:
                    logger.warning(f"FastEmbed load attempt {attempt + 1}/3: {e}")
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        self._fastembed_model = None
                        return None
        
        if self._fastembed_model is None:
            return None
        
        try:
            vectors: List[List[float]] = []
            for emb in self._fastembed_model.embed(texts):
                vectors.append([float(x) for x in emb])
            return vectors
        except Exception as e:
            logger.warning(f"FastEmbed embedding failed: {e}")
            self._fastembed_model = None
            return None

    async def _embed_openai(self, texts: List[str]) -> Optional[List[List[float]]]:
        """使用 OpenAI 兼容接口生成向量"""
        if self.provider != "openai_compatible" or self._openai_client is None:
            return None
        
        attempts = max(1, int(getattr(settings, 'LLM_MAX_RETRIES', 1)))
        for attempt in range(attempts):
            await self._acquire_rate_slot()
            try:
                resp = await self._openai_client.embeddings.create(
                    model=self._openai_embedding_model,
                    input=texts,
                )
                
                vectors = [[float(x) for x in d.embedding] for d in resp.data]
                
                # 记录使用量
                if hasattr(resp, 'usage'):
                    self._record_usage(
                        resp.usage.prompt_tokens,
                        resp.usage.completion_tokens,
                    )
                
                return vectors
            
            except Exception as e:
                if self._is_retryable_error(e):
                    if self._is_rate_limit_error(e):
                        LLMClient._cooldown_until = time.monotonic() + float(getattr(settings, "LLM_COOLDOWN_SECONDS", 20.0))
                    await self._backoff_sleep(attempt)
                    continue
                raise
            finally:
                self._release_rate_slot()
        
        return None

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
            return await self._chat_text_openai(system_prompt, user_prompt, temperature, max_tokens)
        
        if self.provider == "anthropic" and self._anthropic_client is not None:
            return await self._chat_text_anthropic(system_prompt, user_prompt, temperature, max_tokens)
        
        raise RuntimeError("LLM provider not properly configured or SDK missing")

    async def _chat_text_openai(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """OpenAI 兼容的文本输出"""
        cache_key = None
        if self._cache_enabled:
            cache_key = f"ct::{self._provider_name}::{self._openai_model}::{hash(system_prompt)}::{hash(user_prompt)}::{temperature}::{max_tokens}"
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
                
                # 记录使用量
                if hasattr(response, 'usage'):
                    self._record_usage(
                        response.usage.prompt_tokens,
                        response.usage.completion_tokens,
                    )
                
                self._cache_put(cache_key, text)
                return text
            
            except Exception as e:
                if self._is_retryable_error(e):
                    if self._is_rate_limit_error(e):
                        LLMClient._cooldown_until = time.monotonic() + float(getattr(settings, "LLM_COOLDOWN_SECONDS", 20.0))
                    await self._backoff_sleep(attempt)
                    continue
                raise
            finally:
                self._release_rate_slot()

    async def _chat_text_anthropic(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Anthropic Claude 的文本输出"""
        cache_key = None
        if self._cache_enabled:
            cache_key = f"ct::{self._provider_name}::anthropic::{hash(system_prompt)}::{hash(user_prompt)}::{temperature}::{max_tokens}"
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
                
                # 记录使用量
                if hasattr(msg, 'usage'):
                    self._record_usage(
                        msg.usage.input_tokens,
                        msg.usage.output_tokens,
                    )
                
                self._cache_put(cache_key, text)
                return text
            
            except Exception as e:
                if self._is_retryable_error(e):
                    if self._is_rate_limit_error(e):
                        LLMClient._cooldown_until = time.monotonic() + float(getattr(settings, "LLM_COOLDOWN_SECONDS", 20.0))
                    await self._backoff_sleep(attempt)
                    continue
                raise
            finally:
                self._release_rate_slot()

    def _record_usage(self, input_tokens: int, output_tokens: int) -> None:
        """记录使用量"""
        if not self._enable_usage_tracking or LLMClient._usage_tracker is None:
            return
        
        LLMClient._usage_tracker.record(
            self._provider_name,
            input_tokens,
            output_tokens,
        )
        
        logger.debug(
            f"Usage tracked: {self._provider_name}, "
            f"input_tokens={input_tokens}, output_tokens={output_tokens}"
        )

    @staticmethod
    def get_usage_summary() -> Dict[str, Any]:
        """获取全局使用量统计"""
        if LLMClient._usage_tracker is None:
            return {"total_input_tokens": 0, "total_output_tokens": 0, "message": "Usage tracking not enabled"}
        
        return LLMClient._usage_tracker.get_summary()

    @staticmethod
    def _safe_json_loads(text: str) -> Dict[str, Any]:
        """稳健解析 JSON：优先直接解析，失败则提取第一个 {...} 或 [...] 片段。"""
        try:
            return json.loads(text)
        except Exception:
            pass
        
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
        
        return {}

    def _cache_get(self, key: Optional[str]) -> Optional[Any]:
        """从缓存获取"""
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
        """存入缓存"""
        if not self._cache_enabled or not key:
            return
        
        try:
            cache: Dict[str, tuple[float, Any]] = getattr(LLMClient, "_resp_cache")
            
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
        """判断是否为可重试的错误"""
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
        """判断是否为限流错误"""
        text = str(e).lower()
        return "429" in text or "rate limit" in text

    async def _backoff_sleep(self, attempt: int) -> None:
        """指数退避睡眠"""
        base = float(getattr(settings, "LLM_BACKOFF_BASE_SECONDS", 1.0))
        frac = time.monotonic() % 1.0
        jitter = 0.25 * frac
        delay = min(5.0, base * (2 ** attempt) + jitter)
        await asyncio.sleep(delay)

    async def _acquire_rate_slot(self) -> None:
        """获取限流槽位"""
        # 等待冷却时间
        try:
            while time.monotonic() < float(getattr(LLMClient, "_cooldown_until", 0.0)):
                await asyncio.sleep(0.2)
        except Exception:
            pass
        
        # 获取限流器
        sem_key = f"_semaphore_{self._provider_name}"
        sem: asyncio.Semaphore = getattr(LLMClient, sem_key)
        await sem.acquire()
        
        # RPM 限制
        rate_key = f"_rate_lock_{self._provider_name}"
        rpm_key = f"_call_timestamps_{self._provider_name}"
        limit = self._rpm_limit
        
        lock: asyncio.Lock = getattr(LLMClient, rate_key)
        q: deque = getattr(LLMClient, rpm_key)
        
        while True:
            now = time.monotonic()
            async with lock:
                cutoff = now - 60.0
                while q and q[0] < cutoff:
                    q.popleft()
                
                if len(q) < limit:
                    q.append(now)
                    return
                
                wait_secs = max(0.01, (q[0] + 60.0) - now)
            
            await asyncio.sleep(min(wait_secs, 0.5))

    def _release_rate_slot(self) -> None:
        """释放限流槽位"""
        try:
            sem_key = f"_semaphore_{self._provider_name}"
            sem: asyncio.Semaphore = getattr(LLMClient, sem_key)
            sem.release()
        except Exception:
            pass

    @classmethod
    def in_cooldown(cls) -> bool:
        """检查是否在冷却期"""
        try:
            return time.monotonic() < float(getattr(cls, "_cooldown_until", 0.0))
        except Exception:
            return False


