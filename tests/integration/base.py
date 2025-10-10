"""
集成测试基础类

提供数据库隔离、测试工具方法等基础设施。
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import structlog

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.ai_engine import ai_engine
from src.db.database import async_session
from src.db.models import Memory, User, Reminder, Interaction
from sqlalchemy import select, delete

logger = structlog.get_logger(__name__)


class IntegrationTestBase:
    """
    集成测试基类
    
    功能：
    1. 数据库隔离（使用test_前缀的用户ID）
    2. 自动清理测试数据
    3. AI引擎初始化
    4. 通用验证方法
    """
    
    # 测试用户ID前缀，用于数据隔离
    TEST_USER_PREFIX = "test_user_integration_"
    
    def __init__(self, test_suite_name: str = "base"):
        """
        初始化测试基类
        
        Args:
            test_suite_name: 测试套件名称，用于生成唯一的用户ID
        """
        self.test_suite_name = test_suite_name
        self.test_user_id = f"{self.TEST_USER_PREFIX}{test_suite_name}"
        self.test_results = []
        self.setup_complete = False
        
    async def setup(self):
        """
        测试前初始化
        
        步骤：
        1. 初始化AI引擎和MCP服务
        2. 清理该测试套件的旧数据
        3. 创建测试用户（如果需要）
        """
        logger.info("test_setup_start", suite=self.test_suite_name)
        
        try:
            # 初始化AI引擎
            if not ai_engine._mcp_initialized:
                await ai_engine.initialize_mcp()
            
            # 清理旧的测试数据
            await self._cleanup_test_data()
            
            logger.info("test_setup_complete", suite=self.test_suite_name)
            self.setup_complete = True
            return True
            
        except Exception as e:
            logger.error("test_setup_failed", suite=self.test_suite_name, error=str(e))
            return False
    
    async def teardown(self):
        """
        测试后清理
        
        默认保留测试数据便于调试，如需清理可以调用cleanup()
        """
        logger.info("test_teardown", suite=self.test_suite_name, 
                   results_count=len(self.test_results))
    
    async def cleanup(self):
        """
        清理测试数据
        
        删除所有test_user_前缀的用户相关数据。
        警告：这会永久删除数据！
        """
        await self._cleanup_test_data()
        logger.info("test_data_cleaned", suite=self.test_suite_name)
    
    async def _cleanup_test_data(self):
        """
        内部方法：清理测试数据
        
        删除内容：
        - Memories (记忆)
        - Reminders (提醒)
        - Interactions (交互记录)
        
        注意：不删除Users表，因为可能有外键约束
        """
        try:
            async with async_session() as session:
                # 获取所有测试用户ID
                result = await session.execute(
                    select(User.id).where(User.id.like(f"{self.TEST_USER_PREFIX}%"))
                )
                test_user_ids = [row[0] for row in result.fetchall()]
                
                if test_user_ids:
                    # 删除memories
                    await session.execute(
                        delete(Memory).where(Memory.user_id.in_(test_user_ids))
                    )
                    
                    # 删除reminders
                    await session.execute(
                        delete(Reminder).where(Reminder.user_id.in_(test_user_ids))
                    )
                    
                    # 删除interactions
                    await session.execute(
                        delete(Interaction).where(Interaction.user_id.in_(test_user_ids))
                    )
                    
                    await session.commit()
                    
                    logger.info("test_data_cleanup_complete", 
                              user_count=len(test_user_ids),
                              suite=self.test_suite_name)
                    
        except Exception as e:
            logger.error("test_data_cleanup_failed", error=str(e))
    
    async def run_test(
        self, 
        test_id: str,
        test_name: str, 
        message: str,
        expected_keywords: Optional[List[str]] = None,
        expected_not_keywords: Optional[List[str]] = None,
        context: Optional[Dict] = None,
        verify_db: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        运行单个测试用例
        
        Args:
            test_id: 测试用例ID（如TC001）
            test_name: 测试名称
            message: 用户输入消息
            expected_keywords: 期望响应包含的关键词列表
            expected_not_keywords: 期望响应不包含的关键词列表
            context: 额外的上下文信息
            verify_db: 数据库验证函数，async callable，返回(success, message)
        
        Returns:
            测试结果字典，包含success, response, duration等
        """
        print()
        print("=" * 80)
        print(f"[{test_id}] {test_name}")
        print("=" * 80)
        print(f"输入：{message}")
        print()
        
        try:
            start_time = datetime.now()
            
            # 构建上下文
            test_context = {
                "channel": "api",
                "thread_id": f"test_thread_{self.test_suite_name}",
                **(context or {})
            }
            
            # 调用AI引擎
            response = await ai_engine.process_message(
                content=message,
                user_id=self.test_user_id,
                context=test_context
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            print("AI回复：")
            print(response)
            print()
            print(f"耗时：{duration:.2f}秒")
            
            # 验证关键词
            success = True
            issues = []
            
            if expected_keywords:
                for keyword in expected_keywords:
                    if keyword.lower() not in response.lower():
                        issues.append(f"缺少关键词：{keyword}")
                        success = False
            
            if expected_not_keywords:
                for keyword in expected_not_keywords:
                    if keyword.lower() in response.lower():
                        issues.append(f"不应包含关键词：{keyword}")
                        success = False
            
            # 数据库验证
            if verify_db:
                db_success, db_message = await verify_db()
                if not db_success:
                    issues.append(f"数据库验证失败：{db_message}")
                    success = False
            
            # 记录结果
            result = {
                "test_id": test_id,
                "test_name": test_name,
                "success": success,
                "duration": duration,
                "response": response,
                "response_length": len(response),
                "issues": issues
            }
            
            self.test_results.append(result)
            
            # 打印结果
            if success:
                print("✅ 测试通过")
            else:
                print("❌ 测试失败")
                for issue in issues:
                    print(f"   - {issue}")
            
            return result
            
        except Exception as e:
            logger.error("test_execution_failed", test_id=test_id, error=str(e))
            print(f"❌ 测试异常：{e}")
            
            result = {
                "test_id": test_id,
                "test_name": test_name,
                "success": False,
                "error": str(e)
            }
            
            self.test_results.append(result)
            return result
    
    async def verify_memory_exists(
        self, 
        filters: Dict[str, Any],
        min_count: int = 1
    ) -> tuple[bool, str]:
        """
        验证数据库中存在满足条件的记忆
        
        Args:
            filters: 过滤条件，如 {"type": "expense", "amount": 100}
            min_count: 最少应有的记录数
        
        Returns:
            (success, message) 元组
        """
        try:
            async with async_session() as session:
                query = select(Memory).where(Memory.user_id == self.test_user_id)
                
                # 应用JSONB过滤
                for key, value in filters.items():
                    if key in ['amount', 'occurred_at', 'created_at']:
                        # 直接列过滤
                        query = query.where(getattr(Memory, key) == value)
                    else:
                        # JSONB字段过滤
                        query = query.where(
                            Memory.ai_understanding[key].astext == str(value)
                        )
                
                result = await session.execute(query)
                memories = result.scalars().all()
                
                if len(memories) >= min_count:
                    return True, f"找到{len(memories)}条记录"
                else:
                    return False, f"只找到{len(memories)}条记录，期望至少{min_count}条"
                    
        except Exception as e:
            return False, f"数据库查询失败：{e}"
    
    async def get_latest_memory(self, memory_type: Optional[str] = None) -> Optional[Memory]:
        """
        获取最新的记忆记录
        
        Args:
            memory_type: 可选的类型过滤
        
        Returns:
            Memory对象或None
        """
        try:
            async with async_session() as session:
                query = select(Memory).where(
                    Memory.user_id == self.test_user_id
                ).order_by(Memory.created_at.desc())
                
                if memory_type:
                    query = query.where(
                        Memory.ai_understanding['type'].astext == memory_type
                    )
                
                result = await session.execute(query)
                return result.scalars().first()
                
        except Exception as e:
            logger.error("get_latest_memory_failed", error=str(e))
            return None
    
    def print_summary(self):
        """
        打印测试总结
        
        显示：
        - 总测试数、通过数、失败数
        - 平均耗时
        - 详细结果列表
        """
        print()
        print("=" * 80)
        print(f"测试总结 - {self.test_suite_name}")
        print("=" * 80)
        
        if not self.test_results:
            print("没有测试结果")
            return
        
        total = len(self.test_results)
        passed = sum(1 for r in self.test_results if r.get('success'))
        failed = total - passed
        
        print(f"总测试数：{total}")
        print(f"✅ 通过：{passed} ({passed/total*100:.1f}%)")
        print(f"❌ 失败：{failed} ({failed/total*100:.1f}%)")
        
        durations = [r.get('duration', 0) for r in self.test_results if 'duration' in r]
        if durations:
            avg_duration = sum(durations) / len(durations)
            print(f"平均耗时：{avg_duration:.2f}秒")
        
        print()
        print("详细结果：")
        for i, result in enumerate(self.test_results, 1):
            status = "✅" if result.get('success') else "❌"
            duration = result.get('duration', 0)
            test_id = result.get('test_id', 'N/A')
            test_name = result.get('test_name', 'Unknown')
            
            print(f"{i}. {status} [{test_id}] {test_name} ({duration:.2f}s)")
            
            if not result.get('success'):
                if 'error' in result:
                    print(f"   错误：{result['error']}")
                if 'issues' in result:
                    for issue in result['issues']:
                        print(f"   {issue}")
        
        print()
        
        return {
            'total': total,
            'passed': passed,
            'failed': failed,
            'pass_rate': passed / total if total > 0 else 0
        }

