-- 初始化数据库脚本
-- 创建pgvector扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 创建UUID扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

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

-- 授予必要的权限
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO faa_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO faa_user;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO faa_user;
