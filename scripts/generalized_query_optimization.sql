-- FAA 通用化精确查询优化方案
-- 基于核心理念：数据结构泛化，但查询性能专业化

-- ===========================================
-- 1. 通用高频字段计算列扩展
-- ===========================================

-- 健康数据高频字段
ALTER TABLE memories ADD COLUMN IF NOT EXISTS person_extracted TEXT 
GENERATED ALWAYS AS (ai_understanding->>'person') STORED;

ALTER TABLE memories ADD COLUMN IF NOT EXISTS metric_extracted TEXT 
GENERATED ALWAYS AS (ai_understanding->>'metric') STORED;

-- 学习数据高频字段  
ALTER TABLE memories ADD COLUMN IF NOT EXISTS subject_extracted TEXT 
GENERATED ALWAYS AS (ai_understanding->>'subject') STORED;

-- 通用维度字段
ALTER TABLE memories ADD COLUMN IF NOT EXISTS source_extracted TEXT 
GENERATED ALWAYS AS (ai_understanding->>'source') STORED;

ALTER TABLE memories ADD COLUMN IF NOT EXISTS tags_extracted JSONB 
GENERATED ALWAYS AS (ai_understanding->'tags') STORED;

-- 数值型字段优化（避免类型转换）
ALTER TABLE memories ADD COLUMN IF NOT EXISTS value_extracted NUMERIC 
GENERATED ALWAYS AS (
    CASE 
        WHEN ai_understanding->>'value' ~ '^[0-9]*\.?[0-9]+$' 
        THEN (ai_understanding->>'value')::NUMERIC 
        ELSE NULL 
    END
) STORED;

-- ===========================================
-- 2. 通用复合索引策略
-- ===========================================

-- 健康数据专用索引组合
DROP INDEX IF EXISTS idx_memories_health_person_metric;
CREATE INDEX CONCURRENTLY idx_memories_health_person_metric 
ON memories (
    user_id,
    type_extracted,
    person_extracted,
    metric_extracted,
    occurred_at DESC,
    value_extracted
) WHERE type_extracted = 'health';

-- 健康趋势分析索引
DROP INDEX IF EXISTS idx_memories_health_timeline;
CREATE INDEX CONCURRENTLY idx_memories_health_timeline 
ON memories (
    user_id,
    person_extracted,
    metric_extracted,
    occurred_at DESC
) WHERE type_extracted = 'health' AND value_extracted IS NOT NULL;

-- 学习数据专用索引组合
DROP INDEX IF EXISTS idx_memories_learning_person_subject;
CREATE INDEX CONCURRENTLY idx_memories_learning_person_subject 
ON memories (
    user_id,
    type_extracted,
    person_extracted,
    subject_extracted,
    occurred_at DESC,
    value_extracted
) WHERE type_extracted IN ('learning', 'exam', 'homework');

-- 通用人员维度索引
DROP INDEX IF EXISTS idx_memories_person_timeline;
CREATE INDEX CONCURRENTLY idx_memories_person_timeline 
ON memories (
    user_id,
    person_extracted,
    type_extracted,
    occurred_at DESC
) WHERE person_extracted IS NOT NULL;

-- 通用类型+时间索引（覆盖所有数据类型）
DROP INDEX IF EXISTS idx_memories_type_timeline;
CREATE INDEX CONCURRENTLY idx_memories_type_timeline 
ON memories (
    user_id,
    type_extracted,
    occurred_at DESC
) WHERE type_extracted IS NOT NULL;

-- ===========================================
-- 3. 高级查询优化函数
-- ===========================================

