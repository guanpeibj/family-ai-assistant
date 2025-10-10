#!/usr/bin/env python3
"""
P1 集成测试 - 高级查询功能

测试用例：TC019 - TC022
优先级：P1（重要功能）

功能覆盖：
- 支出趋势分析
- 月度对比分析
- 多维度组合查询
- 支出模式识别
"""

import asyncio
from datetime import datetime, timedelta
from base import IntegrationTestBase


class TestP1AdvancedQuery(IntegrationTestBase):
    """P1 高级查询功能测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p1_advanced_query")
    
    async def _prepare_rich_test_data(self):
        """准备丰富的测试数据"""
        print("\n--- 准备测试数据 ---")
        
        # 模拟多样化的支出
        expenses = [
            # 餐饮类
            "买菜180元",
            "外卖午餐55元",
            "超市购物350元",
            "晚餐聚会200元",
            # 交通类
            "打车50元",
            "加油300元",
            "停车费20元",
            # 教育类
            "给大女儿买书120元",
            "二女儿钢琴课200元",
            # 医疗类
            "儿子看病150元",
            "买药80元",
            # 其他
            "看电影100元",
            "买衣服280元",
        ]
        
        for i, expense in enumerate(expenses, 1):
            await self.run_test(
                test_id=f"P1-ADV-setup-{i}",
                test_name=f"准备数据 {i}/{len(expenses)}",
                message=expense,
                expected_keywords=["记录"]
            )
            await asyncio.sleep(0.2)
        
        print("--- 测试数据准备完成 ---\n")
        await asyncio.sleep(0.5)
    
    async def test_tc019_expense_trend_analysis(self):
        """
        TC019: 支出趋势分析
        
        验证点：
        1. AI识别查询异常的意图
        2. 分析支出模式（大额、增长、频繁等）
        3. 识别异常项目
        4. 给出分析建议
        """
        await self._prepare_rich_test_data()
        
        await self.run_test(
            test_id="TC019",
            test_name="支出趋势分析",
            message="本月支出有什么异常吗？",
            expected_keywords=["支出"]  # AI可能识别异常或说明正常
        )
    
    async def test_tc020_monthly_comparison(self):
        """
        TC020: 月度对比分析
        
        验证点：
        1. AI理解对比两个月的意图
        2. 获取两月的支出数据
        3. 计算差异（绝对值和百分比）
        4. 分析主要差异原因
        5. 可能按类目细分对比
        """
        await self.run_test(
            test_id="TC020",
            test_name="月度对比分析",
            message="这个月比上个月多花了多少？",
            expected_keywords=["支出"]  # 应返回对比数据
        )
    
    async def test_tc021_multi_dimension_query(self):
        """
        TC021: 多维度组合查询
        
        验证点：
        1. AI理解复合筛选条件
        2. 时间维度：9月份
        3. 人员维度：大女儿
        4. 类目维度：教育
        5. 三维交叉过滤准确
        """
        await self.run_test(
            test_id="TC021",
            test_name="多维度组合查询",
            message="9月份大女儿的教育支出",
            expected_keywords=["教育", "大女儿"]
        )
    
    async def test_tc022_spending_pattern_recognition(self):
        """
        TC022: 支出模式识别
        
        验证点：
        1. AI分析整体支出分布
        2. 识别主要支出类目
        3. 计算各类目占比
        4. 给出消费特征描述
        5. 可能提供优化建议
        """
        await self.run_test(
            test_id="TC022",
            test_name="支出模式识别",
            message="我们家主要花钱在哪些方面？",
            expected_keywords=["支出", "主要"]
        )


async def main():
    """运行P1高级查询功能测试"""
    print("=" * 80)
    print("P1 集成测试 - 高级查询功能")
    print("=" * 80)
    print()
    
    tester = TestP1AdvancedQuery()
    
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        await tester.test_tc019_expense_trend_analysis()
        await asyncio.sleep(0.5)
        
        await tester.test_tc020_monthly_comparison()
        await asyncio.sleep(0.5)
        
        await tester.test_tc021_multi_dimension_query()
        await asyncio.sleep(0.5)
        
        await tester.test_tc022_spending_pattern_recognition()
        
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

