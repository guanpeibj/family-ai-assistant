"""Initial database schema - unified migration

Revision ID: 20251017_initial
Revises: None
Create Date: 2025-10-17

这是合并后的初始迁移，包含所有表结构：
- users & user_channels（用户和多渠道支持）
- memories & reminders（核心记忆系统）
- interactions（交互追踪）
- family_households, family_members, family_member_accounts（家庭结构）
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = '20251017_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """创建完整的数据库架构"""
    
    # ========================================
    # 1. 用户相关表
    # ========================================
    
    # channel_type 枚举由 init_db.sql 创建，此处不再创建
    
    # users 表
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    )
    
    # user_channels 表（使用原生 SQL 避免 SQLAlchemy Enum 自动创建类型的问题）
    op.execute("""
        CREATE TABLE user_channels (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            channel channel_type NOT NULL,
            channel_user_id VARCHAR(255) NOT NULL,
            channel_data JSONB,
            is_primary BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_channel_user UNIQUE (channel, channel_user_id)
        )
    """)
    op.create_index('idx_user_channels_user_id', 'user_channels', ['user_id'])
    op.create_index('idx_user_channels_channel', 'user_channels', ['channel'])
    
    # ========================================
    # 2. 核心记忆系统
    # ========================================
    
    # memories 表（核心表）
    op.create_table(
        'memories',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('ai_understanding', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('embedding', Vector(512), nullable=True),  # BAAI/bge-small-zh-v1.5
        sa.Column('amount', sa.Numeric(10, 2), nullable=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=True),
        # 生成列（从 ai_understanding JSONB 中提取）
        sa.Column('thread_id_extracted', sa.Text(), sa.Computed("(ai_understanding->>'thread_id')", persisted=True)),
        sa.Column('type_extracted', sa.Text(), sa.Computed("(ai_understanding->>'type')", persisted=True)),
        sa.Column('category_extracted', sa.Text(), sa.Computed("(ai_understanding->>'category')", persisted=True)),
        sa.Column('person_extracted', sa.Text(), sa.Computed("(ai_understanding->>'person')", persisted=True)),
        sa.Column('metric_extracted', sa.Text(), sa.Computed("(ai_understanding->>'metric')", persisted=True)),
        sa.Column('subject_extracted', sa.Text(), sa.Computed("(ai_understanding->>'subject')", persisted=True)),
        sa.Column('source_extracted', sa.Text(), sa.Computed("(ai_understanding->>'source')", persisted=True)),
        sa.Column('value_extracted', sa.Numeric(), 
                  sa.Computed("CASE WHEN (ai_understanding->>'value') ~ '^-?\\d+(?:\\.\\d+)?$' THEN (ai_understanding->>'value')::numeric ELSE NULL END", persisted=True)),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    
    # memories 表索引
    op.create_index('ix_memories_user_id', 'memories', ['user_id'])
    op.create_index('ix_memories_created_at', 'memories', ['created_at'])
    op.create_index('ix_memories_amount', 'memories', ['amount'])
    op.create_index('ix_memories_occurred_at', 'memories', ['occurred_at'])
    op.create_index('idx_memories_user_created', 'memories', ['user_id', 'created_at'])
    
    # JSONB 索引
    op.create_index('idx_memories_ai_understanding', 'memories', ['ai_understanding'], postgresql_using='gin')
    op.create_index('idx_memories_ai_understanding_path', 'memories', ['ai_understanding'], postgresql_using='gin', postgresql_ops={'ai_understanding': 'jsonb_path_ops'})
    
    # JSONB 表达式索引
    op.execute("CREATE INDEX idx_memories_aiu_thread_id ON memories ((ai_understanding->>'thread_id'))")
    op.execute("CREATE INDEX idx_memories_aiu_type ON memories ((ai_understanding->>'type'))")
    op.execute("CREATE INDEX idx_memories_aiu_channel ON memories ((ai_understanding->>'channel'))")
    op.execute("CREATE INDEX idx_memories_person ON memories ((ai_understanding->>'person'))")
    op.execute("CREATE INDEX idx_memories_metric ON memories ((ai_understanding->>'metric'))")
    op.execute("CREATE INDEX idx_memories_intent ON memories ((ai_understanding->>'intent'))")
    
    # 全文和向量索引
    op.execute("CREATE INDEX idx_memories_content_trgm ON memories USING gin (content gin_trgm_ops)")
    op.execute("CREATE INDEX idx_memories_embedding_ivfflat ON memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")
    
    # reminders 表
    op.create_table(
        'reminders',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('memory_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('remind_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('external_key', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['memory_id'], ['memories.id']),
    )
    op.create_index('ix_reminders_memory_id', 'reminders', ['memory_id'])
    op.create_index('ix_reminders_remind_at', 'reminders', ['remind_at'])
    op.create_index('ix_reminders_external_key', 'reminders', ['external_key'])
    op.execute("CREATE INDEX idx_reminders_pending ON reminders (remind_at) WHERE sent_at IS NULL")
    
    # ========================================
    # 3. 交互追踪
    # ========================================
    
    op.create_table(
        'interactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('thread_id', sa.String(255), nullable=True),
        sa.Column('channel', sa.String(64), nullable=True),
        sa.Column('message_id', sa.String(255), nullable=True),
        sa.Column('input_text', sa.Text(), nullable=False),
        sa.Column('understanding_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('actions_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('tool_calls_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('response_text', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    op.create_index('idx_interactions_user_created', 'interactions', ['user_id', 'created_at'])
    op.create_index('ix_interactions_channel', 'interactions', ['channel'])
    op.create_index('ix_interactions_message_id', 'interactions', ['message_id'])
    
    # ========================================
    # 4. 家庭结构表
    # ========================================
    
    # family_households 表
    op.create_table(
        'family_households',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('slug', sa.String(128), nullable=False, unique=True),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index('ix_family_households_slug', 'family_households', ['slug'], unique=True)
    
    # family_members 表
    op.create_table(
        'family_members',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('household_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('member_key', sa.String(128), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('relationship', sa.String(64), nullable=True),
        sa.Column('profile', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.ForeignKeyConstraint(['household_id'], ['family_households.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('household_id', 'member_key', name='uq_family_member_household_key'),
    )
    op.create_index('ix_family_members_household_id', 'family_members', ['household_id'])
    
    # family_member_accounts 表
    op.create_table(
        'family_member_accounts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('member_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('labels', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(['member_id'], ['family_members.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('member_id', 'user_id', name='uq_family_member_user'),
    )
    op.create_index('ix_family_member_accounts_member_id', 'family_member_accounts', ['member_id'])
    op.create_index('ix_family_member_accounts_user_id', 'family_member_accounts', ['user_id'])
    
    print("✅ 数据库架构初始化完成")


def downgrade():
    """删除所有表"""
    
    # 删除家庭结构表
    op.drop_index('ix_family_member_accounts_user_id', table_name='family_member_accounts')
    op.drop_index('ix_family_member_accounts_member_id', table_name='family_member_accounts')
    op.drop_table('family_member_accounts')
    
    op.drop_index('ix_family_members_household_id', table_name='family_members')
    op.drop_table('family_members')
    
    op.drop_index('ix_family_households_slug', table_name='family_households')
    op.drop_table('family_households')
    
    # 删除交互追踪表
    op.drop_index('ix_interactions_message_id', table_name='interactions')
    op.drop_index('ix_interactions_channel', table_name='interactions')
    op.drop_index('idx_interactions_user_created', table_name='interactions')
    op.drop_table('interactions')
    
    # 删除记忆系统表
    op.drop_index('idx_reminders_pending', table_name='reminders')
    op.drop_index('ix_reminders_external_key', table_name='reminders')
    op.drop_index('ix_reminders_remind_at', table_name='reminders')
    op.drop_index('ix_reminders_memory_id', table_name='reminders')
    op.drop_table('reminders')
    
    op.execute("DROP INDEX IF EXISTS idx_memories_embedding_ivfflat")
    op.execute("DROP INDEX IF EXISTS idx_memories_content_trgm")
    op.execute("DROP INDEX IF EXISTS idx_memories_intent")
    op.execute("DROP INDEX IF EXISTS idx_memories_metric")
    op.execute("DROP INDEX IF EXISTS idx_memories_person")
    op.execute("DROP INDEX IF EXISTS idx_memories_aiu_channel")
    op.execute("DROP INDEX IF EXISTS idx_memories_aiu_type")
    op.execute("DROP INDEX IF EXISTS idx_memories_aiu_thread_id")
    op.drop_index('idx_memories_ai_understanding_path', table_name='memories')
    op.drop_index('idx_memories_ai_understanding', table_name='memories')
    op.drop_index('idx_memories_user_created', table_name='memories')
    op.drop_index('ix_memories_occurred_at', table_name='memories')
    op.drop_index('ix_memories_amount', table_name='memories')
    op.drop_index('ix_memories_created_at', table_name='memories')
    op.drop_index('ix_memories_user_id', table_name='memories')
    op.drop_table('memories')
    
    # 删除用户相关表
    op.drop_index('idx_user_channels_channel', table_name='user_channels')
    op.drop_index('idx_user_channels_user_id', table_name='user_channels')
    op.drop_table('user_channels')
    
    op.drop_table('users')
    
    # 删除枚举类型
    op.execute("DROP TYPE IF EXISTS channel_type")
    
    print("✅ 数据库架构已清理")
