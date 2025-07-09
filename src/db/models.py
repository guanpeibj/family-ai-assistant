from sqlalchemy import Column, String, DateTime, Text, Float, Index, Numeric, Boolean, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
import uuid
import enum

from .database import Base


class ChannelType(enum.Enum):
    """支持的渠道类型"""
    THREEMA = "threema"
    EMAIL = "email"
    WECHAT = "wechat"


class User(Base):
    """用户表 - 统一用户身份"""
    __tablename__ = 'users'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # 未来可以添加更多用户属性，但现在保持极简


class UserChannel(Base):
    """用户渠道绑定表"""
    __tablename__ = 'user_channels'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    channel = Column(Enum(ChannelType), nullable=False)
    channel_user_id = Column(String(255), nullable=False)  # Threema ID、邮箱、OpenID等
    channel_data = Column(JSONB)  # 渠道特定数据（如昵称等）
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        UniqueConstraint('channel', 'channel_user_id', name='uq_channel_user'),
    )


class Memory(Base):
    """通用记忆表 - AI驱动的数据存储"""
    __tablename__ = "memories"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    
    # 核心数据
    content = Column(Text, nullable=False)  # 原始内容
    ai_understanding = Column(JSONB, nullable=False)  # AI理解的所有信息
    embedding = Column(Vector(1536))  # 语义向量
    
    # 精确查询支持（可选，AI决定是否填充）
    amount = Column(Numeric(10, 2), index=True)  # 金额（如果是财务相关）
    occurred_at = Column(DateTime(timezone=True), index=True)  # 事件时间（如果AI识别出）
    
    __table_args__ = (
        Index('idx_memories_ai_understanding', 'ai_understanding', postgresql_using='gin'),
    )


class Reminder(Base):
    """提醒表 - 简化版"""
    __tablename__ = "reminders"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    memory_id = Column(UUID(as_uuid=True), index=True)  # 关联的记忆
    remind_at = Column(DateTime(timezone=True), nullable=False, index=True)
    sent = Column(DateTime(timezone=True))  # 发送时间，NULL表示未发送
    
    __table_args__ = (
        Index('idx_reminders_pending', 'remind_at', postgresql_where=(sent.is_(None))),
    )