#!/usr/bin/env python3
"""
通用 MCP 服务端 - 完全 AI 驱动，不包含任何业务逻辑
"""
import asyncio
import json
import os
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
import uuid
import os
import io

# 延迟导入 MCP 相关模块，避免在 HTTP 模式下因版本差异报错
import asyncpg

# 环境变量
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://faa:faa@localhost:5432/family_assistant')


class GenericMCPServer:
    def __init__(self):
        # HTTP 模式不需要 MCP Server 对象，避免在初始化时调用新版 mcp 不兼容的 API
        self.server = None  # 延迟创建，仅在 stdio 模式下使用
        self.pool = None
        # 用于将任意字符串稳定映射为 UUID（当传入的 user_id 非 UUID 时）
        self._ns = uuid.NAMESPACE_URL
    
    async def initialize(self):
        """初始化数据库连接池"""
        self.pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
        # 确保必要扩展与索引存在（幂等）
        try:
            async with self.pool.acquire() as conn:
                await self._ensure_db_extensions(conn)
                await self._ensure_db_indexes(conn)
        except Exception:
            # 初始化阶段不因索引/扩展失败而阻塞服务启动（日志交由上层）
            pass
    
    async def close(self):
        """关闭连接池"""
        if self.pool:
            await self.pool.close()
    
    async def _store(self, content: str, ai_data: Dict[str, Any], user_id: str, embedding: Optional[Any] = None) -> Dict[str, Any]:
        """存储任何 AI 认为需要记住的信息"""
        try:
            async with self.pool.acquire() as conn:
                # 规范化用户ID并确保用户存在
                uid = self._normalize_user_id(user_id)
                await self._ensure_user(conn, uid)
                # 嵌入向量由 AI 引擎统一生成并传入；支持 list[float] 或 "[x,y,...]" 字符串。
                if embedding is None and isinstance(ai_data, dict):
                    # 兼容：若调用方误放到 ai_data 中
                    embedding = ai_data.get('_embedding') or ai_data.get('embedding')
                # 确保 JSON 可序列化：若传入为 numpy 类型，转 Python float
                try:
                    if embedding is not None and not isinstance(embedding, str):
                        embedding = [float(x) for x in embedding]
                except Exception:
                    pass
                embedding_text = self._normalize_embedding(embedding)
                
                # 提取 AI 识别的金额和时间（如果有）
                amount = ai_data.get('amount')
                occurred_at = ai_data.get('occurred_at')
                if occurred_at and isinstance(occurred_at, str):
                    occurred_at = datetime.fromisoformat(occurred_at)
                
                # 插入记忆
                memory_id = await conn.fetchval(
                    """
                    INSERT INTO memories (
                        id, user_id, content, ai_understanding, 
                        embedding, amount, occurred_at
                    ) VALUES ($1, $2, $3, $4, $5::vector, $6, $7)
                    RETURNING id
                    """,
                    uuid.uuid4(),
                    uid,
                    content,
                    json.dumps(ai_data),
                    embedding_text,
                    amount,
                    occurred_at
                )
                
                return {
                    "success": True,
                    "id": str(memory_id),
                    "message": "信息已存储"
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _search(self, user_id: str, query: Optional[str] = None, filters: Optional[Dict[str, Any]] = None, query_embedding: Optional[Any] = None) -> List[Dict[str, Any]]:
        """搜索相关记忆，支持语义和精确查询
        
        参数:
        - user_id: 必需，用户标识
        - query: 可选，查询文本（用于trigram匹配）
        - filters: 可选，精确过滤条件
        - query_embedding: 可选，查询向量
        """
        try:
            async with self.pool.acquire() as conn:
                results = []
                uid = self._normalize_user_id(user_id)
                await self._ensure_user(conn, uid)
                # 共享线程模式：当指定 shared_thread=True 且提供 thread_id 时，放宽 user_id 约束，允许跨用户按线程聚合
                shared_thread_mode = bool(filters and filters.get('shared_thread') and filters.get('thread_id'))
                # 对共享线程施加更严格的 limit 上限，避免全表扫
                shared_thread_limit_cap = 30
                
                # 如果提供查询向量，进行语义搜索
                if query_embedding is not None:
                    used_vector = True
                    used_trigram = False
                    query_embedding_text = self._normalize_embedding(query_embedding)
                    
                    # 构建查询
                    if shared_thread_mode:
                        sql = """
                        SELECT id, content, ai_understanding, amount, occurred_at, created_at, user_id,
                               1 - (embedding <=> $1::vector) as similarity
                        FROM memories
                        WHERE embedding IS NOT NULL
                          AND COALESCE(ai_understanding->>'deleted','false') <> 'true'
                        """
                        params = [query_embedding_text]
                    else:
                        sql = """
                        SELECT id, content, ai_understanding, amount, occurred_at, created_at, user_id,
                               1 - (embedding <=> $1::vector) as similarity
                        FROM memories
                        WHERE user_id = $2 AND embedding IS NOT NULL
                          AND COALESCE(ai_understanding->>'deleted','false') <> 'true'
                        """
                        params = [query_embedding_text, uid]
                    
                    # 添加过滤条件（优化版：优先使用计算列）
                    if filters:
                        # thread_id/type 过滤（优化：优先使用计算列）
                        if 'thread_id' in filters:
                            sql += f" AND thread_id_extracted = ${len(params) + 1}"
                            params.append(filters['thread_id'])
                        if 'type' in filters:
                            sql += f" AND type_extracted = ${len(params) + 1}"
                            params.append(filters['type'])
                        if 'channel' in filters:
                            sql += f" AND (ai_understanding->>'channel') = ${len(params) + 1}"
                            params.append(filters['channel'])
                        if 'date_from' in filters:
                            sql += f" AND occurred_at >= ${len(params) + 1}"
                            params.append(datetime.fromisoformat(filters['date_from']))
                        if 'date_to' in filters:
                            sql += f" AND occurred_at <= ${len(params) + 1}"
                            params.append(datetime.fromisoformat(filters['date_to']))
                        if 'min_amount' in filters:
                            sql += f" AND amount >= ${len(params) + 1}"
                            params.append(filters['min_amount'])
                        if 'max_amount' in filters:
                            sql += f" AND amount <= ${len(params) + 1}"
                            params.append(filters['max_amount'])
                        # JSONB 包含过滤（优化：对常用字段使用计算列）
                        je = filters.get('jsonb_equals') if isinstance(filters.get('jsonb_equals'), dict) else None
                        if je:
                            # 分别处理每个字段，优先使用计算列
                            computed_col_filters = {}
                            jsonb_filters = {}
                            
                            for k, v in je.items():
                                if k in ['type', 'thread_id', 'category', 'person', 'metric', 'subject', 'source']:
                                    computed_col_filters[k] = v
                                else:
                                    jsonb_filters[k] = v
                            
                            # 计算列过滤（更高效）- 支持所有高频字段
                            for k, v in computed_col_filters.items():
                                if k == 'type':
                                    sql += f" AND type_extracted = ${len(params) + 1}"
                                elif k == 'thread_id':
                                    sql += f" AND thread_id_extracted = ${len(params) + 1}"
                                elif k == 'category':
                                    sql += f" AND category_extracted = ${len(params) + 1}"
                                elif k == 'person':
                                    sql += f" AND person_extracted = ${len(params) + 1}"
                                elif k == 'metric':
                                    sql += f" AND metric_extracted = ${len(params) + 1}"
                                elif k == 'subject':
                                    sql += f" AND subject_extracted = ${len(params) + 1}"
                                elif k == 'source':
                                    sql += f" AND source_extracted = ${len(params) + 1}"
                                params.append(str(v))
                            
                            # 剩余JSONB过滤
                            if jsonb_filters:
                                sql += f" AND ai_understanding @> ${len(params) + 1}::jsonb"
                                params.append(json.dumps(jsonb_filters))
                    
                    limit_value = 20
                    if filters and isinstance(filters.get('limit'), int) and filters['limit'] > 0:
                        limit_value = min(filters['limit'], 100)
                    if shared_thread_mode:
                        limit_value = min(limit_value, shared_thread_limit_cap)
                    sql += " ORDER BY similarity DESC LIMIT $" + str(len(params) + 1)
                    params.append(limit_value)
                    
                    rows = await conn.fetch(sql, *params)
                else:
                    # 无查询向量：过滤 + 可选 trigram 相似匹配（需 pg_trgm）
                    used_vector = False
                    if shared_thread_mode:
                        base_sql = """
                        SELECT id, content, ai_understanding, amount, occurred_at, created_at, user_id
                        FROM memories
                        WHERE TRUE
                        """
                        params = []
                    else:
                        base_sql = """
                        SELECT id, content, ai_understanding, amount, occurred_at, created_at, user_id
                        FROM memories
                        WHERE user_id = $1
                        """
                        params = [uid]

                    # 软删除过滤（约定 ai_understanding.deleted=true 为软删除）
                    sql = base_sql + " AND COALESCE(ai_understanding->>'deleted','false') <> 'true'"

                    trigram_param_idx = None
                    if query:
                        used_trigram = True
                        trigram_param_idx = len(params) + 1
                        sql += f" AND content % ${trigram_param_idx}"
                        params.append(query)
                    
                    if filters:
                        # 优先使用计算列过滤（更高效）
                        if 'thread_id' in filters:
                            sql += f" AND thread_id_extracted = ${len(params) + 1}"
                            params.append(filters['thread_id'])
                        if 'type' in filters:
                            sql += f" AND type_extracted = ${len(params) + 1}"
                            params.append(filters['type'])
                        if 'channel' in filters:
                            sql += f" AND (ai_understanding->>'channel') = ${len(params) + 1}"
                            params.append(filters['channel'])
                        if 'date_from' in filters:
                            sql += f" AND occurred_at >= ${len(params) + 1}"
                            params.append(datetime.fromisoformat(filters['date_from']))
                        if 'date_to' in filters:
                            sql += f" AND occurred_at <= ${len(params) + 1}"
                            params.append(datetime.fromisoformat(filters['date_to']))
                        if 'min_amount' in filters:
                            sql += f" AND amount >= ${len(params) + 1}"
                            params.append(filters['min_amount'])
                        if 'max_amount' in filters:
                            sql += f" AND amount <= ${len(params) + 1}"
                            params.append(filters['max_amount'])
                        # JSONB 包含过滤（优化版）
                        je = filters.get('jsonb_equals') if isinstance(filters.get('jsonb_equals'), dict) else None
                        if je:
                            computed_col_filters = {}
                            jsonb_filters = {}
                            
                            for k, v in je.items():
                                if k in ['type', 'thread_id', 'category', 'person', 'metric', 'subject', 'source']:
                                    computed_col_filters[k] = v
                                else:
                                    jsonb_filters[k] = v
                            
                            # 计算列过滤
                            for k, v in computed_col_filters.items():
                                if k == 'type':
                                    sql += f" AND type_extracted = ${len(params) + 1}"
                                elif k == 'thread_id':
                                    sql += f" AND thread_id_extracted = ${len(params) + 1}"
                                elif k == 'category':
                                    sql += f" AND category_extracted = ${len(params) + 1}"
                                elif k == 'person':
                                    sql += f" AND person_extracted = ${len(params) + 1}"
                                elif k == 'metric':
                                    sql += f" AND metric_extracted = ${len(params) + 1}"
                                elif k == 'subject':
                                    sql += f" AND subject_extracted = ${len(params) + 1}"
                                elif k == 'source':
                                    sql += f" AND source_extracted = ${len(params) + 1}"
                                params.append(str(v))
                            
                            # JSONB过滤
                            if jsonb_filters:
                                sql += f" AND ai_understanding @> ${len(params) + 1}::jsonb"
                                params.append(json.dumps(jsonb_filters))
                        if 'limit' in filters and isinstance(filters['limit'], int):
                            limit_value = min(max(filters['limit'], 1), 200)
                        else:
                            limit_value = 20
                    else:
                        limit_value = 20

                    if shared_thread_mode:
                        limit_value = min(limit_value, shared_thread_limit_cap)
                    if trigram_param_idx is not None:
                        sql += f" ORDER BY similarity(content, ${trigram_param_idx}) DESC NULLS LAST, occurred_at DESC NULLS LAST, created_at DESC LIMIT {limit_value}"
                    else:
                        used_trigram = False
                        sql += f" ORDER BY occurred_at DESC NULLS LAST, created_at DESC LIMIT {limit_value}"

                    rows = await conn.fetch(sql, *params)
                
                # 格式化结果
                for row in rows:
                    result = {
                        "id": str(row['id']),
                        "content": row['content'],
                        "ai_understanding": json.loads(row['ai_understanding']),
                        "amount": float(row['amount']) if row['amount'] else None,
                        "occurred_at": row['occurred_at'].isoformat() if row['occurred_at'] else None,
                        "created_at": row['created_at'].isoformat() if row['created_at'] else None,
                        "user_id": str(row['user_id'])
                    }
                    if 'similarity' in row:
                        result['similarity'] = float(row['similarity'])
                    results.append(result)
                
                # 附加 meta 信息（作为列表末尾的 _meta 项，兼容旧用法）
                try:
                    applied_filters = list((filters or {}).keys())
                except Exception:
                    applied_filters = []
                results.append({
                    "_meta": {
                        "used_vector": bool('similarity' in rows[0] if rows else False) if query_embedding is not None else used_vector,
                        "used_trigram": used_trigram if query_embedding is None else False,
                        "limit": limit_value if 'limit_value' in locals() else None,
                        "applied_filters": applied_filters,
                        "shared_thread_mode": shared_thread_mode,
                        "returned": len(results)
                    }
                })

                return results
                
        except Exception as e:
            return [{
                "error": str(e)
            }]

    async def _ensure_db_extensions(self, conn) -> None:
        """确保所需扩展存在。"""
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except Exception:
            pass
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        except Exception:
            pass

    async def _ensure_db_indexes(self, conn) -> None:
        """确保关键索引存在（幂等）。"""
        stmts = [
            # 向量检索索引（ivfflat，cosine）
            "CREATE INDEX IF NOT EXISTS idx_memories_embedding_ivfflat ON memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)",
            # trigram 文本相似索引
            "CREATE INDEX IF NOT EXISTS idx_memories_content_trgm ON memories USING gin (content gin_trgm_ops)",
            # JSONB 包含查询优化（path ops）
            "CREATE INDEX IF NOT EXISTS idx_memories_ai_understanding_path ON memories USING gin (ai_understanding jsonb_path_ops)",
            # 表达式索引：thread_id/type/channel
            "CREATE INDEX IF NOT EXISTS idx_memories_aiu_thread_id ON memories ((ai_understanding->>'thread_id'))",
            "CREATE INDEX IF NOT EXISTS idx_memories_aiu_type ON memories ((ai_understanding->>'type'))",
            "CREATE INDEX IF NOT EXISTS idx_memories_aiu_channel ON memories ((ai_understanding->>'channel'))",
            # 组合索引：thread + time，加速共享线程回放
            "CREATE INDEX IF NOT EXISTS idx_memories_thread_time ON memories ((ai_understanding->>'thread_id'), occurred_at DESC)",
            # 组合索引：用户 + 时间
            "CREATE INDEX IF NOT EXISTS idx_memories_user_occ ON memories (user_id, occurred_at DESC)",
            # 软去重：存在 external_id 时的唯一约束
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_user_external_id ON memories (user_id, (ai_understanding->>'external_id')) WHERE ai_understanding ? 'external_id'"
        ]
        for s in stmts:
            try:
                await conn.execute(s)
            except Exception:
                # 单条失败不影响整体
                pass
    
    async def _aggregate(self, user_id: Union[str, List[str]], operation: str, field: Optional[str], filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        对数据进行聚合统计
        
        重要：财务统计时需要区分数据类型，避免混淆预算和支出：
        - 支出统计: filters={"jsonb_equals": {"type": "expense"}}
        - 收入统计: filters={"jsonb_equals": {"type": "income"}} 
        - 预算查询: filters={"jsonb_equals": {"type": "budget"}}
        - 分类统计: filters={"group_by_ai_field": "category"}
        - 时间范围: filters={"date_from": "2025-08-01", "date_to": "2025-08-31"}
        
        常见错误：
        - 统计支出时忘记排除预算，导致金额虚高
        - 分类统计时没有使用 group_by_ai_field，无法获取分组数据
        """
        try:
            async with self.pool.acquire() as conn:
                if isinstance(user_id, (list, tuple, set)):
                    raw_ids = [str(u) for u in user_id]
                else:
                    raw_ids = [str(user_id)]

                normalized_ids: List[uuid.UUID] = []
                for raw in raw_ids:
                    try:
                        norm = self._normalize_user_id(raw)
                        normalized_ids.append(norm)
                        await self._ensure_user(conn, norm)
                    except Exception:
                        return {"error": f"invalid_user_id: {raw}"}

                params: List[Any] = []
                if len(normalized_ids) == 1:
                    user_condition = f"user_id = ${len(params) + 1}"
                    params.append(normalized_ids[0])
                else:
                    user_condition = f"user_id = ANY(${len(params) + 1}::uuid[])"
                    # asyncpg 允许直接传入 list[UUID]
                    params.append(normalized_ids)
                # 构建聚合查询
                if operation not in ['sum', 'count', 'avg', 'min', 'max']:
                    return {"error": f"不支持的操作: {operation}"}

                if operation != 'count' and not field:
                    return {"error": "field is required for non-count aggregation"}
                
                # 分组支持
                period = None
                ai_group_field = None
                if filters:
                    gb = filters.get('group_by')
                    if gb in ['day', 'week', 'month']:
                        period = gb
                    agf = filters.get('group_by_ai_field')
                    if isinstance(agf, str) and agf:
                        ai_group_field = agf
                group_exprs = []
                group_labels = []
                if period:
                    group_exprs.append(f"date_trunc('{period}', occurred_at)")
                    group_labels.append("period")
                if ai_group_field:
                    group_exprs.append(f"(ai_understanding->>'{ai_group_field}')")
                    group_labels.append("ai_group")
                if group_exprs:
                    select_cols = []
                    for expr, label in zip(group_exprs, group_labels):
                        select_cols.append(f"{expr} AS {label}")
                    if operation == 'count':
                        select_cols.append("COUNT(*) AS result")
                    else:
                        select_cols.append(f"{operation.upper()}({field}) AS result")
                    sql = f"SELECT {', '.join(select_cols)} FROM memories WHERE {user_condition}"
                else:
                    if operation == 'count':
                        sql = f"SELECT COUNT(*) as result FROM memories WHERE {user_condition}"
                    else:
                        sql = f"SELECT {operation.upper()}({field}) as result FROM memories WHERE {user_condition}"
                
                # 添加过滤条件（优化版：优先使用计算列）
                if filters:
                    # type过滤（优化：优先使用计算列索引）
                    if 'type' in filters:
                        sql += f" AND type_extracted = ${len(params) + 1}"
                        params.append(filters['type'])
                    # channel过滤
                    if 'channel' in filters:
                        sql += f" AND (ai_understanding->>'channel') = ${len(params) + 1}"
                        params.append(filters['channel'])
                    # 时间过滤（保持原样，有专用索引）
                    if 'date_from' in filters:
                        sql += f" AND occurred_at >= ${len(params) + 1}"
                        params.append(datetime.fromisoformat(filters['date_from']))
                    if 'date_to' in filters:
                        sql += f" AND occurred_at <= ${len(params) + 1}"
                        params.append(datetime.fromisoformat(filters['date_to']))
                    # 通用 JSONB 等值过滤（保持向后兼容）
                    je = filters.get('jsonb_equals') if isinstance(filters.get('jsonb_equals'), dict) else None
                    if je:
                        for k, v in je.items():
                            # 对高频字段使用计算列优化
                            if k == 'type':
                                sql += f" AND type_extracted = ${len(params) + 1}"
                            elif k == 'category':
                                sql += f" AND category_extracted = ${len(params) + 1}"
                            elif k == 'thread_id':
                                sql += f" AND thread_id_extracted = ${len(params) + 1}"
                            else:
                                # 其他字段使用JSONB查询
                                sql += f" AND (ai_understanding->>'{k}') = ${len(params) + 1}"
                            params.append(str(v))
                
                # 对于非 count 操作，确保字段不为空
                if operation != 'count':
                    sql += f" AND {field} IS NOT NULL"
                if group_exprs:
                    sql += " GROUP BY " + ", ".join(group_exprs)
                    sql += " ORDER BY " + ", ".join(group_labels)
                    rows = await conn.fetch(sql, *params)
                    groups = []
                    for row in rows:
                        group_obj = {}
                        for label in group_labels:
                            val = row[label]
                            if hasattr(val, 'isoformat'):
                                group_obj[label] = val.isoformat()
                            else:
                                group_obj[label] = val
                        groups.append({
                            "group": group_obj,
                            "result": float(row['result']) if row['result'] is not None else 0,
                        })
                    return {
                        "operation": operation,
                        "field": field,
                        "groups": groups,
                        "filters": filters,
                        "_meta": {
                            "group_by": period,
                            "group_by_ai_field": ai_group_field,
                            "applied_filters": list((filters or {}).keys())
                        }
                    }
                else:
                    result = await conn.fetchval(sql, *params)
                    return {
                        "operation": operation,
                        "field": field,
                        "result": float(result) if result else 0,
                        "filters": filters,
                        "_meta": {
                            "applied_filters": list((filters or {}).keys())
                        }
                    }
                
        except Exception as e:
            return {
                "error": str(e)
            }

    async def _render_chart(self, type: str, title: str, x: List[Any], series: List[Dict[str, Any]], style: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        渲染图表为 PNG 文件（M2）：使用 matplotlib，无GUI后端。
        返回 {success, path}。
        """
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import numpy as np
            # 中文字体支持（尝试设为 SimHei，不存在则忽略）
            try:
                plt.rcParams['font.sans-serif'] = ['SimHei']
                plt.rcParams['axes.unicode_minus'] = False
            except Exception:
                pass
            width = (style or {}).get('width', 1000)
            height = (style or {}).get('height', 600)
            dpi = 100
            fig_w = max(4, width / dpi)
            fig_h = max(3, height / dpi)
            fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
            ax.set_title(title or '')
            if type in ('line', 'bar'):
                indices = np.arange(len(x))
                if type == 'line':
                    for s in series:
                        ax.plot(x, s.get('y', []), label=s.get('name', 'series'))
                else:
                    # 简单并列柱状
                    total = max(1, len(series))
                    bar_width = 0.8 / total
                    for i, s in enumerate(series):
                        ax.bar(indices + i * bar_width, s.get('y', []), width=bar_width, label=s.get('name', 'series'))
                    ax.set_xticks(indices + (bar_width * (max(1, len(series)) - 1) / 2))
                    # 自动旋转，避免拥挤
                    rotation = 0 if len(x) <= 8 else 30 if len(x) <= 16 else 60
                    ax.set_xticklabels(x, rotation=rotation)
            elif type == 'pie':
                # 取第一组数据画饼
                s0 = series[0] if series else {"name": "series", "y": []}
                ax.pie(s0.get('y', []), labels=x, autopct='%1.1f%%', startangle=140)
                ax.axis('equal')
            else:
                ax.text(0.5, 0.5, f"Unsupported chart type: {type}", ha='center')
            ax.legend(loc='best')
            # 保存到媒体目录
            media_root = os.getenv('MEDIA_ROOT', '/data/media')
            now = datetime.now()
            base_dir = os.path.join(media_root, now.strftime('%Y'), now.strftime('%m'))
            os.makedirs(base_dir, exist_ok=True)
            fname = f"chart_{uuid.uuid4()}.png"
            fpath = os.path.join(base_dir, fname)
            plt.tight_layout()
            fig.savefig(fpath)
            plt.close(fig)
            return {"success": True, "path": fpath}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _schedule_reminder(self, memory_id: str, remind_at: str) -> Dict[str, Any]:
        """为某个记忆设置提醒"""
        try:
            async with self.pool.acquire() as conn:
                reminder_id = await conn.fetchval(
                    """
                    INSERT INTO reminders (id, memory_id, remind_at)
                    VALUES ($1, $2, $3)
                    RETURNING id
                    """,
                    uuid.uuid4(),
                    uuid.UUID(memory_id),
                    datetime.fromisoformat(remind_at)
                )
                
                return {
                    "success": True,
                    "reminder_id": str(reminder_id),
                    "remind_at": remind_at
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _get_pending_reminders(self, user_id: str) -> List[Dict[str, Any]]:
        """获取待发送的提醒"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT r.id as reminder_id, r.remind_at, 
                           m.content, m.ai_understanding
                    FROM reminders r
                    JOIN memories m ON r.memory_id = m.id
                    WHERE m.user_id = $1 
                      AND r.sent_at IS NULL
                      AND r.remind_at <= NOW()
                    ORDER BY r.remind_at
                    """,
                    uuid.UUID(user_id)
                )
                
                return [
                    {
                        "reminder_id": str(row['reminder_id']),
                        "remind_at": row['remind_at'].isoformat(),
                        "content": row['content'],
                        "ai_understanding": json.loads(row['ai_understanding'])
                    }
                    for row in rows
                ]
                
        except Exception as e:
            return [{
                "error": str(e)
            }]
    
    async def _mark_reminder_sent(self, reminder_id: str) -> Dict[str, Any]:
        """标记提醒为已发送"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE reminders 
                    SET sent_at = NOW()
                    WHERE id = $1
                    """,
                    uuid.UUID(reminder_id)
                )
                
                return {
                    "success": True,
                    "reminder_id": reminder_id
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def _batch_store(self, memories: List[Dict[str, Any]]) -> Dict[str, Any]:
        """批量存储记忆。每项: {content, ai_data, user_id, embedding?}"""
        try:
            inserted: List[str] = []
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    for item in memories:
                        content = item.get('content', '')
                        ai_data = item.get('ai_data') or {}
                        user_id = item.get('user_id')
                        uid = self._normalize_user_id(user_id)
                        await self._ensure_user(conn, uid)
                        passed_embedding = item.get('embedding')
                        embedding_text = self._normalize_embedding(passed_embedding)
                        amount = ai_data.get('amount')
                        occurred_at = ai_data.get('occurred_at')
                        if occurred_at and isinstance(occurred_at, str):
                            occurred_at = datetime.fromisoformat(occurred_at)
                        memory_id = await conn.fetchval(
                            """
                            INSERT INTO memories (
                                id, user_id, content, ai_understanding,
                                embedding, amount, occurred_at
                            ) VALUES ($1, $2, $3, $4, $5::vector, $6, $7)
                            RETURNING id
                            """,
                            uuid.uuid4(), uid, content, json.dumps(ai_data), embedding_text, amount, occurred_at
                        )
                        inserted.append(str(memory_id))
            return {"success": True, "ids": inserted, "count": len(inserted)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _batch_search(self, queries: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """批量搜索。每项: {query, user_id, filters?, query_embedding?}"""
        results: List[List[Dict[str, Any]]] = []
        for q in queries:
            r = await self._search(
                q.get('query', ''),
                q.get('user_id', ''),
                q.get('filters'),
                q.get('query_embedding'),
            )
            results.append(r)
        return results

    async def _update_memory_fields(self, memory_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """通用字段级更新：支持 content、amount、occurred_at、embedding、ai_understanding(浅合并)。"""
        try:
            async with self.pool.acquire() as conn:
                sets = []
                params: List[Any] = []
                # content
                if 'content' in fields and fields['content'] is not None:
                    sets.append(f"content = ${len(params)+1}")
                    params.append(fields['content'])
                # amount
                if 'amount' in fields and fields['amount'] is not None:
                    sets.append(f"amount = ${len(params)+1}")
                    params.append(fields['amount'])
                # occurred_at
                if 'occurred_at' in fields and fields['occurred_at'] is not None:
                    sets.append(f"occurred_at = ${len(params)+1}")
                    val = fields['occurred_at']
                    if isinstance(val, str):
                        val = datetime.fromisoformat(val)
                    params.append(val)
                # embedding
                if 'embedding' in fields:
                    emb_text = self._normalize_embedding(fields.get('embedding'))
                    sets.append(f"embedding = ${len(params)+1}::vector")
                    params.append(emb_text)
                # ai_understanding 合并
                if 'ai_understanding' in fields and isinstance(fields['ai_understanding'], dict):
                    sets.append("ai_understanding = COALESCE(ai_understanding, '{}'::jsonb) || $" + str(len(params)+1) + "::jsonb")
                    params.append(json.dumps(fields['ai_understanding']))
                if not sets:
                    return {"success": False, "error": "no_fields"}
                params.append(uuid.UUID(memory_id))
                sql = f"UPDATE memories SET {', '.join(sets)} WHERE id = ${len(params)}"
                await conn.execute(sql, *params)
                return {"success": True, "id": memory_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _soft_delete(self, memory_id: str) -> Dict[str, Any]:
        """软删除：设置 ai_understanding.deleted = true"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE memories
                    SET ai_understanding = COALESCE(ai_understanding, '{}'::jsonb) || '{"deleted": true}'::jsonb
                    WHERE id = $1
                    """,
                    uuid.UUID(memory_id)
                )
                return {"success": True, "id": memory_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _reembed_memories(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """返回需要重嵌的记忆列表，用于引擎端生成向量后回填。支持 filters: date_from/date_to/jsonb_equals/limit/embedding_missing(bool)。"""
        try:
            async with self.pool.acquire() as conn:
                sql = "SELECT id, content FROM memories WHERE COALESCE(ai_understanding->>'deleted','false') <> 'true'"
                params: List[Any] = []
                if filters:
                    if filters.get('embedding_missing'):
                        sql += " AND embedding IS NULL"
                    if 'date_from' in filters:
                        sql += f" AND occurred_at >= ${len(params)+1}"
                        params.append(datetime.fromisoformat(filters['date_from']))
                    if 'date_to' in filters:
                        sql += f" AND occurred_at <= ${len(params)+1}"
                        params.append(datetime.fromisoformat(filters['date_to']))
                    je = filters.get('jsonb_equals') if isinstance(filters.get('jsonb_equals'), dict) else None
                    if je:
                        for k, v in je.items():
                            sql += f" AND (ai_understanding->>'{k}') = ${len(params) + 1}"
                            params.append(str(v))
                limit_value = 100
                if filters and isinstance(filters.get('limit'), int):
                    limit_value = min(max(filters['limit'], 1), 1000)
                sql += f" ORDER BY occurred_at DESC NULLS LAST, created_at DESC LIMIT {limit_value}"
                rows = await conn.fetch(sql, *params)
                return [{"id": str(r['id']), "content": r['content']} for r in rows]
        except Exception as e:
            return [{"error": str(e)}]

    async def _get_expense_summary_optimized(self, user_id: Union[str, List[str]], date_from: Optional[str] = None, date_to: Optional[str] = None) -> Dict[str, Any]:
        """
        高效的财务统计函数，支持家庭统计（多用户）和单用户统计
        """
        try:
            async with self.pool.acquire() as conn:
                # 智能处理用户ID：支持单用户和家庭（多用户）统计
                if isinstance(user_id, str):
                    user_ids = [self._normalize_user_id(user_id)]
                else:
                    user_ids = [self._normalize_user_id(uid) for uid in user_id]
                
                # 确保所有用户都存在
                for uid in user_ids:
                    await self._ensure_user(conn, uid)
                
                # 准备时间参数 - 智能处理日期边界
                date_from_param = None
                date_to_param = None
                if date_from:
                    date_from_param = datetime.fromisoformat(date_from)
                if date_to:
                    # 如果date_to只是日期格式（如"2025-08-19"），自动调整为当天结束时刻
                    if len(date_to) == 10:  # YYYY-MM-DD格式
                        date_to_param = datetime.fromisoformat(date_to + " 23:59:59")
                    else:
                        date_to_param = datetime.fromisoformat(date_to)
                
                # 智能处理多用户和单用户查询
                if len(user_ids) == 1:
                    # 单用户查询：直接调用数据库函数
                    result = await conn.fetchrow(
                        "SELECT * FROM get_expense_summary($1, $2, $3)",
                        user_ids[0], date_from_param, date_to_param
                    )
                else:
                    # 家庭统计（多用户）：合并多个用户的结果
                    combined_results = {
                        'total_amount': 0.0,
                        'record_count': 0,
                        'category_breakdown': {}
                    }
                    
                    for uid in user_ids:
                        user_result = await conn.fetchrow(
                            "SELECT * FROM get_expense_summary($1, $2, $3)",
                            uid, date_from_param, date_to_param
                        )
                        
                        if user_result:
                            # 累计总金额和记录数
                            combined_results['total_amount'] += float(user_result['total_amount'] or 0)
                            combined_results['record_count'] += int(user_result['record_count'] or 0)
                            
                            # 合并分类明细
                            user_categories = user_result['category_breakdown'] or {}
                            if isinstance(user_categories, str):
                                try:
                                    import json
                                    user_categories = json.loads(user_categories)
                                except:
                                    user_categories = {}
                            
                            for category, amount in user_categories.items():
                                if category in combined_results['category_breakdown']:
                                    combined_results['category_breakdown'][category] += float(amount)
                                else:
                                    combined_results['category_breakdown'][category] = float(amount)
                    
                    # 构造合并结果（直接使用字典，避免动态对象访问问题）
                    result = combined_results
                
                if result:
                    # 确保category_breakdown是JSON对象而不是字符串
                    category_breakdown = result['category_breakdown'] or {}
                    if isinstance(category_breakdown, str):
                        try:
                            import json
                            category_breakdown = json.loads(category_breakdown)
                        except:
                            category_breakdown = {}
                    
                    return {
                        "success": True,
                        "total_amount": float(result['total_amount']) if result['total_amount'] else 0,
                        "category_breakdown": category_breakdown,
                        "record_count": result['record_count'] or 0,
                        "date_range": {
                            "from": date_from,
                            "to": date_to
                        }
                    }
                else:
                    return {
                        "success": True,
                        "total_amount": 0,
                        "category_breakdown": {},
                        "record_count": 0,
                        "date_range": {
                            "from": date_from,
                            "to": date_to
                        }
                    }
                    
        except Exception as e:
            # 如果数据库函数不存在，回退到传统查询
            return await self._get_expense_summary_fallback(user_id, date_from, date_to, str(e))
    
    async def _get_expense_summary_fallback(self, user_id: str, date_from: Optional[str], date_to: Optional[str], error: str) -> Dict[str, Any]:
        """
        财务统计回退方案，使用优化的传统查询
        """
        try:
            async with self.pool.acquire() as conn:
                uid = self._normalize_user_id(user_id)
                
                # 构建优化的查询，使用计算列索引
                sql = """
                SELECT 
                    COALESCE(SUM(amount), 0) as total_amount,
                    COUNT(*) as record_count,
                    jsonb_object_agg(
                        COALESCE(category_extracted, '未分类'),
                        category_sum
                    ) FILTER (WHERE category_sum > 0) as category_breakdown
                FROM (
                    SELECT 
                        category_extracted,
                        SUM(amount) as category_sum
                    FROM memories 
                    WHERE user_id = $1 
                      AND type_extracted = 'expense'
                      AND amount IS NOT NULL
                """
                
                params = [uid]
                
                if date_from:
                    sql += f" AND occurred_at >= ${len(params) + 1}"
                    params.append(datetime.fromisoformat(date_from))
                if date_to:
                    sql += f" AND occurred_at <= ${len(params) + 1}"
                    params.append(datetime.fromisoformat(date_to))
                
                sql += " GROUP BY category_extracted) cat_summary"
                
                result = await conn.fetchrow(sql, *params)
                
                return {
                    "success": True,
                    "total_amount": float(result['total_amount']) if result['total_amount'] else 0,
                    "category_breakdown": result['category_breakdown'] or {},
                    "record_count": result['record_count'] or 0,
                    "date_range": {
                        "from": date_from,
                        "to": date_to
                    },
                    "fallback_used": True,
                    "original_error": error
                }
                
        except Exception as e:
                            return {
                    "success": False,
                    "error": str(e),
                    "fallback_error": True
                }

    async def _get_health_summary_optimized(self, user_id: str, person: Optional[str] = None, metric: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None) -> Dict[str, Any]:
        """
        健康数据统计优化函数
        """
        try:
            async with self.pool.acquire() as conn:
                uid = self._normalize_user_id(user_id)
                await self._ensure_user(conn, uid)
                
                # 准备时间参数
                date_from_param = None
                date_to_param = None
                if date_from:
                    date_from_param = datetime.fromisoformat(date_from)
                if date_to:
                    date_to_param = datetime.fromisoformat(date_to)
                
                # 尝试调用数据库函数
                try:
                    result = await conn.fetch(
                        "SELECT * FROM get_health_summary($1, $2, $3, $4, $5)",
                        uid, person, metric, date_from_param, date_to_param
                    )
                    
                    health_data = []
                    for row in result:
                        health_data.append({
                            "person": row['person'],
                            "metric": row['metric'], 
                            "latest_value": float(row['latest_value']) if row['latest_value'] else None,
                            "latest_date": row['latest_date'].isoformat() if row['latest_date'] else None,
                            "trend_data": row['trend_data'],
                            "record_count": row['record_count']
                        })
                    
                    return {
                        "success": True,
                        "health_summary": health_data,
                        "filters": {
                            "person": person,
                            "metric": metric,
                            "date_from": date_from,
                            "date_to": date_to
                        }
                    }
                
                except Exception as e:
                    # 回退到传统查询
                    return await self._get_health_summary_fallback(user_id, person, metric, date_from, date_to, str(e))
                    
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def _get_health_summary_fallback(self, user_id: str, person: Optional[str], metric: Optional[str], date_from: Optional[str], date_to: Optional[str], error: str) -> Dict[str, Any]:
        """
        健康数据统计回退方案
        """
        try:
            async with self.pool.acquire() as conn:
                uid = self._normalize_user_id(user_id)
                
                # 构建优化查询
                sql = """
                SELECT 
                    person_extracted as person,
                    metric_extracted as metric,
                    value_extracted as value,
                    occurred_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY person_extracted, metric_extracted 
                        ORDER BY occurred_at DESC
                    ) as rn
                FROM memories 
                WHERE user_id = $1 
                  AND type_extracted = 'health'
                  AND value_extracted IS NOT NULL
                """
                
                params = [uid]
                
                if person:
                    sql += f" AND person_extracted = ${len(params) + 1}"
                    params.append(person)
                if metric:
                    sql += f" AND metric_extracted = ${len(params) + 1}"
                    params.append(metric)
                if date_from:
                    sql += f" AND occurred_at >= ${len(params) + 1}"
                    params.append(datetime.fromisoformat(date_from))
                if date_to:
                    sql += f" AND occurred_at <= ${len(params) + 1}"
                    params.append(datetime.fromisoformat(date_to))
                
                sql += " ORDER BY person_extracted, metric_extracted, occurred_at DESC"
                
                rows = await conn.fetch(sql, *params)
                
                # 处理结果
                health_data = {}
                for row in rows:
                    key = f"{row['person']}_{row['metric']}"
                    if key not in health_data:
                        health_data[key] = {
                            "person": row['person'],
                            "metric": row['metric'],
                            "latest_value": None,
                            "latest_date": None,
                            "trend_data": [],
                            "record_count": 0
                        }
                    
                    if row['rn'] == 1:  # 最新记录
                        health_data[key]["latest_value"] = float(row['value'])
                        health_data[key]["latest_date"] = row['occurred_at'].isoformat()
                    
                    if row['rn'] <= 10:  # 最近10条用于趋势
                        health_data[key]["trend_data"].append({
                            "date": row['occurred_at'].isoformat(),
                            "value": float(row['value'])
                        })
                    
                    health_data[key]["record_count"] += 1
                
                return {
                    "success": True,
                    "health_summary": list(health_data.values()),
                    "filters": {
                        "person": person,
                        "metric": metric,
                        "date_from": date_from,
                        "date_to": date_to
                    },
                    "fallback_used": True,
                    "original_error": error
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "fallback_error": True
            }

    async def _get_learning_progress_optimized(self, user_id: str, person: Optional[str] = None, subject: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None) -> Dict[str, Any]:
        """
        学习进展统计优化函数
        """
        try:
            async with self.pool.acquire() as conn:
                uid = self._normalize_user_id(user_id)
                await self._ensure_user(conn, uid)
                
                # 准备时间参数
                date_from_param = None
                date_to_param = None
                if date_from:
                    date_from_param = datetime.fromisoformat(date_from)
                if date_to:
                    date_to_param = datetime.fromisoformat(date_to)
                
                # 尝试调用数据库函数
                try:
                    result = await conn.fetch(
                        "SELECT * FROM get_learning_progress($1, $2, $3, $4, $5)",
                        uid, person, subject, date_from_param, date_to_param
                    )
                    
                    learning_data = []
                    for row in result:
                        learning_data.append({
                            "person": row['person'],
                            "subject": row['subject'],
                            "avg_score": float(row['avg_score']) if row['avg_score'] else None,
                            "latest_score": float(row['latest_score']) if row['latest_score'] else None,
                            "improvement": float(row['improvement']) if row['improvement'] else None,
                            "record_count": row['record_count'],
                            "score_distribution": row['score_distribution']
                        })
                    
                    return {
                        "success": True,
                        "learning_progress": learning_data,
                        "filters": {
                            "person": person,
                            "subject": subject,
                            "date_from": date_from,
                            "date_to": date_to
                        }
                    }
                
                except Exception as e:
                    # 回退到传统查询
                    return await self._get_learning_progress_fallback(user_id, person, subject, date_from, date_to, str(e))
                    
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def _get_learning_progress_fallback(self, user_id: str, person: Optional[str], subject: Optional[str], date_from: Optional[str], date_to: Optional[str], error: str) -> Dict[str, Any]:
        """
        学习进展统计回退方案
        """
        try:
            async with self.pool.acquire() as conn:
                uid = self._normalize_user_id(user_id)
                
                # 构建优化查询
                sql = """
                SELECT 
                    person_extracted as person,
                    subject_extracted as subject,
                    value_extracted as score,
                    occurred_at
                FROM memories 
                WHERE user_id = $1 
                  AND type_extracted IN ('learning', 'exam', 'homework')
                  AND value_extracted IS NOT NULL
                """
                
                params = [uid]
                
                if person:
                    sql += f" AND person_extracted = ${len(params) + 1}"
                    params.append(person)
                if subject:
                    sql += f" AND subject_extracted = ${len(params) + 1}"
                    params.append(subject)
                if date_from:
                    sql += f" AND occurred_at >= ${len(params) + 1}"
                    params.append(datetime.fromisoformat(date_from))
                if date_to:
                    sql += f" AND occurred_at <= ${len(params) + 1}"
                    params.append(datetime.fromisoformat(date_to))
                
                sql += " ORDER BY person_extracted, subject_extracted, occurred_at DESC"
                
                rows = await conn.fetch(sql, *params)
                
                # 处理结果
                learning_data = {}
                for row in rows:
                    key = f"{row['person']}_{row['subject']}"
                    if key not in learning_data:
                        learning_data[key] = {
                            "person": row['person'],
                            "subject": row['subject'],
                            "scores": [],
                            "record_count": 0
                        }
                    
                    learning_data[key]["scores"].append(float(row['score']))
                    learning_data[key]["record_count"] += 1
                
                # 计算统计信息
                for data in learning_data.values():
                    scores = data["scores"]
                    if scores:
                        data["avg_score"] = round(sum(scores) / len(scores), 2)
                        data["latest_score"] = scores[0] if scores else None
                        data["improvement"] = scores[0] - scores[-1] if len(scores) > 1 else None
                        data["score_distribution"] = {
                            "excellent": len([s for s in scores if s >= 90]),
                            "good": len([s for s in scores if 80 <= s < 90]),
                            "average": len([s for s in scores if 70 <= s < 80]),
                            "needs_improvement": len([s for s in scores if s < 70])
                        }
                    del data["scores"]  # 移除临时字段
                
                return {
                    "success": True,
                    "learning_progress": list(learning_data.values()),
                    "filters": {
                        "person": person,
                        "subject": subject,
                        "date_from": date_from,
                        "date_to": date_to
                    },
                    "fallback_used": True,
                    "original_error": error
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "fallback_error": True
            }

    async def _get_data_type_summary_optimized(self, user_id: str, data_type: str, group_by_field: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None) -> Dict[str, Any]:
        """
        通用数据类型统计优化函数
        """
        try:
            async with self.pool.acquire() as conn:
                uid = self._normalize_user_id(user_id)
                await self._ensure_user(conn, uid)
                
                # 准备时间参数
                date_from_param = None
                date_to_param = None
                if date_from:
                    date_from_param = datetime.fromisoformat(date_from)
                if date_to:
                    date_to_param = datetime.fromisoformat(date_to)
                
                # 尝试调用数据库函数
                try:
                    result = await conn.fetch(
                        "SELECT * FROM get_data_type_summary($1, $2, $3, $4, $5)",
                        uid, data_type, group_by_field, date_from_param, date_to_param
                    )
                    
                    summary_data = []
                    for row in result:
                        summary_data.append({
                            "data_type": row['data_type'],
                            "group_value": row['group_value'],
                            "record_count": row['record_count'],
                            "numeric_summary": row['numeric_summary'],
                            "latest_records": row['latest_records']
                        })
                    
                    return {
                        "success": True,
                        "data_summary": summary_data,
                        "filters": {
                            "data_type": data_type,
                            "group_by_field": group_by_field,
                            "date_from": date_from,
                            "date_to": date_to
                        }
                    }
                
                except Exception as e:
                    # 回退到传统查询
                    return await self._get_data_type_summary_fallback(user_id, data_type, group_by_field, date_from, date_to, str(e))
                    
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def _get_data_type_summary_fallback(self, user_id: str, data_type: str, group_by_field: Optional[str], date_from: Optional[str], date_to: Optional[str], error: str) -> Dict[str, Any]:
        """
        通用数据类型统计回退方案
        """
        try:
            async with self.pool.acquire() as conn:
                uid = self._normalize_user_id(user_id)
                
                # 构建基础查询
                sql = f"""
                SELECT 
                    type_extracted as data_type,
                    {f"{group_by_field}_extracted as group_value," if group_by_field else "'total' as group_value,"}
                    COUNT(*) as record_count,
                    AVG(value_extracted) as avg_value,
                    MIN(value_extracted) as min_value,
                    MAX(value_extracted) as max_value,
                    SUM(value_extracted) as sum_value
                FROM memories 
                WHERE user_id = $1 
                  AND type_extracted = $2
                """
                
                params = [uid, data_type]
                
                if date_from:
                    sql += f" AND occurred_at >= ${len(params) + 1}"
                    params.append(datetime.fromisoformat(date_from))
                if date_to:
                    sql += f" AND occurred_at <= ${len(params) + 1}"
                    params.append(datetime.fromisoformat(date_to))
                
                if group_by_field:
                    sql += f" GROUP BY type_extracted, {group_by_field}_extracted"
                else:
                    sql += " GROUP BY type_extracted"
                
                sql += " ORDER BY record_count DESC"
                
                rows = await conn.fetch(sql, *params)
                
                summary_data = []
                for row in rows:
                    numeric_summary = None
                    if row['avg_value'] is not None:
                        numeric_summary = {
                            "avg": round(float(row['avg_value']), 2) if row['avg_value'] else None,
                            "min": float(row['min_value']) if row['min_value'] else None,
                            "max": float(row['max_value']) if row['max_value'] else None,
                            "sum": float(row['sum_value']) if row['sum_value'] else None
                        }
                    
                    summary_data.append({
                        "data_type": row['data_type'],
                        "group_value": row['group_value'],
                        "record_count": row['record_count'],
                        "numeric_summary": numeric_summary,
                        "latest_records": []  # 简化版本不包含最新记录
                    })
                
                return {
                    "success": True,
                    "data_summary": summary_data,
                    "filters": {
                        "data_type": data_type,
                        "group_by_field": group_by_field,
                        "date_from": date_from,
                        "date_to": date_to
                    },
                    "fallback_used": True,
                    "original_error": error
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "fallback_error": True
            }
    
    def _setup_tools(self):
        """注册所有通用工具"""
        if self.server is None:
            return
        
        @self.server.tool()
        async def store(content: str, ai_data: Dict[str, Any], user_id: str, embedding: Optional[Any] = None) -> Dict[str, Any]:
            """
            存储任何 AI 认为需要记住的信息
            
            财务数据存储时，ai_data 建议包含：
            - type: "expense"(支出) | "income"(收入) | "budget"(预算)
            - amount: 金额数值（必须）
            - category: 分类（如 "餐饮", "交通", "医疗"）
            - occurred_at: 发生时间（ISO格式）
            - person: 相关人员（可选）
            - description: 详细描述
            
            Args:
                content: 原始内容文本
                ai_data: AI理解的结构化信息
                user_id: 用户ID
                embedding: 向量表示（可选）
            """
            return await self._store(content, ai_data, user_id, embedding)
        
        @self.server.tool()
        async def search(user_id: str, query: Optional[str] = None, filters: Optional[Dict[str, Any]] = None, query_embedding: Optional[Any] = None) -> List[Dict[str, Any]]:
            """
            搜索相关记忆，支持语义和精确查询
            
            财务查询时建议使用精确过滤：
            - 按类型过滤: filters={"jsonb_equals": {"type": "expense"}}
            - 按时间过滤: filters={"date_from": "2025-08-01", "date_to": "2025-08-31"}
            - 按分类过滤: filters={"jsonb_equals": {"category": "餐饮"}}
            
            Args:
                user_id: 用户ID（必需）
                query: 搜索查询词（可选，为空时使用结构化过滤）
                filters: 过滤条件，支持各种精确匹配
                query_embedding: 查询向量（可选，用于语义搜索）
            """
            return await self._search(user_id, query, filters, query_embedding)
        
        @self.server.tool()
        async def aggregate(user_id: str, operation: str, field: Optional[str], filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            """
            对数据进行聚合统计
            
            重要：财务统计时需要区分数据类型，避免混淆预算和支出：
            - 支出统计: filters={"jsonb_equals": {"type": "expense"}}
            - 收入统计: filters={"jsonb_equals": {"type": "income"}} 
            - 预算查询: filters={"jsonb_equals": {"type": "budget"}}
            - 分类统计: filters={"group_by_ai_field": "category"}
            
            Args:
                user_id: 用户ID
                operation: sum|count|avg|min|max
                field: 要聚合的字段名（如 "amount"）
                filters: 过滤条件，支持 jsonb_equals/date_from/date_to/group_by_ai_field
                
            Returns:
                聚合结果，如有分组则返回 groups 数组
            """
            return await self._aggregate(user_id, operation, field, filters)
        
        @self.server.tool()
        async def schedule_reminder(memory_id: str, remind_at: str) -> Dict[str, Any]:
            return await self._schedule_reminder(memory_id, remind_at)
        
        @self.server.tool()
        async def get_pending_reminders(user_id: str) -> List[Dict[str, Any]]:
            return await self._get_pending_reminders(user_id)
        
        @self.server.tool()
        async def mark_reminder_sent(reminder_id: str) -> Dict[str, Any]:
            return await self._mark_reminder_sent(reminder_id)

        @self.server.tool()
        async def batch_store(memories: List[Dict[str, Any]]) -> Dict[str, Any]:
            return await self._batch_store(memories)

        @self.server.tool()
        async def batch_search(queries: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
            return await self._batch_search(queries)

        @self.server.tool()
        async def update_memory_fields(memory_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
            return await self._update_memory_fields(memory_id, fields)

        @self.server.tool()
        async def soft_delete(memory_id: str) -> Dict[str, Any]:
            return await self._soft_delete(memory_id)

        @self.server.tool()
        async def reembed_memories(filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
            return await self._reembed_memories(filters)
        
        @self.server.tool()
        async def render_chart(type: str, title: str, x: List[Any], series: List[Dict[str, Any]], style: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            return await self._render_chart(type, title, x, series, style)
        
        @self.server.tool()
        async def get_expense_summary_optimized(user_id: Union[str, List[str]], date_from: Optional[str] = None, date_to: Optional[str] = None) -> Dict[str, Any]:
            """
            高效的财务统计函数，支持家庭统计（多用户）和单用户统计
            
            Args:
                user_id: 用户ID（字符串）或用户ID列表（家庭统计）
                date_from: 开始日期（ISO格式，可选）
                date_to: 结束日期（ISO格式，可选）
            
            Returns:
                包含总金额、分类明细、记录数的统计结果
                家庭统计时自动合并所有家庭成员的数据
            """
            return await self._get_expense_summary_optimized(user_id, date_from, date_to)

        @self.server.tool()
        async def get_health_summary_optimized(user_id: str, person: Optional[str] = None, metric: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None) -> Dict[str, Any]:
            """
            高效的健康数据统计函数，支持趋势分析和最新状态查询
            
            Args:
                user_id: 用户ID
                person: 家庭成员（可选，如"儿子"、"大女儿"）
                metric: 健康指标（可选，如"身高"、"体重"）
                date_from: 开始日期（ISO格式，可选）
                date_to: 结束日期（ISO格式，可选）
            
            Returns:
                包含各成员各指标的最新值、趋势数据、记录数的统计结果
            """
            return await self._get_health_summary_optimized(user_id, person, metric, date_from, date_to)

        @self.server.tool()
        async def get_learning_progress_optimized(user_id: str, person: Optional[str] = None, subject: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None) -> Dict[str, Any]:
            """
            高效的学习进展统计函数，支持成绩分析和进步追踪
            
            Args:
                user_id: 用户ID
                person: 家庭成员（可选，如"儿子"、"大女儿"）
                subject: 学习科目（可选，如"数学"、"语文"）
                date_from: 开始日期（ISO格式，可选）
                date_to: 结束日期（ISO格式，可选）
            
            Returns:
                包含各成员各科目的平均分、最新分、进步情况、分数分布的统计结果
            """
            return await self._get_learning_progress_optimized(user_id, person, subject, date_from, date_to)

        @self.server.tool()  
        async def get_data_type_summary_optimized(user_id: str, data_type: str, group_by_field: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None) -> Dict[str, Any]:
            """
            通用数据类型统计函数，支持任意类型的聚合分析
            
            Args:
                user_id: 用户ID
                data_type: 数据类型（如"health"、"learning"、"expense"等）
                group_by_field: 分组字段（可选，如"person"、"metric"、"category"）
                date_from: 开始日期（ISO格式，可选）
                date_to: 结束日期（ISO格式，可选）
            
            Returns:
                包含按指定字段分组的统计结果，数值摘要，最新记录等
            """
            return await self._get_data_type_summary_optimized(user_id, data_type, group_by_field, date_from, date_to)
    
    async def run(self):
        """运行 MCP 服务器"""
        await self.initialize()
        try:
            # 仅在需要 stdio 模式时才初始化 Server 和注册工具
            if self.server is None:
                from mcp.server import Server
                from mcp.server.stdio import stdio_server
                self.server = Server("family-assistant")
                self._setup_tools()
            async with stdio_server() as (read, write):
                await self.server.run(read, write)
        finally:
            await self.close()

    def _normalize_user_id(self, user_id: str) -> uuid.UUID:
        """将传入的 user_id 转换为 UUID；若非标准 UUID，生成稳定的 UUID5。"""
        try:
            return uuid.UUID(user_id)
        except Exception:
            return uuid.uuid5(self._ns, f"faa:{user_id}")

    async def _ensure_user(self, conn, user_uuid: uuid.UUID) -> None:
        """确保 users 表中存在该用户（幂等）。"""
        await conn.execute(
            "INSERT INTO users (id) VALUES ($1) ON CONFLICT (id) DO NOTHING",
            user_uuid,
        )

    def _normalize_embedding(self, embedding: Optional[Any]) -> Optional[str]:
        """将传入的嵌入标准化为 pgvector 可接受的文本格式，如 "[0.1,0.2,...]"。
        支持 list[float] 或 str（已格式化或逗号分隔）。
        """
        if embedding is None:
            return None
        if isinstance(embedding, str):
            txt = embedding.strip()
            if txt.startswith("[") and txt.endswith("]"):
                return txt
            try:
                parts = [float(p.strip()) for p in txt.split(",")]
                return "[" + ",".join(f"{x:.6f}" for x in parts) + "]"
            except Exception:
                return None
        try:
            parts = [float(x) for x in embedding]
            return "[" + ",".join(f"{x:.6f}" for x in parts) + "]"
        except Exception:
            return None


if __name__ == "__main__":
    server = GenericMCPServer()
    asyncio.run(server.run()) 
