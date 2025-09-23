from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, PostgresDsn


class Settings(BaseSettings):
    """应用配置"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # 允许 .env 中未使用的键存在
    )
    
    # 应用设置
    APP_NAME: str = "阿福 (Family AI Assistant)"
    APP_ENV: str = Field(default="development", pattern="^(development|production|test)$")
    DEBUG: bool = Field(default=True)
    
    # 数据库
    DATABASE_URL: PostgresDsn
    
    # Threema配置（本地可不启用）
    THREEMA_GATEWAY_ID: str | None = Field(default=None, description="Threema Gateway ID (starts with *)")
    THREEMA_SECRET: str | None = Field(default=None, description="Threema Gateway Secret")
    THREEMA_PRIVATE_KEY: str = Field(default="", description="Threema private key (hex encoded)")
    THREEMA_WEBHOOK_URL: str = Field(default="", description="Public URL for Threema webhook")
    
    # LLM 配置（支持 OpenAI 兼容/国内厂商兼容）
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "kimi-k2-turbo-preview"
    OPENAI_BASE_URL: str = Field(default="", description="可选，OpenAI 兼容基座，例如 Qwen: https://dashscope.aliyuncs.com/compatible-mode/v1")
    AI_PROVIDER: str = Field(default="openai_compatible", description="llm 提供商标识：openai_compatible/anthropic/mock")
    OPENAI_EMBEDDING_MODEL: str = Field(default="text-embedding-3-small", description="用于生成语义向量的模型名")
    # LLM 限流与预算
    LLM_RPM_LIMIT: int = Field(default=30, description="全局每分钟最大 LLM 调用次数（RPM）")
    LLM_CONCURRENCY: int = Field(default=3, description="并发的 LLM 调用上限（信号量）")
    LOW_LLM_BUDGET: bool = Field(default=False, description="低预算模式：跳过/延后部分 LLM 环节以减少调用次数")
    LLM_MAX_RETRIES: int = Field(default=1, description="LLM调用最大重试次数（降低减少API消耗）")
    LLM_BACKOFF_BASE_SECONDS: float = Field(default=1.0, description="遭遇429/5xx时的退避起始秒数（指数退避基数）")
    LLM_COOLDOWN_SECONDS: float = Field(default=20.0, description="发生限流后进入降级/冷却的时长")
    LLM_ENABLE_CACHE: bool = Field(default=True, description="是否启用小型结果缓存以去重相同请求")
    LLM_CACHE_TTL_SECONDS: float = Field(default=30.0, description="结果缓存TTL（秒）")
    LLM_CACHE_MAX_ITEMS: int = Field(default=512, description="结果缓存最大条目数（进程内）")
    # 向量提供方（默认使用本地开源 fastembed）
    EMBED_PROVIDER: str = Field(default="local_fastembed", description="embedding 提供方：local_fastembed/openai_compatible")
    FASTEMBED_MODEL: str = Field(default="BAAI/bge-small-zh-v1.5", description="fastembed 本地向量模型名（建议 bge-small/m3e/gte small/base 级别）")
    # Anthropic（可选）
    ANTHROPIC_API_KEY: str = Field(default="", description="Anthropic API Key，可选")
    ANTHROPIC_MODEL: str = Field(default="claude-3-7-sonnet-latest", description="Anthropic 模型名")
    
    # 媒体与多模态
    MEDIA_ROOT: str = Field(default="/data/media", description="媒体文件存储根目录")
    MEDIA_PUBLIC_BASE_URL: str = Field(default="", description="对外可访问的媒体基础URL，如 https://example.com/media")
    SIGNING_SECRET: str = Field(default="", description="媒体签名链接的密钥")
    ENABLE_STT: bool = Field(default=True, description="启用语音转写（OpenAI Whisper API 优先）")
    ENABLE_OCR: bool = Field(default=False, description="启用图片OCR（需要额外依赖或Vision能力）")
    ENABLE_VISION: bool = Field(default=False, description="启用 LLM Vision 能力用于图片理解（可选）")
    OPENAI_STT_MODEL: str = Field(default="whisper-1", description="OpenAI 语音转写模型名，如 whisper-1 或 gpt-4o-transcribe")
    OPENAI_VISION_MODEL: str = Field(default="gpt-4o-mini", description="OpenAI Vision 支持的模型名")
    
    # 安全设置
    SECRET_KEY: str
    ALLOWED_USERS: List[str] = Field(default_factory=list)
    FAMILY_SHARED_USER_IDS: List[str] = Field(default_factory=list, description="家庭共享的用户ID列表，默认家庭范围统计使用")
    
    # 日志
    LOG_LEVEL: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    
    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"
    
    def parse_allowed_users(self) -> List[str]:
        """解析允许的用户列表"""
        if isinstance(self.ALLOWED_USERS, str):
            return [u.strip() for u in self.ALLOWED_USERS.split(",") if u.strip()]
        return self.ALLOWED_USERS

    def get_family_shared_user_ids(self) -> List[str]:
        """获取家庭共享的用户ID配置"""
        ids = self.FAMILY_SHARED_USER_IDS
        if isinstance(ids, str):
            return [v.strip() for v in ids.split(',') if v.strip()]
        return list(ids)


# 创建全局配置实例
settings = Settings()
