"""
通用MCP Server - 提供基础数据操作能力，不预设业务逻辑
"""
import asyncio
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from mcp.server import Server
from mcp.server.stdio import stdio_server
import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
import openai
import numpy as np
import os

logger = structlog.get_logger()


class GenericMCPServer:
    def __init__(self):
        self.server = Server("family-ai-mcp")
        self.database_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://faa_user:faa_password@postgres:5432/faa_db")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.engine = create_async_engine(self.database_url)
        self.openai_client = openai.AsyncClient(api_key=self.openai_api_key)
        self._setup_tools()
    
    def _setup_tools(self):
        """注册通用工具 - 不预设具体业务逻辑"""
        
        @self.server.tool()
        async def store(content: str, ai_data: Dict[str, Any], user_id: str) -> Dict[str, Any]:
            """存储信息 - 完全由AI决定存什么"""
            async with AsyncSession(self.engine) as session:
                try:
                    # 生成embedding
                    embedding = await self._generate_embedding(content)
                    
                    # 提取精确数据（如果AI提供了）
                    amount = None
                    if 'amount' in ai_data:
                        try:
                            amount = float(ai_data['amount'])
                        except:
                            pass
                    
                    occurred_at = None
                    if 'occurred_at' in ai_data:
                        try:
                            occurred_at = datetime.fromisoformat(ai_data['occurred_at'])
                        except:
                            pass
                    
                    # 使用参数化查询插入数据
                    result = await session.execute(
                        text("""
                            INSERT INTO memories (user_id, content, ai_understanding, embedding, amount, occurred_at)
                            VALUES (:user_id, :content, :ai_understanding::jsonb, :embedding, :amount, :occurred_at)
                            RETURNING id
                        """),
                        {
                            'user_id': user_id,
                            'content': content,
                            'ai_understanding': json.dumps(ai_data, ensure_ascii=False),
                            'embedding': embedding,
                            'amount': amount,
                            'occurred_at': occurred_at
                        }
                    )
                    
                    memory_id = result.scalar()
                    await session.commit()
                    
                    return {"success": True, "id": str(memory_id)}
                except Exception as e:
                    logger.error(f"Store error: {e}")
                    return {"success": False, "error": str(e)}
        
        @self.server.tool()
        async def search(query: str, user_id: Optional[str] = None, filters: Optional[Dict] = None) -> List[Dict]:
            """搜索信息 - 支持语义搜索和精确查询"""
            async with AsyncSession(self.engine) as session:
                try:
                    # 构建查询
                    conditions = []
                    params = {}
                    
                    if user_id:
                        conditions.append("user_id = :user_id")
                        params['user_id'] = user_id
                    
                    # 精确过滤条件
                    if filters:
                        if 'min_amount' in filters:
                            conditions.append("amount >= :min_amount")
                            params['min_amount'] = filters['min_amount']
                        if 'max_amount' in filters:
                            conditions.append("amount <= :max_amount")
                            params['max_amount'] = filters['max_amount']
                        if 'date_from' in filters:
                            conditions.append("occurred_at >= :date_from")
                            params['date_from'] = filters['date_from']
                        if 'date_to' in filters:
                            conditions.append("occurred_at <= :date_to")
                            params['date_to'] = filters['date_to']
                    
                    where_clause = " AND ".join(conditions) if conditions else "1=1"
                    
                    # 语义搜索或时间排序
                    if query:
                        query_embedding = await self._generate_embedding(query)
                        sql = f"""
                            SELECT id, content, ai_understanding, amount, occurred_at, created_at,
                                   embedding <-> :embedding::vector as distance
                            FROM memories
                            WHERE {where_clause}
                            ORDER BY distance
                            LIMIT 20
                        """
                        params['embedding'] = query_embedding
                    else:
                        sql = f"""
                            SELECT id, content, ai_understanding, amount, occurred_at, created_at
                            FROM memories
                            WHERE {where_clause}
                            ORDER BY created_at DESC
                            LIMIT 20
                        """
                    
                    result = await session.execute(text(sql), params)
                    rows = result.fetchall()
                    
                    return [
                        {
                            'id': str(row.id),
                            'content': row.content,
                            'ai_understanding': row.ai_understanding,
                            'amount': float(row.amount) if row.amount else None,
                            'occurred_at': row.occurred_at.isoformat() if row.occurred_at else None,
                            'created_at': row.created_at.isoformat()
                        }
                        for row in rows
                    ]
                except Exception as e:
                    logger.error(f"Search error: {e}")
                    return []
        
        @self.server.tool()
        async def aggregate(user_id: str, operation: str, field: str = "amount", filters: Optional[Dict] = None) -> Dict[str, Any]:
            """聚合计算 - 用于精确统计"""
            async with AsyncSession(self.engine) as session:
                try:
                    # 构建条件
                    conditions = ["user_id = :user_id"]
                    params = {'user_id': user_id}
                    
                    if filters:
                        if 'date_from' in filters:
                            conditions.append("occurred_at >= :date_from")
                            params['date_from'] = filters['date_from']
                        if 'date_to' in filters:
                            conditions.append("occurred_at <= :date_to")
                            params['date_to'] = filters['date_to']
                        if 'ai_filter' in filters:
                            # AI可以传递JSONB查询条件
                            for key, value in filters['ai_filter'].items():
                                conditions.append(f"ai_understanding->>{key!r} = :{key}")
                                params[key] = value
                    
                    where_clause = " AND ".join(conditions)
                    
                    # 执行聚合操作
                    if operation == "sum":
                        sql = f"SELECT SUM({field}) as result FROM memories WHERE {where_clause}"
                    elif operation == "count":
                        sql = f"SELECT COUNT(*) as result FROM memories WHERE {where_clause}"
                    elif operation == "avg":
                        sql = f"SELECT AVG({field}) as result FROM memories WHERE {where_clause}"
                    elif operation == "max":
                        sql = f"SELECT MAX({field}) as result FROM memories WHERE {where_clause}"
                    elif operation == "min":
                        sql = f"SELECT MIN({field}) as result FROM memories WHERE {where_clause}"
                    else:
                        return {"error": f"Unknown operation: {operation}"}
                    
                    result = await session.execute(text(sql), params)
                    value = result.scalar()
                    
                    return {
                        "operation": operation,
                        "field": field,
                        "result": float(value) if value else 0,
                        "filters": filters
                    }
                except Exception as e:
                    logger.error(f"Aggregate error: {e}")
                    return {"error": str(e)}
        
        @self.server.tool()
        async def schedule_reminder(memory_id: str, remind_at: str) -> Dict[str, Any]:
            """设置提醒 - 基于已存储的记忆"""
            async with AsyncSession(self.engine) as session:
                try:
                    remind_time = datetime.fromisoformat(remind_at)
                    
                    result = await session.execute(
                        text("""
                            INSERT INTO reminders (memory_id, remind_at)
                            VALUES (:memory_id, :remind_at)
                            RETURNING id
                        """),
                        {
                            'memory_id': memory_id,
                            'remind_at': remind_time
                        }
                    )
                    
                    reminder_id = result.scalar()
                    await session.commit()
                    
                    return {"success": True, "reminder_id": str(reminder_id)}
                except Exception as e:
                    logger.error(f"Schedule reminder error: {e}")
                    return {"success": False, "error": str(e)}
        
        @self.server.tool()
        async def get_pending_reminders(user_id: str) -> List[Dict]:
            """获取待发送的提醒"""
            async with AsyncSession(self.engine) as session:
                try:
                    sql = """
                        SELECT r.id, r.remind_at, m.content, m.ai_understanding
                        FROM reminders r
                        JOIN memories m ON r.memory_id = m.id
                        WHERE m.user_id = :user_id 
                          AND r.sent IS NULL 
                          AND r.remind_at <= :now
                        ORDER BY r.remind_at
                    """
                    
                    result = await session.execute(
                        text(sql),
                        {'user_id': user_id, 'now': datetime.now()}
                    )
                    
                    rows = result.fetchall()
                    
                    return [
                        {
                            'reminder_id': str(row.id),
                            'remind_at': row.remind_at.isoformat(),
                            'content': row.content,
                            'ai_understanding': row.ai_understanding
                        }
                        for row in rows
                    ]
                except Exception as e:
                    logger.error(f"Get reminders error: {e}")
                    return []
        
        @self.server.tool()
        async def mark_reminder_sent(reminder_id: str) -> Dict[str, Any]:
            """标记提醒已发送"""
            async with AsyncSession(self.engine) as session:
                try:
                    await session.execute(
                        text("UPDATE reminders SET sent = :now WHERE id = :id"),
                        {'id': reminder_id, 'now': datetime.now()}
                    )
                    await session.commit()
                    return {"success": True}
                except Exception as e:
                    logger.error(f"Mark reminder error: {e}")
                    return {"success": False, "error": str(e)}
    
    async def _generate_embedding(self, text: str) -> List[float]:
        """生成文本embedding"""
        try:
            response = await self.openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Embedding generation error: {e}")
            # 返回零向量作为后备
            return [0.0] * 1536
    
    async def run(self):
        """运行MCP服务器"""
        async with stdio_server() as (read, write):
            await self.server.run(read, write)


if __name__ == "__main__":
    server = GenericMCPServer()
    asyncio.run(server.run()) 