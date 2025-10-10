#!/usr/bin/env python3
"""
P1 集成测试 - 月度场景

测试用例：TC361 - TC363
优先级：P1（重要功能）

功能覆盖：
- 月初查看上月报告
- 月初设置新月预算
- 月末预算检查
"""

import asyncio
from datetime import datetime
from base import IntegrationTestBase


class TestP1MonthlyScenarios(IntegrationTestBase):
    """P1 月度场景测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p1_monthly")
    
    async def _prepare_monthly_data(self):
        """准备月度测试数据"""
        print("\n--- 准备月度数据 ---")
        
        # 模拟上月数据
        expenses = [
            "餐饮3000元",
            "交通1000元",
            "教育2000元",
            "医疗800元",
            "娱乐600元",
            "居住2500元",
        ]
        
        for expense in expenses:
            await self.run_test(
                test_id="P1-MONTHLY-setup",
                test_name="准备数据",
                message=expense,
                expected_keywords=["记录"]
            )
            await asyncio.sleep(0.2)
        
        print("--- 数据准备完成 ---\n")
        await asyncio.sleep(0.5)
    
    async def test_tc361_monthly_report_generation(self):
        """
        TC361: 月初查看上月报告
        
        验证点：
        1. 查询上月数据
        2. 生成完整财务报告
        3. 包含：总览、分类、异常、建议
        4. 格式清晰易读
        5. 数据准确
        
        模拟场景：11月1日查询10月报告
        """
        await self._prepare_monthly_data()
        
        await self.run_test(
            test_id="TC361",
            test_name="月初查看上月报告",
            message="上个月财务报告",
            expected_keywords=["支出", "报告", "月"]
        )
    
    async def test_tc362_set_new_month_budget(self):
        """
        TC362: 月初设置新月预算
        
        验证点：
        1. 设置新月份预算
        2. 可以参考上月情况
        3. 设置分类预算
        4. 确认设置成功
        """
        await self.run_test(
            test_id="TC362",
            test_name="月初设置新月预算",
            message="设置11月预算12000元",
            expected_keywords=["设置", "预算", "12000"]
        )
    
    async def test_tc363_month_end_budget_check(self):
        """
        TC363: 月末预算检查
        
        验证点：
        1. 查询预算执行情况
        2. 返回使用率
        3. 剩余天数提示
        4. 预算剩余建议
        5. 提醒合理分配
        
        模拟场景：10月30日查询预算
        """
        # 先设置预算
        print("\n--- 设置本月预算 ---")
        await self.run_test(
            test_id="TC363-1",
            test_name="设置预算",
            message="设置本月预算10000元",
            expected_keywords=["设置", "预算"]
        )
        
        await asyncio.sleep(0.5)
        
        # 记录一些支出
        print("\n--- 记录支出 ---")
        await self.run_test(
            test_id="TC363-2",
            test_name="记录支出",
            message="餐饮支出2500元",
            expected_keywords=["记录"]
        )
        
        await asyncio.sleep(0.5)
        
        # 月末检查
        print("\n--- 月末预算检查 ---")
        await self.run_test(
            test_id="TC363",
            test_name="月末预算检查",
            message="预算执行情况",
            expected_keywords=["预算", "支出"]
        )


async def main():
    """运行P1月度场景测试"""
    print("=" * 80)
    print("P1 集成测试 - 月度场景")
    print("=" * 80)
    print()
    
    tester = TestP1MonthlyScenarios()
    
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        await tester.test_tc361_monthly_report_generation()
        await asyncio.sleep(0.5)
        
        await tester.test_tc362_set_new_month_budget()
        await asyncio.sleep(0.5)
        
        await tester.test_tc363_month_end_budget_check()
        
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

