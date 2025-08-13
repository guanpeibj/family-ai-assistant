#!/usr/bin/env python3
"""
通用 MCP 服务端 - 完全 AI 驱动，不包含任何业务逻辑
"""
import asyncio
import json
import os
from typing import Dict, List, Any, Optional
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
    
    async def _search(self, query: str, user_id: str, filters: Optional[Dict[str, Any]] = None, query_embedding: Optional[Any] = None) -> List[Dict[str, Any]]:
        """搜索相关记忆，支持语义和精确查询"""
        try:
            async with self.pool.acquire() as conn:
                results = []
                uid = self._normalize_user_id(user_id)
                await self._ensure_user(conn, uid)
                # 共享线程模式：当指定 shared_thread=True 且提供 thread_id 时，放宽 user_id 约束，允许跨用户按线程聚合
                shared_thread_mode = bool(filters and filters.get('shared_thread') and filters.get('thread_id'))
                
                # 如果提供查询向量，进行语义搜索
                if query_embedding is not None:
                    used_vector = True
                    used_trigram = False
                    query_embedding_text = self._normalize_embedding(query_embedding)
                    
                    # 构建查询
                    if shared_thread_mode:
                        sql = """
                        SELECT id, content, ai_understanding, amount, occurred_at,
                               1 - (embedding <=> $1::vector) as similarity
                        FROM memories
                        WHERE embedding IS NOT NULL
                        """
                        params = [query_embedding_text]
                    else:
                        sql = """
                        SELECT id, content, ai_understanding, amount, occurred_at,
                               1 - (embedding <=> $1::vector) as similarity
                        FROM memories
                        WHERE user_id = $2 AND embedding IS NOT NULL
                        """
                        params = [query_embedding_text, uid]
                    
                    # 添加过滤条件
                    if filters:
                        # thread_id/type 过滤（来自 ai_data 中）
                        if 'thread_id' in filters:
                            sql += f" AND (ai_understanding->>'thread_id') = ${len(params) + 1}"
                            params.append(filters['thread_id'])
                        if 'type' in filters:
                            sql += f" AND (ai_understanding->>'type') = ${len(params) + 1}"
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
                        # 通用 JSONB 等值过滤：filters.jsonb_equals = {key: value}
                        je = filters.get('jsonb_equals') if isinstance(filters.get('jsonb_equals'), dict) else None
                        if je:
                            for k, v in je.items():
                                sql += f" AND (ai_understanding->>'{k}') = ${len(params) + 1}"
                                params.append(str(v))
                    
                    limit_value = 20
                    if filters and isinstance(filters.get('limit'), int) and filters['limit'] > 0:
                        limit_value = min(filters['limit'], 100)
                    sql += " ORDER BY similarity DESC LIMIT $" + str(len(params) + 1)
                    params.append(limit_value)
                    
                    rows = await conn.fetch(sql, *params)
                else:
                    # 无查询向量：过滤 + 可选 trigram 相似匹配（需 pg_trgm）
                    used_vector = False
                    if shared_thread_mode:
                        base_sql = """
                        SELECT id, content, ai_understanding, amount, occurred_at
                        FROM memories
                        WHERE TRUE
                        """
                        params = []
                    else:
                        base_sql = """
                        SELECT id, content, ai_understanding, amount, occurred_at
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
                        if 'thread_id' in filters:
                            sql += f" AND (ai_understanding->>'thread_id') = ${len(params) + 1}"
                            params.append(filters['thread_id'])
                        if 'type' in filters:
                            sql += f" AND (ai_understanding->>'type') = ${len(params) + 1}"
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
                        # 通用 JSONB 等值过滤
                        je = filters.get('jsonb_equals') if isinstance(filters.get('jsonb_equals'), dict) else None
                        if je:
                            for k, v in je.items():
                                sql += f" AND (ai_understanding->>'{k}') = ${len(params) + 1}"
                                params.append(str(v))
                        if 'limit' in filters and isinstance(filters['limit'], int):
                            limit_value = min(max(filters['limit'], 1), 200)
                        else:
                            limit_value = 20
                    else:
                        limit_value = 20

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
                        "occurred_at": row['occurred_at'].isoformat() if row['occurred_at'] else None
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
    
    async def _aggregate(self, user_id: str, operation: str, field: Optional[str], filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """对数据进行聚合统计"""
        try:
            async with self.pool.acquire() as conn:
                uid = self._normalize_user_id(user_id)
                await self._ensure_user(conn, uid)
                # 构建聚合查询
                if operation not in ['sum', 'count', 'avg', 'min', 'max']:
                    return {"error": f"不支持的操作: {operation}"}
                
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
                params = [uid]
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
                    sql = f"SELECT {', '.join(select_cols)} FROM memories WHERE user_id = $1"
                else:
                    if operation == 'count':
                        sql = f"SELECT COUNT(*) as result FROM memories WHERE user_id = $1"
                    else:
                        sql = f"SELECT {operation.upper()}({field}) as result FROM memories WHERE user_id = $1"
                
                # 添加过滤条件
                if filters:
                    if 'date_from' in filters:
                        sql += f" AND occurred_at >= ${len(params) + 1}"
                        params.append(datetime.fromisoformat(filters['date_from']))
                    if 'date_to' in filters:
                        sql += f" AND occurred_at <= ${len(params) + 1}"
                        params.append(datetime.fromisoformat(filters['date_to']))
                    # 通用 JSONB 等值过滤
                    je = filters.get('jsonb_equals') if isinstance(filters.get('jsonb_equals'), dict) else None
                    if je:
                        for k, v in je.items():
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
    
    def _setup_tools(self):
        """注册所有通用工具"""
        if self.server is None:
            return
        
        @self.server.tool()
        async def store(content: str, ai_data: Dict[str, Any], user_id: str, embedding: Optional[Any] = None) -> Dict[str, Any]:
            return await self._store(content, ai_data, user_id, embedding)
        
        @self.server.tool()
        async def search(query: str, user_id: str, filters: Optional[Dict[str, Any]] = None, query_embedding: Optional[Any] = None) -> List[Dict[str, Any]]:
            return await self._search(query, user_id, filters, query_embedding)
        
        @self.server.tool()
        async def aggregate(user_id: str, operation: str, field: Optional[str], filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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