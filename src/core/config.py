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
    # Provider 选择：openai/kimi/qwen/doubao/deepseek/anthropic
    LLM_PROVIDER_NAME: str = Field(default="qwen", description="LLM provider 标识：openai/kimi/qwen/doubao/deepseek/anthropic")
    
    # Provider 通用配置（优先级高于预配置）
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = Field(default="", description="模型名，为空则使用provider预配置")
    OPENAI_BASE_URL: str = Field(default="", description="API基址，为空则使用provider预配置")
    AI_PROVIDER: str = Field(default="openai_compatible", description="llm 提供商标识：openai_compatible/anthropic（通常不需要改）")
    OPENAI_EMBEDDING_MODEL: str = Field(default="text-embedding-3-small", description="用于生成语义向量的模型名")
    
    # LLM 限流与预算
    LLM_RPM_LIMIT: int = Field(default=0, description="每分钟最大LLM调用次数，为0则使用provider预配置")
    LLM_CONCURRENCY: int = Field(default=0, description="并发LLM调用上限，为0则使用provider预配置")
    LOW_LLM_BUDGET: bool = Field(default=False, description="低预算模式：跳过/延后部分LLM环节以减少调用次数")
    LLM_MAX_RETRIES: int = Field(default=1, description="LLM调用最大重试次数")
    LLM_BACKOFF_BASE_SECONDS: float = Field(default=1.0, description="遭遇429/5xx时的退避起始秒数")
    LLM_COOLDOWN_SECONDS: float = Field(default=20.0, description="发生限流后进入降级/冷却的时长")
    LLM_ENABLE_CACHE: bool = Field(default=True, description="是否启用小型结果缓存以去重相同请求")
    LLM_CACHE_TTL_SECONDS: float = Field(default=30.0, description="结果缓存TTL（秒）")
    LLM_CACHE_MAX_ITEMS: int = Field(default=512, description="结果缓存最大条目数（进程内）")
    
    # 向量提供方（默认使用本地开源 fastembed）
    EMBED_PROVIDER: str = Field(default="local_fastembed", description="embedding 提供方：local_fastembed/openai_compatible")
    FASTEMBED_MODEL: str = Field(default="BAAI/bge-small-zh-v1.5", description="fastembed 本地向量模型名")
    
    # Anthropic（可选）
    ANTHROPIC_API_KEY: str = Field(default="", description="Anthropic API Key，可选")
    ANTHROPIC_MODEL: str = Field(default="claude-3-7-sonnet-latest", description="Anthropic 模型名")
    
    # 测试评估器LLM配置（用于集成测试中的AI评估AI）
    EVALUATOR_LLM_PROVIDER: str = Field(default="openai_compatible", description="评估器LLM提供商")
    EVALUATOR_LLM_MODEL: str = Field(default="gpt-4o-mini", description="评估器使用的模型")
    EVALUATOR_LLM_BASE_URL: str = Field(default="https://api.openai.com/v1", description="评估器LLM的API地址")
    EVALUATOR_LLM_API_KEY: str = Field(default="", description="评估器LLM的API Key")
    
    # 媒体与多模态
    MEDIA_ROOT: str = Field(default="/data/media", description="媒体文件存储根目录")
    MEDIA_PUBLIC_BASE_URL: str = Field(default="", description="对外可访问的媒体基础URL")
    SIGNING_SECRET: str = Field(default="", description="媒体签名链接的密钥")
    ENABLE_STT: bool = Field(default=True, description="启用语音转写")
    ENABLE_OCR: bool = Field(default=False, description="启用图片OCR")
    ENABLE_VISION: bool = Field(default=False, description="启用LLM Vision能力")
    OPENAI_STT_MODEL: str = Field(default="whisper-1", description="OpenAI语音转写模型名")
    OPENAI_VISION_MODEL: str = Field(default="gpt-4o-mini", description="OpenAI Vision模型名")
    
    # 安全设置
    SECRET_KEY: str
    ALLOWED_USERS: List[str] = Field(default_factory=list)
    FAMILY_SHARED_USER_IDS: List[str] = Field(default_factory=list, description="家庭共享的用户ID列表")
    
    # 日志与成本追踪
    LOG_LEVEL: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    ENABLE_USAGE_TRACKING: bool = Field(default=True, description="启用LLM成本追踪")
    
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
