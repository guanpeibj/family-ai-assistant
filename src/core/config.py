from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, PostgresDsn


class Settings(BaseSettings):
    """应用配置"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )
    
    # 应用设置
    APP_NAME: str = "Family AI Assistant"
    APP_ENV: str = Field(default="development", pattern="^(development|production|test)$")
    DEBUG: bool = Field(default=True)
    
    # 数据库
    DATABASE_URL: PostgresDsn
    
    # Threema配置
    THREEMA_ID: str
    THREEMA_SECRET: str
    
    # OpenAI配置
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4-turbo-preview"
    
    # 安全设置
    SECRET_KEY: str
    ALLOWED_USERS: List[str] = Field(default_factory=list)
    
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


# 创建全局配置实例
settings = Settings()
