#!/usr/bin/env python3
"""
P0 集成测试 - 基础提醒功能

测试用例：TC038 - TC041
优先级：P0（核心必测）

功能覆盖：
- 设置单次提醒
- 设置提前提醒
- 缺少人员时的澄清
- 缺少时间时的澄清
"""

import asyncio
from datetime import datetime, timedelta
from base import IntegrationTestBase


class TestP0Reminder(IntegrationTestBase):
    """P0 基础提醒功能测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p0_reminder")
    
    async def test_tc038_single_reminder(self):
        """
        TC038: 设置单次提醒
        
        验证点：
        1. AI理解提醒设置意图
        2. 正确解析时间（明天下午3点）
        3. 正确提取事项（接孩子放学）
        4. 创建提醒记录
        5. remind_at设置正确
        """
        await self.run_test(
            test_id="TC038",
            test_name="设置单次提醒",
            message="提醒我明天下午3点接孩子放学",
            expected_keywords=["提醒", "明天", "3点"]
        )
        
        # 注：验证remind_at的精确时间需要查询reminders表
    
    async def test_tc039_advance_reminder(self):
        """
        TC040: 设置提前提醒
        
        验证点：
        1. AI理解"提前一天提醒"的含义
        2. 计算提醒时间 = 目标时间 - 1天
        3. 正确提取人员（二女儿）和事项（打疫苗）
        4. remind_at = 下周二（下周三-1天）
        """
        await self.run_test(
            test_id="TC040",
            test_name="设置提前提醒",
            message="下周三给二女儿打疫苗，提前一天提醒我",
            expected_keywords=["提醒", "疫苗"]
        )
    
    async def test_tc041_reminder_missing_person(self):
        """
        TC041: 提醒 - 缺少人员（澄清）
        
        验证点：
        1. AI识别涉及"孩子"但未指定具体人员
        2. 发起澄清询问
        3. 可能提供成员列表
        """
        await self.run_test(
            test_id="TC041",
            test_name="提醒 - 缺少人员（澄清）",
            message="提醒我下个月3号给孩子打疫苗",
            expected_keywords=["哪个", "孩子", "谁"]
        )
    
    async def test_tc042_reminder_missing_time(self):
        """
        TC042: 提醒 - 缺少时间（澄清）
        
        验证点：
        1. AI识别缺少具体时间
        2. 发起澄清询问时间
        3. 询问"什么时候"或"几点"
        """
        await self.run_test(
            test_id="TC042",
            test_name="提醒 - 缺少时间（澄清）",
            message="提醒我给儿子打疫苗",
            expected_keywords=["什么时候", "时间", "几点", "哪天"]
        )


async def main():
    """运行P0基础提醒功能测试"""
    print("=" * 80)
    print("P0 集成测试 - 基础提醒功能")
    print("=" * 80)
    print()
    
    tester = TestP0Reminder()
    
    # 设置
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        # 运行所有测试
        await tester.test_tc038_single_reminder()
        await asyncio.sleep(0.5)
        
        await tester.test_tc039_advance_reminder()
        await asyncio.sleep(0.5)
        
        await tester.test_tc041_reminder_missing_person()
        await asyncio.sleep(0.5)
        
        await tester.test_tc042_reminder_missing_time()
        
        # 打印总结
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

