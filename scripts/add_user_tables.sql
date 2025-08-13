-- 添加用户相关表的迁移脚本
-- 用于支持多渠道接入（Threema、Email、WeChat等）

-- 创建枚举类型（如果不存在）
DO $$ BEGIN
    CREATE TYPE channel_type AS ENUM ('threema', 'email', 'wechat');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 创建用户表
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
    -- 未来可以添加更多用户属性，但现在保持极简
);

-- 创建用户渠道绑定表
CREATE TABLE IF NOT EXISTS user_channels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel channel_type NOT NULL,
    channel_user_id VARCHAR(255) NOT NULL,    -- Threema ID、邮箱、OpenID等
    channel_data JSONB,                       -- 渠道特定数据（如昵称等）
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    
    -- 确保渠道+用户ID唯一
    CONSTRAINT uq_channel_user UNIQUE (channel, channel_user_id)
);

-- 创建索引
CREATE INDEX idx_user_channels_user_id ON user_channels(user_id);
CREATE INDEX idx_user_channels_channel ON user_channels(channel);

-- 修改 memories 表（如果需要）
DO $$
BEGIN
    -- 检查 user_id 列的类型
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'memories' 
        AND column_name = 'user_id' 
        AND data_type = 'character varying'
    ) THEN
        -- 创建临时列
        ALTER TABLE memories ADD COLUMN user_id_new UUID;
        
        -- 为现有数据创建默认用户
        INSERT INTO users (id) VALUES ('00000000-0000-0000-0000-000000000000')
        ON CONFLICT DO NOTHING;
        
        -- 更新所有记录使用默认用户
        UPDATE memories SET user_id_new = '00000000-0000-0000-0000-000000000000';
        
        -- 删除旧列，重命名新列
        ALTER TABLE memories DROP COLUMN user_id;
        ALTER TABLE memories RENAME COLUMN user_id_new TO user_id;
        
        -- 添加外键约束
        ALTER TABLE memories ADD CONSTRAINT fk_memories_user 
            FOREIGN KEY (user_id) REFERENCES users(id);
            
        -- 创建索引
        CREATE INDEX idx_memories_user_id ON memories(user_id);
    END IF;
END $$;

-- 授予权限（与 POSTGRES_USER=faa 一致）
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO faa;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO faa;