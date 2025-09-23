from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import structlog

from ..core.config import settings
from sqlalchemy import text

logger = structlog.get_logger()

# 创建异步引擎（确保使用 asyncpg 驱动）
raw_database_url = str(settings.DATABASE_URL)
if raw_database_url.startswith("postgres://"):
    # 兼容旧的 postgres:// 前缀
    raw_database_url = raw_database_url.replace("postgres://", "postgresql://", 1)

if raw_database_url.startswith("postgresql://") and "+asyncpg" not in raw_database_url:
    async_database_url = raw_database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    async_database_url = raw_database_url

engine = create_async_engine(
    async_database_url,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# 创建异步会话工厂
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# 创建Base类
Base = declarative_base()


async def init_db():
    """初始化数据库"""
    async with engine.begin() as conn:
        # 安装扩展（幂等）
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS \"pgcrypto\"")
        # 创建所有表
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized successfully")


async def close_db():
    """关闭数据库连接"""
    await engine.dispose()
    logger.info("Database connections closed")


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# 依赖注入函数
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI依赖注入函数"""
    async with get_session() as session:
        yield session
