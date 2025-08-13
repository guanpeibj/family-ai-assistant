-- 初始化数据库脚本
-- 创建pgvector扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 创建UUID扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 创建 pgcrypto 扩展以支持 gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 创建 trigram 扩展以支持相似度匹配（可用于无向量时的文本召回）
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 为简化的数据模型创建额外的索引和函数
-- 创建一个用于时间范围查询的函数
CREATE OR REPLACE FUNCTION get_date_range(period TEXT)
RETURNS TABLE(start_date TIMESTAMP, end_date TIMESTAMP) AS $$
BEGIN
    CASE period
        WHEN 'today' THEN
            RETURN QUERY SELECT 
                date_trunc('day', NOW())::TIMESTAMP,
                date_trunc('day', NOW() + INTERVAL '1 day')::TIMESTAMP;
        WHEN 'this_week' THEN
            RETURN QUERY SELECT 
                date_trunc('week', NOW())::TIMESTAMP,
                date_trunc('week', NOW() + INTERVAL '1 week')::TIMESTAMP;
        WHEN 'this_month' THEN
            RETURN QUERY SELECT 
                date_trunc('month', NOW())::TIMESTAMP,
                date_trunc('month', NOW() + INTERVAL '1 month')::TIMESTAMP;
        ELSE
            RETURN QUERY SELECT NOW()::TIMESTAMP, NOW()::TIMESTAMP;
    END CASE;
END;
$$ LANGUAGE plpgsql;

-- 创建一个用于JSONB深度查询的索引示例
-- CREATE INDEX idx_memories_ai_understanding_deep ON memories USING GIN ((ai_understanding->'entities'));

-- 授予必要的权限（与 POSTGRES_USER=faa 一致）
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO faa;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO faa;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO faa;

-- 可选：加速检索的索引（幂等创建）
-- 1) 内容 trigram 索引（用于 ILIKE/相似度检索）
CREATE INDEX IF NOT EXISTS idx_memories_content_trgm ON memories USING gin (content gin_trgm_ops);
-- 2) 向量 ivfflat 索引（需要 pgvector 支持）
-- 注意：如遇到不支持 vector_l2_ops 的环境，可改为 "USING ivfflat (embedding)" 或跳过
DO $$ BEGIN
  BEGIN
    EXECUTE 'CREATE INDEX IF NOT EXISTS idx_memories_embedding_ivfflat ON memories USING ivfflat (embedding vector_l2_ops) WITH (lists=100)';
  EXCEPTION WHEN others THEN
    -- 兜底：忽略索引创建失败（版本不兼容时）
    NULL;
  END;
END $$;

-- 3) JSONB 高频字段表达式索引（健康/意图等维度常用筛选）
DO $$ BEGIN
  BEGIN
    CREATE INDEX IF NOT EXISTS idx_memories_person ON memories ((ai_understanding->>'person'));
  EXCEPTION WHEN others THEN NULL;
  END;
  BEGIN
    CREATE INDEX IF NOT EXISTS idx_memories_metric ON memories ((ai_understanding->>'metric'));
  EXCEPTION WHEN others THEN NULL;
  END;
  BEGIN
    CREATE INDEX IF NOT EXISTS idx_memories_intent ON memories ((ai_understanding->>'intent'));
  EXCEPTION WHEN others THEN NULL;
  END;
END $$;

-- 4) 待发送提醒的部分索引（与模型中的 sent_at 对齐）
DO $$ BEGIN
  BEGIN
    CREATE INDEX IF NOT EXISTS idx_reminders_pending ON reminders (remind_at) WHERE sent_at IS NULL;
  EXCEPTION WHEN others THEN NULL;
  END;
END $$;
