"""rename reminders.sent to sent_at, add FK and indexes

Revision ID: 20250813_01
Revises: None
Create Date: 2025-08-13

"""
from alembic import op
import sqlalchemy as sa

revision = '20250813_01'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # 1) 列重命名（兼容已有表）
    with op.batch_alter_table('reminders') as batch_op:
        # 如果不存在 sent 列，跳过重命名
        try:
            batch_op.alter_column('sent', new_column_name='sent_at')
        except Exception:
            pass
        # 添加外键（若尚未存在）
        try:
            batch_op.create_foreign_key('fk_reminders_memory', 'memories', ['memory_id'], ['id'])
        except Exception:
            pass

    # 2) 创建待发送部分索引（对齐 sent_at）
    try:
        op.execute("CREATE INDEX IF NOT EXISTS idx_reminders_pending ON reminders (remind_at) WHERE sent_at IS NULL")
    except Exception:
        pass

    # 3) JSONB 常用表达式索引（幂等）
    try:
        op.execute("CREATE INDEX IF NOT EXISTS idx_memories_person ON memories ((ai_understanding->>'person'))")
    except Exception:
        pass
    try:
        op.execute("CREATE INDEX IF NOT EXISTS idx_memories_metric ON memories ((ai_understanding->>'metric'))")
    except Exception:
        pass
    try:
        op.execute("CREATE INDEX IF NOT EXISTS idx_memories_intent ON memories ((ai_understanding->>'intent'))")
    except Exception:
        pass


def downgrade():
    # 仅做 best-effort 回滚
    try:
        op.execute("DROP INDEX IF EXISTS idx_reminders_pending")
    except Exception:
        pass
    try:
        op.execute("DROP INDEX IF EXISTS idx_memories_person")
    except Exception:
        pass
    try:
        op.execute("DROP INDEX IF EXISTS idx_memories_metric")
    except Exception:
        pass
    try:
        op.execute("DROP INDEX IF EXISTS idx_memories_intent")
    except Exception:
        pass
    with op.batch_alter_table('reminders') as batch_op:
        try:
            batch_op.drop_constraint('fk_reminders_memory', type_='foreignkey')
        except Exception:
            pass
        try:
            batch_op.alter_column('sent_at', new_column_name='sent')
        except Exception:
            pass


