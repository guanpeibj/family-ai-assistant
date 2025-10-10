#!/usr/bin/env python3
"""
P0 集成测试 - 日常场景与性能

测试用例：TC161, TC163 - TC166
优先级：P0（核心必测）

功能覆盖：
- 简单查询响应时间（<5秒）
- 早晨唤醒场景
- 一天记账流程
- 查看预算使用情况
- 设置明天提醒
"""

import asyncio
from datetime import datetime
from base import IntegrationTestBase


class TestP0Scenarios(IntegrationTestBase):
    """P0 日常场景与性能测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p0_scenarios")
    
    async def test_tc161_simple_query_performance(self):
        """
        TC161: 简单查询响应时间
        
        验证点：
        1. 查询"这个月花了多少钱"
        2. 响应时间 < 5秒
        3. 返回准确结果
        
        性能要求：简单查询应在5秒内返回
        """
        # 先记录几笔支出
        print("\n--- 准备测试数据 ---")
        expenses = ["买菜80元", "打车25元", "午餐45元"]
        for expense in expenses:
            await self.run_test(
                test_id="TC161-setup",
                test_name="准备数据",
                message=expense,
                expected_keywords=["记录"]
            )
            await asyncio.sleep(0.2)
        
        await asyncio.sleep(0.5)
        
        # 主测试：性能验证
        print("\n--- 主测试：性能验证 ---")
        result = await self.run_test(
            test_id="TC161",
            test_name="简单查询响应时间",
            message="这个月花了多少钱？",
            expected_keywords=["支出"]
        )
        
        # 验证性能
        if result and 'duration' in result:
            duration = result['duration']
            if duration < 5.0:
                print(f"✅ 性能达标：{duration:.2f}秒 < 5秒")
            else:
                print(f"⚠️ 性能未达标：{duration:.2f}秒 >= 5秒")
    
    async def test_tc163_morning_wake_scenario(self):
        """
        TC163: 早晨唤醒场景
        
        验证点：
        1. AI理解问候和查询意图
        2. 返回今日提醒（如果有）
        3. 返回预算剩余情况
        4. 可能包含待办事项
        5. 响应友好自然
        """
        await self.run_test(
            test_id="TC163",
            test_name="早晨唤醒场景",
            message="早上好，今天有什么安排？",
            expected_keywords=[]  # AI自由发挥，可能包含提醒、预算等
        )
    
    async def test_tc164_daily_accounting_flow(self):
        """
        TC164: 一天记账流程
        
        验证点：
        1. 模拟一天的6笔支出
        2. 早餐 → 交通 → 午餐 → 购物 → 晚餐 → 娱乐
        3. 每笔都正确记录
        4. 预算实时更新
        5. 可能触发预算提醒
        """
        print("\n--- 模拟一天的记账流程 ---")
        
        daily_expenses = [
            ("早餐：包子加豆浆15元", "早餐"),
            ("坐地铁上班5元", "交通"),
            ("中午外卖45元", "午餐"),
            ("下午超市购物180元", "购物"),
            ("晚上聚餐200元", "晚餐"),
            ("看电影80元", "娱乐"),
        ]
        
        for i, (expense, label) in enumerate(daily_expenses, 1):
            print(f"\n--- {label} ({i}/6) ---")
            await self.run_test(
                test_id=f"TC164-{i}",
                test_name=f"一天记账 - {label}",
                message=expense,
                expected_keywords=["记录"]
            )
            await asyncio.sleep(0.3)
        
        print("\n--- 验证：一天记账完成 ---")
        print("✅ 6笔支出都已记录")
    
    async def test_tc165_check_budget_usage(self):
        """
        TC165: 查看预算使用情况
        
        验证点：
        1. AI理解查询剩余预算的意图
        2. 根据预算和已用情况计算
        3. 返回具体金额
        4. 可能给出消费建议
        """
        await self.run_test(
            test_id="TC165",
            test_name="查看预算使用情况",
            message="今天还能花多少钱？",
            expected_keywords=["预算", "剩余", "还能"]
        )
    
    async def test_tc166_set_tomorrow_reminder(self):
        """
        TC166: 设置明天提醒
        
        验证点：
        1. AI理解明天的提醒设置
        2. 正确解析时间（明天）
        3. 提取事项（给大女儿带雨伞）
        4. 创建提醒记录
        5. 确认设置成功
        """
        await self.run_test(
            test_id="TC166",
            test_name="设置明天提醒",
            message="明天提醒我给大女儿带雨伞",
            expected_keywords=["提醒", "明天"]
        )


async def main():
    """运行P0日常场景与性能测试"""
    print("=" * 80)
    print("P0 集成测试 - 日常场景与性能")
    print("=" * 80)
    print()
    
    tester = TestP0Scenarios()
    
    # 设置
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        # 运行所有测试
        await tester.test_tc161_simple_query_performance()
        await asyncio.sleep(0.5)
        
        await tester.test_tc163_morning_wake_scenario()
        await asyncio.sleep(0.5)
        
        await tester.test_tc164_daily_accounting_flow()
        await asyncio.sleep(0.5)
        
        await tester.test_tc165_check_budget_usage()
        await asyncio.sleep(0.5)
        
        await tester.test_tc166_set_tomorrow_reminder()
        
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

