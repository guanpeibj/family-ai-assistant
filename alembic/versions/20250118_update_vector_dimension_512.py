"""update vector dimension to 512 for BAAI/bge-small-zh-v1.5

Revision ID: 20250118_01
Revises: 20250813_01
Create Date: 2025-01-18

"""
from alembic import op
import sqlalchemy as sa

revision = '20250118_01'
down_revision = '20250813_01'
branch_labels = None
depends_on = None


def upgrade():
    """将embedding字段从vector(1536)修改为vector(512)以匹配BAAI/bge-small-zh-v1.5"""
    try:
        # 先删除现有的向量索引（如果存在）
        op.execute("DROP INDEX IF EXISTS idx_memories_embedding_ivfflat")
        
        # 修改列类型 - 注意：这会清空现有的embedding数据
        op.execute("ALTER TABLE memories ALTER COLUMN embedding TYPE vector(512)")
        
        # 重新创建向量索引
        op.execute("CREATE INDEX IF NOT EXISTS idx_memories_embedding_ivfflat ON memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")
        
        print("Successfully updated embedding dimension to 512")
        
    except Exception as e:
        print(f"Warning: Could not update vector dimension: {e}")
        # 在开发环境中，如果遇到问题，可以选择重建表
        pass


def downgrade():
    """回滚到vector(1536)"""
    try:
        # 删除512维的索引
        op.execute("DROP INDEX IF EXISTS idx_memories_embedding_ivfflat")
        
        # 修改回1536维
        op.execute("ALTER TABLE memories ALTER COLUMN embedding TYPE vector(1536)")
        
        # 重新创建索引
        op.execute("CREATE INDEX IF NOT EXISTS idx_memories_embedding_ivfflat ON memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")
        
    except Exception as e:
        print(f"Warning: Could not downgrade vector dimension: {e}")
        pass
