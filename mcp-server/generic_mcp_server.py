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

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import asyncpg
import numpy as np
from openai import AsyncOpenAI

# 环境变量
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://faa:faa@localhost:5432/family_assistant')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# OpenAI 客户端
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


class GenericMCPServer:
    def __init__(self):
        self.server = Server("family-assistant")
        self.pool = None
        self._setup_tools()
    
    async def initialize(self):
        """初始化数据库连接池"""
        self.pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    
    async def close(self):
        """关闭连接池"""
        if self.pool:
            await self.pool.close()
    
    async def _store(self, content: str, ai_data: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """存储任何 AI 认为需要记住的信息"""
        try:
            async with self.pool.acquire() as conn:
                # 生成向量（如果有 OpenAI API）
                embedding = None
                if openai_client:
                    response = await openai_client.embeddings.create(
                        model="text-embedding-3-small",
                        input=content
                    )
                    embedding = response.data[0].embedding
                
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
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING id
                    """,
                    uuid.uuid4(),
                    uuid.UUID(user_id),
                    content,
                    json.dumps(ai_data),
                    embedding,
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
    
    async def _search(self, query: str, user_id: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """搜索相关记忆，支持语义和精确查询"""
        try:
            async with self.pool.acquire() as conn:
                results = []
                
                # 如果有查询文本，进行语义搜索
                if query and openai_client:
                    # 生成查询向量
                    response = await openai_client.embeddings.create(
                        model="text-embedding-3-small",
                        input=query
                    )
                    query_embedding = response.data[0].embedding
                    
                    # 构建查询
                    sql = """
                    SELECT id, content, ai_understanding, amount, occurred_at,
                           1 - (embedding <=> $1::vector) as similarity
                    FROM memories
                    WHERE user_id = $2
                    """
                    params = [query_embedding, uuid.UUID(user_id)]
                    
                    # 添加过滤条件
                    if filters:
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
                    
                    sql += " ORDER BY similarity DESC LIMIT 20"
                    
                    rows = await conn.fetch(sql, *params)
                else:
                    # 没有查询文本，只用过滤条件
                    sql = """
                    SELECT id, content, ai_understanding, amount, occurred_at
                    FROM memories
                    WHERE user_id = $1
                    """
                    params = [uuid.UUID(user_id)]
                    
                    if filters:
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
                    
                    sql += " ORDER BY occurred_at DESC LIMIT 20"
                    
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
                
                return results
                
        except Exception as e:
            return [{
                "error": str(e)
            }]
    
    async def _aggregate(self, user_id: str, operation: str, field: str, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """对数据进行聚合统计"""
        try:
            async with self.pool.acquire() as conn:
                # 构建聚合查询
                if operation not in ['sum', 'count', 'avg', 'min', 'max']:
                    return {"error": f"不支持的操作: {operation}"}
                
                if operation == 'count':
                    sql = f"SELECT COUNT(*) as result FROM memories WHERE user_id = $1"
                else:
                    sql = f"SELECT {operation.upper()}({field}) as result FROM memories WHERE user_id = $1"
                
                params = [uuid.UUID(user_id)]
                
                # 添加过滤条件
                if filters:
                    if 'date_from' in filters:
                        sql += f" AND occurred_at >= ${len(params) + 1}"
                        params.append(datetime.fromisoformat(filters['date_from']))
                    if 'date_to' in filters:
                        sql += f" AND occurred_at <= ${len(params) + 1}"
                        params.append(datetime.fromisoformat(filters['date_to']))
                
                # 对于非 count 操作，确保字段不为空
                if operation != 'count':
                    sql += f" AND {field} IS NOT NULL"
                
                result = await conn.fetchval(sql, *params)
                
                return {
                    "operation": operation,
                    "field": field,
                    "result": float(result) if result else 0,
                    "filters": filters
                }
                
        except Exception as e:
            return {
                "error": str(e)
            }
    
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
    
    def _setup_tools(self):
        """注册所有通用工具"""
        
        @self.server.tool()
        async def store(content: str, ai_data: Dict[str, Any], user_id: str) -> Dict[str, Any]:
            return await self._store(content, ai_data, user_id)
        
        @self.server.tool()
        async def search(query: str, user_id: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
            return await self._search(query, user_id, filters)
        
        @self.server.tool()
        async def aggregate(user_id: str, operation: str, field: str, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
    
    async def run(self):
        """运行 MCP 服务器"""
        await self.initialize()
        try:
            async with stdio_server() as (read, write):
                await self.server.run(read, write)
        finally:
            await self.close()


if __name__ == "__main__":
    server = GenericMCPServer()
    asyncio.run(server.run()) 