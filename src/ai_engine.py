"""
AI驱动的核心引擎 - 让AI决定一切
"""
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import openai
import structlog
import httpx
import os

from .core.config import settings

logger = structlog.get_logger(__name__)

# 家庭AI助手的系统提示词
FAMILY_AI_SYSTEM_PROMPT = """
你是一个贴心的家庭AI助手，专门服务于一个有3个孩子的家庭。

你的核心能力：
1. 记账管理：识别并记录家庭收支，提供统计分析和预算建议
2. 健康追踪：记录家人健康数据（身高、体重、疫苗等），跟踪变化趋势
3. 杂事提醒：管理日常事务，及时提醒重要事项

回复原则：
- 温馨友好，像家人般关怀
- 简洁实用，不说废话
- 主动提供有价值的统计和建议
- 记住这是一个有3个孩子的家庭，关注育儿相关需求

信息理解指南：
- "今天/昨天/上周"等时间表达要转换为具体日期
- 识别家庭成员：儿子、女儿（大女儿、二女儿）、妻子、我/老公
- 支出自动分类：餐饮、购物、交通、医疗、教育、日用品等
- 如果提到"更新"或"改为"，要覆盖之前的记录

你有以下工具可以使用：
- store: 存储任何重要信息（支出、收入、健康数据、杂事等）
- search: 查找历史记录
- aggregate: 统计分析数据（求和、计数、平均值等）
- schedule_reminder: 设置提醒
- get_pending_reminders: 查看待发送提醒
- mark_reminder_sent: 标记提醒已发送
"""


