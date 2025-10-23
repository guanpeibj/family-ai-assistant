from sqlalchemy import (
    Column,
    String,
    DateTime,
    Text,
    Float,
    Index,
    Numeric,
    Boolean,
    ForeignKey,
    Enum,
    UniqueConstraint,
)
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
    channel = Column(
        Enum(
            ChannelType,
            name="channel_type",
            create_type=False,
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    channel_user_id = Column(String(255), nullable=False)  # Threema ID、邮箱、OpenID等
    channel_data = Column(JSONB)  # 渠道特定数据（如昵称等）
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        UniqueConstraint('channel', 'channel_user_id', name='uq_channel_user'),
    )


class FamilyHousehold(Base):
    """家庭表 - 描述一户家庭的成员集合"""
    __tablename__ = 'family_households'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    slug = Column(String(128), nullable=False, unique=True, index=True)  # 例如 "primary"
    display_name = Column(String(255), nullable=False)
    description = Column(Text)
    config = Column(JSONB, default=dict)  # 额外配置：共享策略、默认时区等


class FamilyMember(Base):
    """家庭成员表 - 支持有无账号的成员"""
    __tablename__ = 'family_members'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id = Column(UUID(as_uuid=True), ForeignKey('family_households.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    member_key = Column(String(128), nullable=False)  # 机器可读的唯一键，例如 "mom"、"child_1"
    display_name = Column(String(255), nullable=False)  # 对外展示名称
    relationship = Column(String(64))  # 可选：妈妈/爸爸/孩子
    profile = Column(JSONB, default=dict)  # 可选信息：生日、偏好等
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint('household_id', 'member_key', name='uq_family_member_household_key'),
    )


class FamilyMemberAccount(Base):
    """家庭成员与用户账号的映射：支持多渠道/多账号"""
    __tablename__ = 'family_member_accounts'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    member_id = Column(UUID(as_uuid=True), ForeignKey('family_members.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    is_primary = Column(Boolean, default=False)
    labels = Column(JSONB, default=dict)  # 可选：渠道标签、别名

    __table_args__ = (
        UniqueConstraint('member_id', 'user_id', name='uq_family_member_user'),
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
    embedding = Column(Vector(512))  # 语义向量 (BAAI/bge-small-zh-v1.5)
    
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
    memory_id = Column(UUID(as_uuid=True), ForeignKey('memories.id'), index=True)  # 关联的记忆（外键）
    remind_at = Column(DateTime(timezone=True), nullable=False, index=True)
    sent_at = Column(DateTime(timezone=True))  # 发送时间，NULL表示未发送
    payload = Column(JSONB, nullable=True)  # AI 提供的补充信息（scope/person/message模板等）
    external_key = Column(String(255), nullable=True, index=True)  # 可选的幂等键（由AI传入）
    
    __table_args__ = (
        Index('idx_reminders_pending', 'remind_at', postgresql_where=(sent_at.is_(None))),
    )


class Interaction(Base):
    """交互追踪表 - 用于全链路回溯与排障"""
    __tablename__ = 'interactions'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # 关联与上下文
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    thread_id = Column(String(255), index=True)
    channel = Column(String(64), index=True)
    message_id = Column(String(255), index=True)

    # 交互内容
    input_text = Column(Text, nullable=False)
    understanding_json = Column(JSONB)
    actions_json = Column(JSONB)
    tool_calls_json = Column(JSONB)
    response_text = Column(Text)
    error = Column(Text)

    __table_args__ = (
        Index('idx_interactions_user_created', 'user_id', 'created_at'),
    )