-- 健康数据统计函数
CREATE OR REPLACE FUNCTION get_health_summary(
    p_user_id UUID,
    p_person TEXT DEFAULT NULL,
    p_metric TEXT DEFAULT NULL,
    p_date_from TIMESTAMP DEFAULT NULL,
    p_date_to TIMESTAMP DEFAULT NULL,
    p_limit INTEGER DEFAULT 100
)
RETURNS TABLE(
    person TEXT,
    metric TEXT,
    latest_value NUMERIC,
    latest_date TIMESTAMP WITH TIME ZONE,
    trend_data JSONB,
    record_count INTEGER
) AS $$
BEGIN
    RETURN QUERY
    WITH health_data AS (
        SELECT 
            person_extracted,
            metric_extracted,
            value_extracted,
            occurred_at,
            ROW_NUMBER() OVER (
                PARTITION BY person_extracted, metric_extracted 
                ORDER BY occurred_at DESC
            ) as rn
        FROM memories 
        WHERE user_id = p_user_id
          AND type_extracted = 'health'
          AND value_extracted IS NOT NULL
          AND (p_person IS NULL OR person_extracted = p_person)
          AND (p_metric IS NULL OR metric_extracted = p_metric)
          AND (p_date_from IS NULL OR occurred_at >= p_date_from)
          AND (p_date_to IS NULL OR occurred_at <= p_date_to)
        ORDER BY occurred_at DESC
        LIMIT p_limit
    ),
    trend_calculation AS (
        SELECT 
            person_extracted,
            metric_extracted,
            MAX(CASE WHEN rn = 1 THEN value_extracted END) as latest_val,
            MAX(CASE WHEN rn = 1 THEN occurred_at END) as latest_dt,
            COUNT(*) as cnt,
            jsonb_agg(
                jsonb_build_object(
                    'date', occurred_at,
                    'value', value_extracted
                ) ORDER BY occurred_at DESC
            ) FILTER (WHERE rn <= 10) as trend
        FROM health_data
        GROUP BY person_extracted, metric_extracted
    )
    SELECT 
        person_extracted,
        metric_extracted,
        latest_val,
        latest_dt,
        trend,
        cnt::INTEGER
    FROM trend_calculation
    ORDER BY person_extracted, metric_extracted;
END;
$$ LANGUAGE plpgsql;

-- 学习进展统计函数
CREATE OR REPLACE FUNCTION get_learning_progress(
    p_user_id UUID,
    p_person TEXT DEFAULT NULL,
    p_subject TEXT DEFAULT NULL,
    p_date_from TIMESTAMP DEFAULT NULL,
    p_date_to TIMESTAMP DEFAULT NULL
)
RETURNS TABLE(
    person TEXT,
    subject TEXT,
    avg_score NUMERIC,
    latest_score NUMERIC,
    improvement NUMERIC,
    record_count INTEGER,
    score_distribution JSONB
) AS $$
BEGIN
    RETURN QUERY
    WITH learning_data AS (
        SELECT 
            person_extracted,
            subject_extracted,
            value_extracted as score,
            occurred_at,
            ROW_NUMBER() OVER (
                PARTITION BY person_extracted, subject_extracted 
                ORDER BY occurred_at DESC
            ) as rn,
            ROW_NUMBER() OVER (
                PARTITION BY person_extracted, subject_extracted 
                ORDER BY occurred_at ASC
            ) as rn_asc
        FROM memories 
        WHERE user_id = p_user_id
          AND type_extracted IN ('learning', 'exam', 'homework')
          AND value_extracted IS NOT NULL
          AND (p_person IS NULL OR person_extracted = p_person)
          AND (p_subject IS NULL OR subject_extracted = p_subject)
          AND (p_date_from IS NULL OR occurred_at >= p_date_from)
          AND (p_date_to IS NULL OR occurred_at <= p_date_to)
    ),
    progress_calc AS (
        SELECT 
            person_extracted,
            subject_extracted,
            ROUND(AVG(score), 2) as avg_score,
            MAX(CASE WHEN rn = 1 THEN score END) as latest_score,
            MAX(CASE WHEN rn_asc = 1 THEN score END) as first_score,
            COUNT(*) as record_count,
            jsonb_build_object(
                'excellent', COUNT(*) FILTER (WHERE score >= 90),
                'good', COUNT(*) FILTER (WHERE score >= 80 AND score < 90),
                'average', COUNT(*) FILTER (WHERE score >= 70 AND score < 80),
                'needs_improvement', COUNT(*) FILTER (WHERE score < 70)
            ) as distribution
        FROM learning_data
        GROUP BY person_extracted, subject_extracted
    )
    SELECT 
        person_extracted,
        subject_extracted,
        avg_score,
        latest_score,
        CASE 
            WHEN first_score IS NOT NULL AND latest_score IS NOT NULL 
            THEN ROUND(latest_score - first_score, 2)
            ELSE NULL 
        END as improvement,
        record_count::INTEGER,
        distribution
    FROM progress_calc
    ORDER BY person_extracted, subject_extracted;
END;
$$ LANGUAGE plpgsql;

