"""
AI驱动的核心引擎 - 让AI决定一切
"""
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
import openai
import structlog
import mcp

from .core.config import settings

logger = structlog.get_logger(__name__)


class AIEngine:
    def __init__(self):
        self.openai_client = openai.AsyncClient(api_key=settings.OPENAI_API_KEY)
        self.mcp_client = None  # 将在启动时初始化
        
    async def initialize_mcp(self):
        """初始化MCP客户端连接"""
        # TODO: 实际的MCP客户端连接
        logger.info("MCP client initialized")
    
    async def process_message(self, content: str, user_id: str) -> str:
        """
        处理用户消息 - 完全由AI驱动
        """
        try:
            # 第一步：理解用户意图和提取信息
            understanding = await self._understand_message(content, user_id)
            
            # 第二步：执行必要的操作
            result = await self._execute_actions(understanding, user_id)
            
            # 第三步：生成回复
            response = await self._generate_response(content, understanding, result)
            
            return response
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return "抱歉，处理您的消息时出现了错误。"
    
    async def _understand_message(self, content: str, user_id: str) -> Dict[str, Any]:
        """
        AI理解消息内容
        """
        prompt = f"""
        分析用户消息并提取所有相关信息。
        
        用户消息：{content}
        
        请分析并返回JSON格式的理解结果，包括但不限于：
        1. intent: 用户意图（record_expense/record_income/record_health/query/set_reminder/general_chat等）
        2. entities: 提取的实体信息
        3. need_action: 是否需要执行动作
        4. suggested_actions: 建议的动作列表
        
        对于财务相关：
        - amount: 金额（数字）
        - type: expense/income
        - category: 分类（餐饮/购物/交通等）
        
        对于健康相关：
        - person: 人物（儿子/女儿/妻子等）
        - metric: 指标（身高/体重/体温等）
        - value: 数值
        - unit: 单位
        
        对于提醒相关：
        - remind_content: 提醒内容
        - remind_time: 提醒时间（ISO格式）
        - repeat: 重复模式（如果有）
        
        请提取所有你认为重要的信息，不要局限于上述字段。
        """
        
        response = await self.openai_client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "你是一个智能助手，擅长理解用户意图并提取结构化信息。"},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.3
        )
        
        understanding = json.loads(response.choices[0].message.content)
        logger.info(f"Message understanding: {understanding}")
        
        # 补充时间信息
        if 'occurred_at' not in understanding.get('entities', {}):
            # 如果消息中包含"今天"、"昨天"等，AI应该已经理解
            # 如果没有明确时间，默认为现在
            if understanding.get('need_action') and understanding.get('intent') in ['record_expense', 'record_income', 'record_health']:
                understanding['entities']['occurred_at'] = datetime.now().isoformat()
        
        return understanding
    
    async def _execute_actions(self, understanding: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """
        根据理解结果执行动作
        """
        result = {"actions_taken": []}
        
        if not understanding.get('need_action'):
            return result
        
        intent = understanding.get('intent')
        entities = understanding.get('entities', {})
        
        # 记录类操作
        if intent in ['record_expense', 'record_income', 'record_health', 'record_info']:
            # 准备AI理解的数据
            ai_data = {
                'intent': intent,
                'entities': entities,
                'timestamp': datetime.now().isoformat()
            }
            
            # 合并所有实体信息
            ai_data.update(entities)
            
            # 调用MCP store工具
            store_result = await self._call_mcp_tool(
                'store',
                content=understanding.get('original_content', entities.get('content', '')),
                ai_data=ai_data,
                user_id=user_id
            )
            
            result['actions_taken'].append({
                'action': 'store',
                'result': store_result
            })
            
            # 如果需要设置提醒
            if entities.get('remind_time') and store_result.get('success'):
                reminder_result = await self._call_mcp_tool(
                    'schedule_reminder',
                    memory_id=store_result['id'],
                    remind_at=entities['remind_time']
                )
                result['actions_taken'].append({
                    'action': 'schedule_reminder',
                    'result': reminder_result
                })
        
        # 查询类操作
        elif intent == 'query':
            # 构建查询参数
            filters = {}
            if entities.get('date_from'):
                filters['date_from'] = entities['date_from']
            if entities.get('date_to'):
                filters['date_to'] = entities['date_to']
            if entities.get('min_amount'):
                filters['min_amount'] = entities['min_amount']
            if entities.get('max_amount'):
                filters['max_amount'] = entities['max_amount']
            
            # 执行搜索
            search_result = await self._call_mcp_tool(
                'search',
                query=entities.get('query_text', ''),
                user_id=user_id,
                filters=filters if filters else None
            )
            
            result['actions_taken'].append({
                'action': 'search',
                'result': search_result
            })
            
            # 如果需要聚合统计
            if entities.get('need_aggregation'):
                agg_result = await self._call_mcp_tool(
                    'aggregate',
                    user_id=user_id,
                    operation=entities.get('aggregation_type', 'sum'),
                    field='amount',
                    filters=filters if filters else None
                )
                result['actions_taken'].append({
                    'action': 'aggregate',
                    'result': agg_result
                })
        
        return result
    
    async def _generate_response(self, original_message: str, understanding: Dict[str, Any], execution_result: Dict[str, Any]) -> str:
        """
        生成自然语言回复
        """
        prompt = f"""
        基于用户消息和执行结果，生成一个友好、有用的回复。
        
        用户原始消息：{original_message}
        
        理解结果：{json.dumps(understanding, ensure_ascii=False)}
        
        执行结果：{json.dumps(execution_result, ensure_ascii=False)}
        
        要求：
        1. 用中文回复
        2. 确认已完成的操作
        3. 如果是财务记录，提供简单的统计（如本月累计）
        4. 如果是查询，简洁地展示结果
        5. 如果设置了提醒，确认提醒时间
        6. 保持友好、简洁的语气
        """
        
        response = await self.openai_client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "你是一个贴心的家庭AI助手，帮助用户管理家庭事务。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        
        return response.choices[0].message.content
    
    async def _call_mcp_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """
        调用MCP工具
        """
        # TODO: 实际的MCP调用
        # 这里暂时模拟
        logger.info(f"Calling MCP tool: {tool_name} with args: {kwargs}")
        
        # 模拟返回
        if tool_name == 'store':
            return {"success": True, "id": "mock-id-123"}
        elif tool_name == 'search':
            return []
        elif tool_name == 'aggregate':
            return {"result": 0}
        else:
            return {"success": True}
    
    async def check_and_send_reminders(self) -> List[Dict[str, Any]]:
        """
        检查并发送到期的提醒
        """
        sent_reminders = []
        
        try:
            # 获取所有用户
            for user_id in settings.ALLOWED_USERS:
                # 获取待发送提醒
                reminders = await self._call_mcp_tool(
                    'get_pending_reminders',
                    user_id=user_id
                )
                
                for reminder in reminders:
                    # 发送提醒（需要集成Threema）
                    # TODO: 实际发送
                    logger.info(f"Sending reminder to {user_id}: {reminder['content']}")
                    
                    # 标记为已发送
                    await self._call_mcp_tool(
                        'mark_reminder_sent',
                        reminder_id=reminder['reminder_id']
                    )
                    
                    sent_reminders.append({
                        'user_id': user_id,
                        'reminder': reminder
                    })
        
        except Exception as e:
            logger.error(f"Error checking reminders: {e}")
        
        return sent_reminders 