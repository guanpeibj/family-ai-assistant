"""
统一的 LLM 客户端抽象：支持多厂商切换

当前支持：
- openai_compatible：任意 OpenAI 兼容接口（含 OpenAI、Grok、Qwen、Moonshot、GLM 等）
- anthropic：Claude 系列（可选安装 anthropic 依赖）
"""
from __future__ import annotations

from typing import Any, Dict, Optional
import json

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

        if self.provider == "openai_compatible":
            try:
                from openai import AsyncOpenAI

                self._openai_client = AsyncOpenAI(
                    api_key=self._openai_api_key,
                    base_url=self._openai_base_url,
                )
            except Exception as _:
                self._openai_client = None
        elif self.provider == "anthropic":
            try:
                from anthropic import AsyncAnthropic

                self._anthropic_client = AsyncAnthropic(api_key=self._anthropic_api_key)
            except Exception as _:
                self._anthropic_client = None

    async def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> Dict[str, Any]:
        """生成 JSON 响应。如果无法严格 JSON，则尝试解析文本中的 JSON。"""

        if self.provider == "openai_compatible" and self._openai_client is not None:
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
            return self._safe_json_loads(content)

        if self.provider == "anthropic" and self._anthropic_client is not None:
            # Anthropic 支持 JSON 输出，但不同模型行为略有差异，这里做稳健解析
            msg = await self._anthropic_client.messages.create(
                model=self._anthropic_model,
                system=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": user_prompt}],
            )
            # content 可能是多块，这里拼接为文本
            text_chunks = []
            for block in msg.content:
                if hasattr(block, "text"):
                    text_chunks.append(block.text)
                elif isinstance(block, dict) and block.get("type") == "text":
                    text_chunks.append(block.get("text", ""))
            content = "".join(text_chunks)
            return self._safe_json_loads(content)

        raise RuntimeError(
            "LLM provider not properly configured or SDK missing. Check AI_PROVIDER and API keys."
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """生成嵌入向量列表。优先使用本地 fastembed；可回退到 openai 兼容端。"""
        # 本地 fastembed（默认）
        if self._embed_provider == "local_fastembed":
            if self._fastembed_model is None:
                try:
                    from fastembed import TextEmbedding
                    self._fastembed_model = TextEmbedding(model_name=self._fastembed_model_name)
                except Exception as e:
                    # 回退到 openai 兼容
                    self._fastembed_model = None
            if self._fastembed_model is not None:
                # fastembed 同步接口，放在线程池可能更稳，这里小规模直接调用
                vectors: list[list[float]] = []
                for emb in self._fastembed_model.embed(texts):
                    # emb 可能是 numpy.ndarray(float32)；需转为 Python float 以便 JSON 序列化
                    try:
                        vectors.append([float(x) for x in emb])
                    except Exception:
                        vectors.append([float(x) for x in list(emb)])
                return vectors
        # 回退：openai 兼容
        if self.provider == "openai_compatible" and self._openai_client is not None:
            resp = await self._openai_client.embeddings.create(
                model=self._openai_embedding_model,
                input=texts,
            )
            # OpenAI 返回为 Python float 列表，但为一致性仍做一次显式转换
            return [[float(x) for x in d.embedding] for d in resp.data]
        # 最后兜底：返回空
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
            response = await self._openai_client.chat.completions.create(
                model=self._openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content

        if self.provider == "anthropic" and self._anthropic_client is not None:
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
            return "".join(text_chunks)

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