-- 通用数据类型统计函数
CREATE OR REPLACE FUNCTION get_data_type_summary(
    p_user_id UUID,
    p_type TEXT,
    p_group_by_field TEXT DEFAULT NULL,
    p_date_from TIMESTAMP DEFAULT NULL,
    p_date_to TIMESTAMP DEFAULT NULL
)
RETURNS TABLE(
    data_type TEXT,
    group_value TEXT,
    record_count INTEGER,
    numeric_summary JSONB,
    latest_records JSONB
) AS $$
BEGIN
    RETURN QUERY
    EXECUTE format(
        'WITH data_summary AS (
            SELECT 
                type_extracted,
                COALESCE(%s, ''total'') as group_val,
                COUNT(*) as cnt,
                jsonb_build_object(
                    ''avg'', ROUND(AVG(value_extracted), 2),
                    ''min'', MIN(value_extracted),
                    ''max'', MAX(value_extracted),
                    ''sum'', SUM(value_extracted)
                ) FILTER (WHERE value_extracted IS NOT NULL) as num_summary,
                jsonb_agg(
                    jsonb_build_object(
                        ''content'', content,
                        ''date'', occurred_at,
                        ''value'', value_extracted
                    ) ORDER BY occurred_at DESC
                ) FILTER (WHERE ROW_NUMBER() OVER (
                    PARTITION BY %s ORDER BY occurred_at DESC
                ) <= 5) as recent
            FROM memories 
            WHERE user_id = $1
              AND type_extracted = $2
              AND ($3 IS NULL OR occurred_at >= $3)
              AND ($4 IS NULL OR occurred_at <= $4)
            GROUP BY type_extracted, %s
        )
        SELECT 
            type_extracted,
            group_val,
            cnt::INTEGER,
            num_summary,
            recent
        FROM data_summary
        ORDER BY type_extracted, group_val',
        CASE WHEN p_group_by_field IS NOT NULL 
             THEN p_group_by_field || '_extracted' 
             ELSE 'NULL' END,
        CASE WHEN p_group_by_field IS NOT NULL 
             THEN p_group_by_field || '_extracted' 
             ELSE 'NULL' END,
        CASE WHEN p_group_by_field IS NOT NULL 
             THEN p_group_by_field || '_extracted' 
             ELSE 'NULL' END
    ) USING p_user_id, p_type, p_date_from, p_date_to;
END;
$$ LANGUAGE plpgsql;

-- ===========================================
-- 4. 智能索引使用分析
-- ===========================================

-- 创建索引使用统计视图
CREATE OR REPLACE VIEW index_usage_analysis AS
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan as scan_count,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched,
    CASE 
        WHEN idx_scan = 0 THEN 'UNUSED'
        WHEN idx_scan < 100 THEN 'LOW_USAGE'
        WHEN idx_scan < 1000 THEN 'MODERATE_USAGE'
        ELSE 'HIGH_USAGE'
    END as usage_level,
    pg_size_pretty(pg_relation_size(indexrelid)) as index_size
FROM pg_stat_user_indexes 
WHERE tablename = 'memories'
ORDER BY idx_scan DESC;

-- ===========================================
-- 5. 查询模式分析函数
-- ===========================================

-- 分析常用查询模式（需要 pg_stat_statements 扩展）
CREATE OR REPLACE FUNCTION analyze_query_patterns()
RETURNS TABLE(
    query_pattern TEXT,
    call_count BIGINT,
    avg_time_ms NUMERIC,
    suggested_optimization TEXT
) AS $$
BEGIN
    -- 检查是否有 pg_stat_statements
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements') THEN
        RAISE NOTICE 'pg_stat_statements extension not installed. Query pattern analysis disabled.';
        RETURN;
    END IF;
    
    RETURN QUERY
    SELECT 
        CASE 
            WHEN query LIKE '%type_extracted%' AND query LIKE '%person_extracted%' 
            THEN 'type_person_query'
            WHEN query LIKE '%person_extracted%' AND query LIKE '%metric_extracted%'
            THEN 'health_person_metric_query'
            WHEN query LIKE '%person_extracted%' AND query LIKE '%subject_extracted%'
            THEN 'learning_person_subject_query'
            WHEN query LIKE '%type_extracted%' AND query LIKE '%occurred_at%'
            THEN 'type_timeline_query'
            ELSE 'other_pattern'
        END as pattern,
        calls,
        ROUND((mean_exec_time)::NUMERIC, 2) as avg_ms,
        CASE 
            WHEN mean_exec_time > 100 THEN 'Consider adding specialized index'
            WHEN calls > 1000 AND mean_exec_time > 10 THEN 'High frequency, optimize'
            ELSE 'Performance acceptable'
        END as suggestion
    FROM pg_stat_statements 
    WHERE query LIKE '%memories%' 
      AND calls > 10
    ORDER BY calls * mean_exec_time DESC
    LIMIT 20;