class AIEngine:
    def __init__(self):
        self.openai_client = openai.AsyncClient(api_key=settings.OPENAI_API_KEY)
        self.mcp_client = None
        self.mcp_url = os.getenv('MCP_SERVER_URL', 'http://faa-mcp:8000')
        
    async def initialize_mcp(self):
        """初始化MCP客户端连接"""
        try:
            # 暂时使用HTTP调用方式，而不是stdio
            # 这样更简单且适合容器化部署
            logger.info(f"Connecting to MCP server at {self.mcp_url}")
            
            # 测试连接
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.mcp_url}/health", timeout=5.0)
                if response.status_code == 200:
                    logger.info("MCP server is healthy")
                    self.mcp_client = True  # 标记为可用
                else:
                    logger.warning(f"MCP server health check failed: {response.status_code}")
            
        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {e}")
            logger.warning("Falling back to mock MCP mode")
            self.mcp_client = None
    
    async def close(self):
        """关闭MCP客户端连接"""
        # HTTP客户端无需特殊关闭
        pass
    
    async def process_message(self, content: str, user_id: str, context: Dict[str, Any] = None) -> str:
        """
        处理用户消息 - 完全由AI驱动
        
        Args:
            content: 消息内容（已解密的文本）
            user_id: 用户ID
            context: 消息上下文（channel、sender_id等，让AI理解）
        """
        try:
            # 第一步：理解用户意图和提取信息
            understanding = await self._understand_message(content, user_id, context)
            
            # 第二步：执行必要的操作
            result = await self._execute_actions(understanding, user_id)
            
            # 第三步：生成回复
            response = await self._generate_response(content, understanding, result, context)
            
            return response
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return "抱歉，处理您的消息时出现了错误。"
    
    async def _understand_message(self, content: str, user_id: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        AI理解消息内容 - 增强版
        """
        # 构建上下文信息
        context_info = ""
        if context:
            context_info = f"\n消息来源：{context.get('channel', '未知')}"
            if context.get('sender_id'):
                context_info += f"\n发送者ID：{context['sender_id']}"
            if context.get('nickname'):
                context_info += f"\n发送者昵称：{context['nickname']}"
        
        # 获取当前时间用于时间理解
        current_time = datetime.now()
        
        prompt = f"""
        分析用户消息并提取所有相关信息。
        
        当前时间：{current_time.isoformat()}
        用户消息：{content}
        {context_info}
        
        请分析并返回JSON格式的理解结果，包括但不限于：
        1. intent: 用户意图（record_expense/record_income/record_health/query/set_reminder/update_info/general_chat等）
        2. entities: 提取的实体信息
        3. need_action: 是否需要执行动作
        4. suggested_actions: 建议的动作列表
        5. original_content: 原始消息内容（用于存储）
        
        时间理解规则：
        - "今天" = {current_time.date()}
        - "昨天" = {(current_time - datetime.timedelta(days=1)).date()}
        - "前天" = {(current_time - datetime.timedelta(days=2)).date()}
        - "上周X" = 计算具体日期
        - "这个月" = {current_time.strftime('%Y-%m')}
        - "上个月" = 计算具体月份
        
        财务相关提取：
        - amount: 金额（数字）
        - type: expense（支出）/income（收入）
        - category: 自动分类（餐饮/购物/交通/医疗/教育/日用品/娱乐/其他）
        - description: 具体描述
        
        健康相关提取：
        - person: 家庭成员（儿子/大女儿/二女儿/妻子/我）
        - metric: 指标（身高/体重/体温/疫苗/症状等）
        - value: 数值
        - unit: 单位
        
        提醒相关提取：
        - remind_content: 提醒内容
        - remind_time: 提醒时间（转换为ISO格式）
        - repeat: 重复模式（daily/weekly/monthly/once）
        
        信息更新识别：
        - 如果包含"改为"、"更新"、"现在是"等词汇，设置 update_existing: true
        - 提取要更新的信息类型和新值
        
        请提取所有你认为重要的信息，occurred_at字段必须是具体的ISO格式时间。
        """
        
        response = await self.openai_client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": FAMILY_AI_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.3
        )
        
        understanding = json.loads(response.choices[0].message.content)
        understanding['original_content'] = content
        logger.info(f"Message understanding: {understanding}")
        
        return understanding
    
    async def _execute_actions(self, understanding: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """
        根据理解结果执行动作 - 增强版，自动进行相关统计
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
            
            # 如果是财务记录，自动进行本月统计
            if intent in ['record_expense', 'record_income'] and entities.get('amount'):
                # 获取本月的日期范围
                now = datetime.now()
                month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                
                # 统计本月该类别的总额
                category = entities.get('category', '其他')
                filters = {
                    'date_from': month_start.isoformat(),
                    'date_to': now.isoformat()
                }
                
                # 搜索本月同类记录
                search_result = await self._call_mcp_tool(
                    'search',
                    query=f"{category} {intent}",
                    user_id=user_id,
                    filters=filters
                )
                
                # 聚合统计
                agg_result = await self._call_mcp_tool(
                    'aggregate',
                    user_id=user_id,
                    operation='sum',
                    field='amount',
                    filters=filters
                )
                
                result['actions_taken'].extend([
                    {'action': 'search', 'result': search_result},
                    {'action': 'aggregate', 'result': agg_result}
                ])
                
                # 如果需要，还可以统计今日总额
                if entities.get('occurred_at'):
                    occurred_date = datetime.fromisoformat(entities['occurred_at']).date()
                    if occurred_date == now.date():
                        today_filters = {
                            'date_from': now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
                            'date_to': now.isoformat()
                        }
                        
                        today_agg = await self._call_mcp_tool(
                            'aggregate',
                            user_id=user_id,
                            operation='sum',
                            field='amount',
                            filters=today_filters
                        )
                        
                        result['actions_taken'].append({
                            'action': 'aggregate',
                            'result': {'operation': 'sum', 'period': 'today', 'result': today_agg.get('result', 0)}
                        })
            
            # 如果是健康记录，查找同一人的历史数据
            elif intent == 'record_health' and entities.get('person'):
                person = entities['person']
                metric = entities.get('metric', '')
                
                # 搜索该家庭成员的历史健康数据
                search_result = await self._call_mcp_tool(
                    'search',
                    query=f"{person} {metric}",
                    user_id=user_id,
                    filters=None
                )
                
                result['actions_taken'].append({
                    'action': 'search',
                    'result': search_result
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
            
            # 智能识别查询时间范围
            query_text = entities.get('query_text', '')
            if '本月' in query_text or '这个月' in query_text:
                now = datetime.now()
                filters['date_from'] = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
                filters['date_to'] = now.isoformat()
            elif '今天' in query_text or '今日' in query_text:
                now = datetime.now()
                filters['date_from'] = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
                filters['date_to'] = now.isoformat()
            elif '昨天' in query_text:
                yesterday = datetime.now() - timedelta(days=1)
                filters['date_from'] = yesterday.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
                filters['date_to'] = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
            
            # 添加其他过滤条件
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
            if entities.get('need_aggregation') or any(word in query_text for word in ['总共', '总计', '多少钱', '统计']):
                # 判断聚合类型
                operation = 'sum'  # 默认求和
                if '平均' in query_text:
                    operation = 'avg'
                elif '次数' in query_text or '几次' in query_text:
                    operation = 'count'
                
                agg_result = await self._call_mcp_tool(
                    'aggregate',
                    user_id=user_id,
                    operation=operation,
                    field='amount' if operation != 'count' else None,
                    filters=filters if filters else None
                )
                result['actions_taken'].append({
                    'action': 'aggregate',
                    'result': agg_result
                })
        
        # 信息更新操作
        elif intent == 'update_info' and entities.get('update_existing'):
            # 先搜索要更新的记录
            search_query = entities.get('update_target', '')
            search_result = await self._call_mcp_tool(
                'search',
                query=search_query,
                user_id=user_id,
                filters={'limit': 1}  # 只获取最新的一条
            )
            
            # 存储新信息（AI会在回复中说明这是更新）
            ai_data = {
                'intent': 'update',
                'previous_record': search_result[0] if search_result else None,
                'entities': entities,
                'timestamp': datetime.now().isoformat()
            }
            ai_data.update(entities)
            
            store_result = await self._call_mcp_tool(
                'store',
                content=f"[更新] {understanding.get('original_content', '')}",
                ai_data=ai_data,
                user_id=user_id
            )
            
            result['actions_taken'].extend([
                {'action': 'search', 'result': search_result},
                {'action': 'store', 'result': store_result}
            ])
        
        return result
    
    async def _generate_response(self, original_message: str, understanding: Dict[str, Any], execution_result: Dict[str, Any], context: Dict[str, Any] = None) -> str:
        """
        生成自然语言回复 - 增强版，提供统计和建议
        """
        # 构建执行结果的详细描述
        actions_summary = []
        search_results = []
        aggregation_results = {}
        
        for action in execution_result.get('actions_taken', []):
            action_type = action['action']
            result = action['result']
            
            if action_type == 'store' and result.get('success'):
                actions_summary.append("✓ 已记录")
            elif action_type == 'schedule_reminder' and result.get('success'):
                actions_summary.append("✓ 已设置提醒")
            elif action_type == 'search' and isinstance(result, list):
                search_results = result
            elif action_type == 'aggregate' and 'result' in result:
                aggregation_results[result.get('operation', 'sum')] = result['result']
        
        # 构建渠道特定的提示
        channel_hint = ""
        if context and context.get('channel') == 'threema':
            channel_hint = "\n注意：通过Threema回复，保持简洁友好，使用表情符号增加亲和力。"
        
        # 构建系统提示
        system_prompt = FAMILY_AI_SYSTEM_PROMPT + f"""

当前任务：基于用户消息和执行结果，生成一个有价值的回复。

回复要求：
1. 确认已完成的操作（{', '.join(actions_summary) if actions_summary else '无操作'}）
2. 如果记录了支出/收入，自动提供本月/今日累计
3. 如果是查询，用简洁的方式展示结果
4. 根据家庭历史数据，提供个性化建议
5. 如果发现异常模式（如超支），温和提醒
6. 使用温暖、像家人般的语气
{channel_hint}

记住这是一个有3个孩子的家庭，可能关注：
- 育儿支出和健康
- 家庭预算管理
- 日常生活便利性
"""
        
        # 准备详细的上下文信息
        detailed_context = {
            "用户消息": original_message,
            "理解结果": understanding,
            "执行情况": actions_summary,
            "查询结果数量": len(search_results) if search_results else 0,
            "统计结果": aggregation_results
        }
        
        # 如果有搜索结果，添加摘要
        if search_results:
            detailed_context["最近记录示例"] = [
                {"内容": r.get('content', ''), "金额": r.get('amount')} 
                for r in search_results[:3]
            ]
        
        prompt = f"""
基于以下信息生成回复：

{json.dumps(detailed_context, ensure_ascii=False, indent=2)}

请生成一个符合要求的回复。如果是财务相关，考虑：
- 本月总支出是否异常？
- 某类支出是否过高？
- 是否需要预算提醒？

如果是健康相关，考虑：
- 成长趋势是否正常？
- 是否到了疫苗接种时间？
- 是否需要健康建议？

如果是提醒相关：
- 确认提醒的具体时间
- 如果是重复提醒，说明频率

回复示例风格：
- "已经帮您记下了！今天买菜花了58元，本月买菜已支出523元，比上月同期增加了20%。💡小建议：可以考虑多买些应季蔬菜，既新鲜又实惠。"
- "记录成功！儿子现在身高90cm，比上个月长高了2cm，成长曲线很棒！📈 下次体检时间是下个月15号。"
- "好的，我会在明天上午9点提醒您给二女儿打疫苗。已添加到提醒列表中。"
"""
        
        response = await self.openai_client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        generated_response = response.choices[0].message.content
        
        # 后处理：确保回复不会太长
        if len(generated_response) > 500 and context and context.get('channel') == 'threema':
            # 对于Threema，截断过长的消息
            generated_response = generated_response[:497] + "..."
        
        return generated_response
    
    async def _call_mcp_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """
        调用MCP工具 - 使用真实客户端或回退到模拟
        """
        logger.info(f"Calling MCP tool: {tool_name} with args: {kwargs}")
        
        # 如果有真实的MCP客户端
        if self.mcp_client:
            try:
                # 使用httpx进行HTTP调用
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.mcp_url}/tool/{tool_name}",
                        json=kwargs,
                        timeout=10.0
                    )
                    response.raise_for_status() # 检查HTTP状态码
                    return response.json()
            except httpx.RequestError as e:
                logger.error(f"HTTP request to MCP tool failed: {e}")
                # 回退到模拟模式
        
        # 模拟模式（用于开发和测试）
        if tool_name == 'store':
            return {"success": True, "id": f"mock-{datetime.now().timestamp()}"}
        elif tool_name == 'search':
            # 模拟一些搜索结果
            if "本月" in str(kwargs.get('query', '')):
                return [
                    {"content": "买菜花了50元", "amount": 50, "occurred_at": datetime.now().isoformat()},
                    {"content": "打车花了30元", "amount": 30, "occurred_at": datetime.now().isoformat()}
                ]
            return []
        elif tool_name == 'aggregate':
            # 模拟聚合结果
            if kwargs.get('operation') == 'sum':
                return {"operation": "sum", "field": "amount", "result": 523.5}
            return {"result": 0}
        elif tool_name == 'get_pending_reminders':
            # 模拟待发送提醒
            return []
        else:
            return {"success": True}
    
    async def check_and_send_reminders(self, send_callback) -> List[Dict[str, Any]]:
        """
        检查并发送到期的提醒 - 改进版
        """
        sent_reminders = []
        
        try:
            # 从数据库获取所有活跃用户
            from .db.database import get_db
            async with get_db() as db:
                # 获取所有有 Threema 渠道的用户
                user_rows = await db.fetch(
                    """
                    SELECT DISTINCT u.id as user_id
                    FROM users u
                    JOIN user_channels uc ON u.id = uc.user_id
                    WHERE uc.channel = 'threema'
                    """
                )
                
                for row in user_rows:
                    user_id = str(row['user_id'])
                    
                    # 获取该用户的待发送提醒
                    reminders = await self._call_mcp_tool(
                        'get_pending_reminders',
                        user_id=user_id
                    )
                    
                    for reminder in reminders:
                        # 构建提醒消息
                        reminder_content = reminder.get('content', '您设置的提醒')
                        ai_understanding = reminder.get('ai_understanding', {})
                        remind_detail = ai_understanding.get('remind_content', reminder_content)
                        
                        reminder_text = f"⏰ 提醒：{remind_detail}\n"
                        if ai_understanding.get('repeat') == 'daily':
                            reminder_text += "（每日提醒）"
                        
                        # 发送提醒
                        success = await send_callback(user_id, reminder_text)
                        
                        if success:
                            # 标记为已发送
                            await self._call_mcp_tool(
                                'mark_reminder_sent',
                                reminder_id=reminder['reminder_id']
                            )
                            
                            sent_reminders.append({
                                'user_id': user_id,
                                'reminder': reminder,
                                'sent': True
                            })
                            
                            logger.info(f"Sent reminder to user {user_id}: {remind_detail}")
                        else:
                            logger.error(f"Failed to send reminder {reminder['reminder_id']} to {user_id}")
                            
        except Exception as e:
            logger.error(f"Error in reminder task: {e}")
        
        return sent_reminders 