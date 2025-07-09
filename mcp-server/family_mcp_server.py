import asyncio
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, Resource
import structlog
from sqlalchemy import select, and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

# 假设这些会从主应用导入
from src.db.database import get_session
from src.db.models import Memory, Reminder
from src.core.config import settings

logger = structlog.get_logger()

class FamilyMemoryMCPServer:
    def __init__(self):
        self.server = Server("family-memory-mcp")
        self._setup_tools()
    
    def _setup_tools(self):
        """注册所有MCP工具"""
        
        # 存储工具组
        @self.server.tool()
        async def store_memory(
            content: str,
            category: str,
            metadata: Optional[Dict[str, Any]] = None
        ) -> Dict[str, Any]:
            """存储家庭记忆"""
            if category not in ['finance', 'health', 'task', 'info']:
                return {"error": f"Invalid category: {category}"}
            
            async with get_session() as session:
                # 解析内容并构建数据
                data = self._parse_content(content, category)
                
                memory = Memory(
                    user_id=metadata.get('user_id', 'default'),
                    category=category,
                    data=data,
                    metadata=metadata or {}
                )
                
                session.add(memory)
                await session.commit()
                
                return {
                    "success": True,
                    "memory_id": str(memory.id),
                    "message": f"已存储{category}记忆"
                }
        
        # 查询工具组
        @self.server.tool()
        async def query_memories(
            query: str,
            category: Optional[str] = None,
            time_range: Optional[Dict[str, str]] = None
        ) -> List[Dict[str, Any]]:
            """查询家庭记忆"""
            async with get_session() as session:
                stmt = select(Memory)
                
                if category:
                    stmt = stmt.where(Memory.category == category)
                
                if time_range:
                    start_date = datetime.fromisoformat(time_range.get('start'))
                    end_date = datetime.fromisoformat(time_range.get('end'))
                    stmt = stmt.where(Memory.created_at.between(start_date, end_date))
                
                # 简单的文本搜索
                if query:
                    stmt = stmt.where(
                        Memory.data['content'].astext.ilike(f'%{query}%')
                    )
                
                result = await session.execute(stmt.order_by(Memory.created_at.desc()).limit(20))
                memories = result.scalars().all()
                
                return [
                    {
                        "id": str(m.id),
                        "category": m.category,
                        "content": m.data.get('content', ''),
                        "data": m.data,
                        "created_at": m.created_at.isoformat(),
                    }
                    for m in memories
                ]
        
        @self.server.tool()
        async def get_person_info(
            person_name: str,
            info_type: Optional[str] = None
        ) -> Dict[str, Any]:
            """查询家庭成员信息"""
            async with get_session() as session:
                stmt = select(Memory).where(
                    and_(
                        Memory.category.in_(['health', 'info']),
                        Memory.data['person'].astext == person_name
                    )
                )
                
                if info_type:
                    stmt = stmt.where(Memory.data['type'].astext == info_type)
                
                result = await session.execute(stmt.order_by(Memory.created_at.desc()))
                memories = result.scalars().all()
                
                return {
                    "person": person_name,
                    "records": [
                        {
                            "type": m.data.get('type'),
                            "data": m.data,
                            "date": m.created_at.isoformat()
                        }
                        for m in memories
                    ]
                }
        
        # 分析工具组
        @self.server.tool()
        async def analyze_finance(
            time_range: Dict[str, str],
            category: Optional[str] = None
        ) -> Dict[str, Any]:
            """财务简单统计"""
            async with get_session() as session:
                start_date = datetime.fromisoformat(time_range['start'])
                end_date = datetime.fromisoformat(time_range['end'])
                
                # 支出统计
                expense_stmt = select(
                    func.sum(Memory.data['amount'].astext.cast(Float)).label('total'),
                    func.count().label('count')
                ).where(
                    and_(
                        Memory.category == 'finance',
                        Memory.data['type'].astext == 'expense',
                        Memory.created_at.between(start_date, end_date)
                    )
                )
                
                # 收入统计
                income_stmt = select(
                    func.sum(Memory.data['amount'].astext.cast(Float)).label('total'),
                    func.count().label('count')
                ).where(
                    and_(
                        Memory.category == 'finance',
                        Memory.data['type'].astext == 'income',
                        Memory.created_at.between(start_date, end_date)
                    )
                )
                
                expense_result = await session.execute(expense_stmt)
                income_result = await session.execute(income_stmt)
                
                expense_data = expense_result.one()
                income_data = income_result.one()
                
                return {
                    "period": f"{start_date.date()} - {end_date.date()}",
                    "expenses": {
                        "total": float(expense_data.total or 0),
                        "count": expense_data.count
                    },
                    "income": {
                        "total": float(income_data.total or 0),
                        "count": income_data.count
                    },
                    "balance": float((income_data.total or 0) - (expense_data.total or 0))
                }
        
        @self.server.tool()
        async def analyze_health(
            person: str,
            metric_type: str
        ) -> Dict[str, Any]:
            """健康趋势分析"""
            async with get_session() as session:
                stmt = select(Memory).where(
                    and_(
                        Memory.category == 'health',
                        Memory.data['person'].astext == person,
                        Memory.data['metrics'][metric_type].astext.isnot(None)
                    )
                ).order_by(Memory.created_at)
                
                result = await session.execute(stmt)
                memories = result.scalars().all()
                
                trends = [
                    {
                        "date": m.created_at.isoformat(),
                        "value": float(m.data['metrics'].get(metric_type, 0)),
                        "unit": m.data['metrics'].get('unit', '')
                    }
                    for m in memories
                ]
                
                return {
                    "person": person,
                    "metric": metric_type,
                    "trends": trends,
                    "latest": trends[-1] if trends else None
                }
        
        # 提醒工具组
        @self.server.tool()
        async def set_reminder(
            content: str,
            remind_time: str,
            repeat_pattern: str = 'once'
        ) -> Dict[str, Any]:
            """设置提醒"""
            async with get_session() as session:
                reminder = Reminder(
                    content=content,
                    remind_at=datetime.fromisoformat(remind_time),
                    repeat_pattern=repeat_pattern,
                    created_by='default',  # 应该从context获取
                    metadata={}
                )
                
                session.add(reminder)
                await session.commit()
                
                return {
                    "success": True,
                    "reminder_id": str(reminder.id),
                    "remind_at": reminder.remind_at.isoformat(),
                    "message": f"提醒已设置：{remind_time}"
                }
        
        @self.server.tool()
        async def list_reminders(
            time_range: Optional[Dict[str, str]] = None,
            status: Optional[str] = None
        ) -> List[Dict[str, Any]]:
            """查看提醒列表"""
            async with get_session() as session:
                stmt = select(Reminder)
                
                if status == 'pending':
                    stmt = stmt.where(Reminder.is_sent == False)
                elif status == 'sent':
                    stmt = stmt.where(Reminder.is_sent == True)
                
                if time_range:
                    start_date = datetime.fromisoformat(time_range['start'])
                    end_date = datetime.fromisoformat(time_range['end'])
                    stmt = stmt.where(Reminder.remind_at.between(start_date, end_date))
                
                result = await session.execute(stmt.order_by(Reminder.remind_at))
                reminders = result.scalars().all()
                
                return [
                    {
                        "id": str(r.id),
                        "content": r.content,
                        "remind_at": r.remind_at.isoformat(),
                        "repeat_pattern": r.repeat_pattern,
                        "is_sent": r.is_sent,
                        "created_at": r.created_at.isoformat()
                    }
                    for r in reminders
                ]
    
    def _parse_content(self, content: str, category: str) -> Dict[str, Any]:
        """解析内容为结构化数据"""
        # 这里应该使用更智能的解析，暂时简化处理
        data = {"content": content, "raw_message": content}
        
        if category == 'finance':
            # 简单提取金额
            import re
            amount_match = re.search(r'(\d+(?:\.\d+)?)', content)
            if amount_match:
                data['amount'] = float(amount_match.group(1))
            
            if '支出' in content or '花' in content:
                data['type'] = 'expense'
            elif '收入' in content or '收' in content:
                data['type'] = 'income'
        
        return data
    
    async def run(self):
        """运行MCP服务器"""
        async with stdio_server() as (read, write):
            await self.server.run(read, write)


if __name__ == "__main__":
    server = FamilyMemoryMCPServer()
    asyncio.run(server.run())