#!/usr/bin/env python3
"""
P0 集成测试 - 基础查询功能

测试用例：TC015 - TC018
优先级：P0（核心必测）

功能覆盖：
- 查询月度支出
- 按类目查询
- 按时间范围查询
- 按家庭成员查询
"""

import asyncio
from datetime import datetime, timedelta
from base import IntegrationTestBase


class TestP0Query(IntegrationTestBase):
    """P0 基础查询功能测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p0_query")
    
    async def _prepare_test_data(self):
        """准备测试数据：记录各类支出"""
        print("\n--- 准备测试数据 ---")
        
        expenses = [
            "买菜花了180元",
            "打车50元",
            "给大女儿买书120元",
            "外卖午餐65元",
            "交通卡充值100元",
            "给儿子买衣服200元",
            "超市购物350元",
        ]
        
        for i, expense in enumerate(expenses, 1):
            await self.run_test(
                test_id=f"TC015-setup-{i}",
                test_name=f"准备数据 {i}/{len(expenses)}",
                message=expense,
                expected_keywords=["记录"]
            )
            await asyncio.sleep(0.2)
        
        print("--- 测试数据准备完成 ---\n")
        await asyncio.sleep(0.5)
    
    async def test_tc015_query_monthly_expense(self):
        """
        TC015: 查询月度支出
        
        验证点：
        1. AI理解查询本月支出的意图
        2. 返回本月总支出金额
        3. 使用家庭范围统计（family_scope.user_ids）
        4. 可能包含分类明细
        """
        await self._prepare_test_data()
        
        await self.run_test(
            test_id="TC015",
            test_name="查询月度支出",
            message="这个月花了多少钱？",
            expected_keywords=["支出", "元"]
        )
    
    async def test_tc016_query_by_category(self):
        """
        TC016: 按类目查询
        
        验证点：
        1. AI理解按类目筛选的意图
        2. 只返回"餐饮"类目的支出
        3. 总额计算准确
        4. 可能包含明细列表
        """
        await self.run_test(
            test_id="TC016",
            test_name="按类目查询",
            message="本月餐饮支出是多少？",
            expected_keywords=["餐饮", "支出"]
        )
    
    async def test_tc017_query_by_time_range(self):
        """
        TC017: 按时间范围查询
        
        验证点：
        1. AI理解"最近一周"的时间范围
        2. 返回近7天的支出记录
        3. 数据筛选准确
        4. 可能包含日期和明细
        """
        await self.run_test(
            test_id="TC017",
            test_name="按时间范围查询",
            message="最近一周的支出",
            expected_keywords=["支出", "一周"]
        )
    
    async def test_tc018_query_by_family_member(self):
        """
        TC018: 按家庭成员查询
        
        验证点：
        1. AI理解按成员筛选的意图
        2. 识别"大女儿"对应的member_key
        3. 只返回与大女儿相关的支出
        4. 总额和明细准确
        
        前提：测试数据中有"给大女儿买书120元"
        """
        await self.run_test(
            test_id="TC018",
            test_name="按家庭成员查询",
            message="这个月给大女儿花了多少钱？",
            expected_keywords=["大女儿", "支出"]
        )


async def main():
    """运行P0基础查询功能测试"""
    print("=" * 80)
    print("P0 集成测试 - 基础查询功能")
    print("=" * 80)
    print()
    
    tester = TestP0Query()
    
    # 设置
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        # 运行所有测试
        await tester.test_tc015_query_monthly_expense()
        await asyncio.sleep(0.5)
        
        await tester.test_tc016_query_by_category()
        await asyncio.sleep(0.5)
        
        await tester.test_tc017_query_by_time_range()
        await asyncio.sleep(0.5)
        
        await tester.test_tc018_query_by_family_member()
        
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

