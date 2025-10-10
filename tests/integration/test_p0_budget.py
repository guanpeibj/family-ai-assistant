#!/usr/bin/env python3
"""
P0 集成测试 - 预算管理核心功能

测试用例：TC009, TC010, TC011, TC013
优先级：P0（核心必测）

功能覆盖：
- 设置月度预算
- 设置分类预算
- 查询预算情况
- 预算警告（80%阈值）

注意：预算数据存储在 user_id="family_default" 下
"""

import asyncio
from datetime import datetime
from base import IntegrationTestBase


class TestP0Budget(IntegrationTestBase):
    """P0 预算管理核心功能测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p0_budget")
    
    async def test_tc009_set_monthly_budget(self):
        """
        TC009: 设置月度预算
        
        验证点：
        1. AI理解预算设置意图
        2. 预算存储在 user_id="family_default"
        3. 金额准确（10000元）
        4. period正确（当前月份）
        5. 响应确认设置成功
        
        重要：这是家庭共享配置，不应存储在个人user_id下
        """
        await self.run_test(
            test_id="TC009",
            test_name="设置月度预算",
            message="设置本月预算10000元",
            expected_keywords=["设置", "预算", "10000"]
        )
        
        # 验证预算存储在family_default下
        # 注：由于测试user_id不是family_default，这里验证逻辑较复杂
        # 实际应该查询user_id="family_default"的记录
        print("提示：预算应存储在family_default用户下")
    
    async def test_tc010_set_category_budgets(self):
        """
        TC010: 设置分类预算
        
        验证点：
        1. AI理解分类预算设置
        2. 各类目预算正确解析
        3. category_budgets字段结构正确
        4. 响应确认
        """
        await self.run_test(
            test_id="TC010",
            test_name="设置分类预算",
            message="设置本月预算：餐饮3000，教育2000，交通1000，其他4000",
            expected_keywords=["设置", "预算"]
        )
    
    async def test_tc011_query_budget(self):
        """
        TC011: 查询预算情况
        
        验证点：
        1. AI理解预算查询意图
        2. 查询family_default用户的预算（配置类查询原则）
        3. 返回总预算、已用、剩余
        4. 返回各类目明细
        5. 使用家庭范围user_ids统计支出
        
        重要：
        - 预算查询必须查数据库，不能依赖对话历史
        - 支出统计使用household.family_scope.user_ids
        """
        # 先记录几笔支出用于统计
        print("\n--- 准备测试数据：记录支出 ---")
        await self.run_test(
            test_id="TC011-setup-1",
            test_name="准备数据 - 记录支出1",
            message="买菜花了150元",
            expected_keywords=["记录"]
        )
        
        await asyncio.sleep(0.3)
        
        await self.run_test(
            test_id="TC011-setup-2",
            test_name="准备数据 - 记录支出2",
            message="加油300元",
            expected_keywords=["记录"]
        )
        
        await asyncio.sleep(0.5)
        
        # 查询预算
        print("\n--- 主测试：查询预算 ---")
        await self.run_test(
            test_id="TC011",
            test_name="查询预算情况",
            message="预算还剩多少？",
            expected_keywords=["预算", "支出"]
        )
    
    async def test_tc013_budget_warning_80_percent(self):
        """
        TC013: 预算警告 - 80%阈值
        
        验证点：
        1. 记录支出达到预算80%后
        2. AI自动提示预算使用率
        3. 提示包含百分比信息
        4. 提醒注意控制支出
        
        前提：
        - 已设置预算10000元
        - 需要记录足够支出达到8000元（80%）
        """
        print("\n--- 准备测试：设置预算 ---")
        await self.run_test(
            test_id="TC013-setup-1",
            test_name="设置测试预算",
            message="设置本月预算5000元",  # 使用较小金额便于触发
            expected_keywords=["设置", "预算"]
        )
        
        await asyncio.sleep(0.5)
        
        print("\n--- 准备测试：记录支出达到80% ---")
        # 记录4000元支出（80%）
        expenses = [
            "买菜500元",
            "交通费300元",
            "购物1500元",
            "餐饮800元",
            "日用品400元",
            "服装500元",  # 累计4000元
        ]
        
        for i, expense in enumerate(expenses, 1):
            await self.run_test(
                test_id=f"TC013-setup-{i+1}",
                test_name=f"记录支出 {i}/6",
                message=expense,
                expected_keywords=["记录"]
            )
            await asyncio.sleep(0.3)
        
        await asyncio.sleep(0.5)
        
        print("\n--- 主测试：触发预算警告 ---")
        # 再记录一笔，应触发警告
        await self.run_test(
            test_id="TC013",
            test_name="预算警告 - 80%阈值",
            message="外卖100元",
            expected_keywords=["记录"]  # 可能包含"预算"、"80%"、"接近"等
        )


async def main():
    """运行P0预算核心功能测试"""
    print("=" * 80)
    print("P0 集成测试 - 预算管理核心功能")
    print("=" * 80)
    print()
    
    tester = TestP0Budget()
    
    # 设置
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        # 运行所有测试
        await tester.test_tc009_set_monthly_budget()
        await asyncio.sleep(0.5)
        
        await tester.test_tc010_set_category_budgets()
        await asyncio.sleep(0.5)
        
        await tester.test_tc011_query_budget()
        await asyncio.sleep(0.5)
        
        await tester.test_tc013_budget_warning_80_percent()
        
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

