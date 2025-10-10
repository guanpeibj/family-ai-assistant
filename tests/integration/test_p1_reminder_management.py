#!/usr/bin/env python3
"""
P1 集成测试 - 提醒管理功能

测试用例：TC241 - TC245
优先级：P1（重要功能）

功能覆盖：
- 查询即将到来的提醒
- 查询所有提醒
- 修改提醒时间
- 取消提醒
- 提醒完成标记
"""

import asyncio
from base import IntegrationTestBase


class TestP1ReminderManagement(IntegrationTestBase):
    """P1 提醒管理功能测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p1_reminder_mgmt")
    
    async def _setup_reminders(self):
        """创建几个提醒用于管理测试"""
        print("\n--- 创建测试提醒 ---")
        
        reminders = [
            "明天下午3点提醒我接大女儿放学",
            "后天提醒我给二女儿打疫苗",
            "下周一提醒我儿子复查",
        ]
        
        for reminder in reminders:
            await self.run_test(
                test_id="P1-REM-setup",
                test_name="创建提醒",
                message=reminder,
                expected_keywords=["提醒"]
            )
            await asyncio.sleep(0.3)
        
        print("--- 提醒创建完成 ---\n")
        await asyncio.sleep(0.5)
    
    async def test_tc241_query_upcoming_reminders(self):
        """
        TC241: 查询即将到来的提醒
        
        验证点：
        1. AI理解查询未来提醒的意图
        2. 筛选未来7天内的提醒
        3. 按时间排序
        4. 显示提醒内容和时间
        """
        await self._setup_reminders()
        
        await self.run_test(
            test_id="TC241",
            test_name="查询即将到来的提醒",
            message="最近有什么事要做？",
            expected_keywords=["提醒"]
        )
    
    async def test_tc242_query_all_reminders(self):
        """
        TC242: 查询所有提醒
        
        验证点：
        1. AI理解查询所有提醒的意图
        2. 返回所有未完成的提醒
        3. 包含详细信息
        4. 可能按类型或时间分组
        """
        await self.run_test(
            test_id="TC242",
            test_name="查询所有提醒",
            message="我设置了哪些提醒？",
            expected_keywords=["提醒"]
        )
    
    async def test_tc243_modify_reminder_time(self):
        """
        TC243: 修改提醒时间
        
        验证点：
        1. AI理解修改提醒的意图
        2. 定位到具体提醒（大女儿打疫苗）
        3. 更新时间为新日期（12号）
        4. 确认修改成功
        """
        await self.run_test(
            test_id="TC243",
            test_name="修改提醒时间",
            message="大女儿打疫苗改到12号",
            expected_keywords=["12号", "改", "修改"]
        )
    
    async def test_tc244_cancel_reminder(self):
        """
        TC244: 取消提醒
        
        验证点：
        1. AI理解取消提醒的意图
        2. 定位到具体提醒（儿子复查）
        3. 标记为已取消
        4. 确认取消成功
        """
        await self.run_test(
            test_id="TC244",
            test_name="取消提醒",
            message="取消儿子的复查提醒",
            expected_keywords=["取消", "儿子"]
        )
    
    async def test_tc245_mark_reminder_completed(self):
        """
        TC245: 提醒完成标记
        
        验证点：
        1. AI理解任务已完成的陈述
        2. 定位到相关提醒
        3. 标记为已完成
        4. 确认完成
        """
        await self.run_test(
            test_id="TC245",
            test_name="提醒完成标记",
            message="今天已经给大女儿打了疫苗",
            expected_keywords=["大女儿", "疫苗"]
        )


async def main():
    """运行P1提醒管理功能测试"""
    print("=" * 80)
    print("P1 集成测试 - 提醒管理功能")
    print("=" * 80)
    print()
    
    tester = TestP1ReminderManagement()
    
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        await tester.test_tc241_query_upcoming_reminders()
        await asyncio.sleep(0.5)
        
        await tester.test_tc242_query_all_reminders()
        await asyncio.sleep(0.5)
        
        await tester.test_tc243_modify_reminder_time()
        await asyncio.sleep(0.5)
        
        await tester.test_tc244_cancel_reminder()
        await asyncio.sleep(0.5)
        
        await tester.test_tc245_mark_reminder_completed()
        
        tester.print_summary()
        return 0
        
    except Exception as e:
        print(f"❌ 测试异常：{e}")
        return 1
        
    finally:
        await tester.teardown()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    import sys
    sys.exit(exit_code)

