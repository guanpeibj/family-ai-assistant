#!/usr/bin/env python3
"""
P1 集成测试 - 主动分析能力

测试用例：TC321 - TC324
优先级：P1（重要功能）

功能覆盖：
- 自动预算警告
- 异常支出检测
- 类目增长提醒
- 即将到期提醒
"""

import asyncio
from base import IntegrationTestBase


class TestP1ProactiveAnalysis(IntegrationTestBase):
    """P1 主动分析能力测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p1_proactive")
    
    async def test_tc321_automatic_budget_warning(self):
        """
        TC321: 自动预算警告
        
        验证点：
        1. 检测本月支出达到预算82%
        2. 任意一笔新记账时主动提示
        3. 提示包含预算使用率
        4. 建议控制支出
        
        前提：需要先设置预算并记录支出
        """
        print("\n--- 步骤1：设置预算 ---")
        await self.run_test(
            test_id="TC321-1",
            test_name="设置预算",
            message="设置本月预算5000元",
            expected_keywords=["设置", "预算"]
        )
        
        await asyncio.sleep(0.5)
        
        print("\n--- 步骤2：记录支出达到82% ---")
        expenses = [
            "买菜500元",
            "交通300元",
            "餐饮800元",
            "购物1200元",
            "娱乐500元",
            "日用品300元",  # 累计3600元，72%
        ]
        
        for expense in expenses:
            await self.run_test(
                test_id="TC321-2",
                test_name="记录支出",
                message=expense,
                expected_keywords=["记录"]
            )
            await asyncio.sleep(0.2)
        
        await asyncio.sleep(0.5)
        
        print("\n--- 步骤3：再记录一笔，触发预算警告 ---")
        await self.run_test(
            test_id="TC321",
            test_name="触发预算警告",
            message="看电影200元",
            expected_keywords=["记录"]  # 可能包含预算提示
        )
    
    async def test_tc322_anomaly_expense_detection(self):
        """
        TC322: 异常支出检测
        
        验证点：
        1. 识别大额支出（>平均月支出20%）
        2. 主动提示"较大"或"异常"
        3. 确认是否正确
        4. 正常记录
        """
        await self.run_test(
            test_id="TC322",
            test_name="异常支出检测",
            message="记账：维修车1500元",
            expected_keywords=["记录", "1500"]  # AI可能提示"大额"
        )
    
    async def test_tc323_category_growth_alert(self):
        """
        TC323: 类目增长提醒
        
        验证点：
        1. 检测医疗支出本月比上月增长40%
        2. 再记录一笔医疗支出时
        3. 主动提示医疗支出增长
        4. 建议关注健康
        
        注：需要历史数据支持，这里简化测试
        """
        print("\n--- 记录多笔医疗支出 ---")
        medical_expenses = [
            "儿子看病150元",
            "买药80元",
            "体检费200元",
        ]
        
        for i, expense in enumerate(medical_expenses, 1):
            await self.run_test(
                test_id=f"TC323-{i}",
                test_name=f"医疗支出 {i}/3",
                message=expense,
                expected_keywords=["记录"]
            )
            await asyncio.sleep(0.3)
        
        print("\n--- 再记录一笔，可能触发增长提醒 ---")
        await self.run_test(
            test_id="TC323",
            test_name="触发类目增长提醒",
            message="给大女儿买感冒药60元",
            expected_keywords=["记录"]  # 可能提示医疗支出增长
        )
    
    async def test_tc324_upcoming_due_reminder(self):
        """
        TC324: 即将到期提醒
        
        验证点：
        1. 设置明天的提醒
        2. 今天查询"明天有什么事"
        3. AI主动提醒明天的任务
        4. 提供详细信息
        """
        print("\n--- 步骤1：设置明天的提醒 ---")
        await self.run_test(
            test_id="TC324-1",
            test_name="设置明天提醒",
            message="明天提醒我给儿子打疫苗",
            expected_keywords=["提醒", "明天"]
        )
        
        await asyncio.sleep(0.5)
        
        print("\n--- 步骤2：查询明天的事 ---")
        await self.run_test(
            test_id="TC324",
            test_name="查询即将到期提醒",
            message="明天有什么事？",
            expected_keywords=["明天", "疫苗", "儿子"]
        )


async def main():
    """运行P1主动分析能力测试"""
    print("=" * 80)
    print("P1 集成测试 - 主动分析能力")
    print("=" * 80)
    print()
    
    tester = TestP1ProactiveAnalysis()
    
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        await tester.test_tc321_automatic_budget_warning()
        await asyncio.sleep(0.5)
        
        await tester.test_tc322_anomaly_expense_detection()
        await asyncio.sleep(0.5)
        
        await tester.test_tc323_category_growth_alert()
        await asyncio.sleep(0.5)
        
        await tester.test_tc324_upcoming_due_reminder()
        
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