END;
$$ LANGUAGE plpgsql;

-- ===========================================
-- 6. 动态索引建议系统
-- ===========================================

-- 基于查询模式自动建议索引
CREATE OR REPLACE FUNCTION suggest_dynamic_indexes()
RETURNS TABLE(
    index_name TEXT,
    create_statement TEXT,
    estimated_benefit TEXT,
    data_type_focus TEXT
) AS $$
BEGIN
    -- 分析哪些字段组合查询频繁但缺乏索引
    RETURN QUERY
    WITH field_usage AS (
        SELECT 
            type_extracted,
            person_extracted,
            metric_extracted,
            subject_extracted,
            COUNT(*) as usage_count,
            COUNT(DISTINCT user_id) as user_count
        FROM memories 
        WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY type_extracted, person_extracted, metric_extracted, subject_extracted
        HAVING COUNT(*) > 50
    )
    SELECT 
        CASE 
            WHEN type_extracted = 'health' AND metric_extracted IS NOT NULL
            THEN 'idx_health_' || LOWER(REPLACE(metric_extracted, ' ', '_'))
            WHEN type_extracted IN ('learning', 'exam') AND subject_extracted IS NOT NULL
            THEN 'idx_learning_' || LOWER(REPLACE(subject_extracted, ' ', '_'))
            ELSE 'idx_custom_' || LOWER(REPLACE(type_extracted, ' ', '_'))
        END as idx_name,
        
        CASE 
            WHEN type_extracted = 'health' AND metric_extracted IS NOT NULL
            THEN format('CREATE INDEX CONCURRENTLY %s ON memories (user_id, person_extracted, occurred_at DESC, value_extracted) WHERE type_extracted = ''health'' AND metric_extracted = ''%s'';',
                'idx_health_' || LOWER(REPLACE(metric_extracted, ' ', '_')), metric_extracted)
            WHEN type_extracted IN ('learning', 'exam') AND subject_extracted IS NOT NULL  
            THEN format('CREATE INDEX CONCURRENTLY %s ON memories (user_id, person_extracted, occurred_at DESC, value_extracted) WHERE type_extracted IN (''learning'', ''exam'') AND subject_extracted = ''%s'';',
                'idx_learning_' || LOWER(REPLACE(subject_extracted, ' ', '_')), subject_extracted)
            ELSE format('CREATE INDEX CONCURRENTLY %s ON memories (user_id, type_extracted, occurred_at DESC);',
                'idx_custom_' || LOWER(REPLACE(type_extracted, ' ', '_')))
        END as create_stmt,
        
        format('High usage: %s records from %s users in 30 days', usage_count, user_count) as benefit,
        type_extracted as focus_type
        
    FROM field_usage
    ORDER BY usage_count DESC;
END;
$$ LANGUAGE plpgsql;

-- ===========================================
-- 7. 统计信息和注释
-- ===========================================

ANALYZE memories;

-- 添加索引注释便于维护
COMMENT ON INDEX idx_memories_health_person_metric IS '健康数据专用复合索引：人员+指标+时间+数值';
COMMENT ON INDEX idx_memories_learning_person_subject IS '学习数据专用复合索引：人员+科目+时间+成绩';  
COMMENT ON INDEX idx_memories_person_timeline IS '通用人员维度索引：支持按人员查询所有记录';
COMMENT ON INDEX idx_memories_type_timeline IS '通用类型维度索引：支持按数据类型查询';

COMMENT ON FUNCTION get_health_summary IS '健康数据统计函数：支持趋势分析和最新状态查询';
COMMENT ON FUNCTION get_learning_progress IS '学习进展统计函数：支持成绩分析和进步追踪';
COMMENT ON FUNCTION get_data_type_summary IS '通用数据类型统计函数：支持任意类型的聚合分析';
COMMENT ON FUNCTION suggest_dynamic_indexes IS '动态索引建议系统：基于使用模式自动推荐索引优化';
