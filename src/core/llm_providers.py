"""
LLM Provider 配置与管理

每个 provider 定义：
- API 端点和基本配置
- 限流策略（RPM、并发）
- Embedding 策略（本地/远程）
- 区域（CN/US）

使用量追踪：
- 记录 API 调用次数
- 记录 token 消耗（输入/输出）
- 不计算成本（由用户根据官方定价自行计算）
"""

from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class ProviderConfig:
    """Provider 配置"""
    name: str                          # Provider 名称
    provider_type: str                 # 提供商类型：openai_compatible/anthropic
    default_base_url: Optional[str]   # 默认 API 基址
    default_model: str                # 默认模型名
    rpm_limit: int                    # 每分钟请求限制
    concurrency_limit: int            # 并发限制
    embedding_strategy: str            # embedding 策略：local_first/openai_only
    description: str                  # 描述
    region: str                       # 地域：cn/us


class ProviderRegistry:
    """Provider 预配置注册表"""

    PROVIDERS: Dict[str, ProviderConfig] = {
        # OpenAI
        "openai": ProviderConfig(
            name="OpenAI",
            provider_type="openai_compatible",
            default_base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
            rpm_limit=500,
            concurrency_limit=10,
            embedding_strategy="openai_only",
            description="OpenAI GPT-4o, GPT-4o-mini",
            region="us",
        ),

        # Moonshot Kimi
        "kimi": ProviderConfig(
            name="Kimi (Moonshot)",
            provider_type="openai_compatible",
            default_base_url="https://api.moonshot.cn/v1",
            default_model="moonshot-v1-128k",
            rpm_limit=60,
            concurrency_limit=5,
            embedding_strategy="local_first",
            description="Moonshot Kimi - 长文本处理能力强",
            region="cn",
        ),

        # Alibaba Qwen
        "qwen": ProviderConfig(
            name="Qwen (Alibaba DashScope)",
            provider_type="openai_compatible",
            default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            default_model="qwen-turbo",
            rpm_limit=2000,
            concurrency_limit=20,
            embedding_strategy="local_first",
            description="Alibaba Qwen - 最稳定，文档完善",
            region="cn",
        ),

        # ByteDance Doubao
        "doubao": ProviderConfig(
            name="Doubao (ByteDance)",
            provider_type="openai_compatible",
            default_base_url="https://ark.cn-beijing.volces.com/api/v3",
            default_model="ep-20250101000000-xxxxx",  # 需使用实际的Endpoint ID
            rpm_limit=1000,
            concurrency_limit=10,
            embedding_strategy="local_first",
            description="ByteDance Doubao - 字节系，性能稳定",
            region="cn",
        ),

        # DeepSeek
        "deepseek": ProviderConfig(
            name="DeepSeek",
            provider_type="openai_compatible",
            default_base_url="https://api.deepseek.com/v1",
            default_model="deepseek-chat",
            rpm_limit=500,
            concurrency_limit=10,
            embedding_strategy="local_first",
            description="DeepSeek - 最便宜，性价比之王",
            region="cn",
        ),

        # Anthropic Claude
        "anthropic": ProviderConfig(
            name="Anthropic Claude",
            provider_type="anthropic",
            default_base_url=None,
            default_model="claude-3-7-sonnet-latest",
            rpm_limit=100,
            concurrency_limit=5,
            embedding_strategy="openai_only",
            description="Anthropic Claude 3.7 Sonnet",
            region="us",
        ),
    }

    @classmethod
    def get_provider(cls, provider_name: str) -> Optional[ProviderConfig]:
        """获取 Provider 配置"""
        return cls.PROVIDERS.get(provider_name.lower())

    @classmethod
    def get_default_config(cls, provider_type: str) -> Optional[ProviderConfig]:
        """根据 provider 类型获取默认配置"""
        if provider_type == "openai_compatible":
            return cls.PROVIDERS.get("openai")
        elif provider_type == "anthropic":
            return cls.PROVIDERS.get("anthropic")
        return None

    @classmethod
    def list_providers(cls) -> Dict[str, str]:
        """列出所有可用的 provider"""
        return {
            name: config.description
            for name, config in cls.PROVIDERS.items()
        }


class UsageTracker:
    """使用量追踪器（仅追踪使用，不计算成本）

    记录指标：
    - API 调用次数
    - 输入 tokens 总数
    - 输出 tokens 总数
    - 每个 provider 的分类统计

    用户应根据官方定价自行计算成本。
    """

    def __init__(self):
        self.total_calls = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0

        # 按 provider 分类
        self.provider_stats: Dict[str, Dict] = {}

    def record(
        self,
        provider_name: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """记录一次 API 调用的使用量"""
        self.total_calls += 1
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

        # 按 provider 统计
        if provider_name not in self.provider_stats:
            self.provider_stats[provider_name] = {
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
            }

        stats = self.provider_stats[provider_name]
        stats["calls"] += 1
        stats["input_tokens"] += input_tokens
        stats["output_tokens"] += output_tokens

    def get_summary(self) -> Dict[str, any]:
        """获取使用量统计摘要"""
        total_tokens = self.total_input_tokens + self.total_output_tokens

        summary = {
            "total_calls": self.total_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": total_tokens,
            "avg_tokens_per_call": (
                total_tokens // self.total_calls if self.total_calls > 0 else 0
            ),
        }

        # 按 provider 分类
        if self.provider_stats:
            summary["by_provider"] = {}
            for provider, stats in self.provider_stats.items():
                summary["by_provider"][provider] = {
                    "calls": stats["calls"],
                    "input_tokens": stats["input_tokens"],
                    "output_tokens": stats["output_tokens"],
                    "total_tokens": stats["input_tokens"] + stats["output_tokens"],
                    "avg_tokens_per_call": (
                        (stats["input_tokens"] + stats["output_tokens"])
                        // stats["calls"]
                        if stats["calls"] > 0
                        else 0
                    ),
                }

        return summary

    def get_pricing_guide(self) -> Dict[str, Dict]:
        """获取各 provider 的定价信息指导（用户应查看官方）"""
        return {
            "qwen": {
                "name": "Alibaba Qwen",
                "pricing_url": "https://help.aliyun.com/zh/dashscope/developer-reference/model-square",
                "note": "查看 Pricing 标签了解最新价格",
            },
            "deepseek": {
                "name": "DeepSeek",
                "pricing_url": "https://platform.deepseek.com/api-docs",
                "note": "查看 Pricing 标签了解最新价格",
            },
            "doubao": {
                "name": "ByteDance Doubao",
                "pricing_url": "https://www.volcengine.com/docs/82379/1298459",
                "note": "查看官方文档了解最新价格",
            },
            "kimi": {
                "name": "Moonshot Kimi",
                "pricing_url": "https://platform.moonshot.cn/docs/pricing",
                "note": "查看官网了解最新价格",
            },
            "openai": {
                "name": "OpenAI",
                "pricing_url": "https://openai.com/pricing/",
                "note": "查看官网了解最新价格",
            },
            "anthropic": {
                "name": "Anthropic Claude",
                "pricing_url": "https://www.anthropic.com/pricing",
                "note": "查看官网了解最新价格",
            },
        }
