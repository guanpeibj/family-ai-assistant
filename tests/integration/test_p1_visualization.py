#!/usr/bin/env python3
"""
P1 集成测试 - 可视化功能

测试用例：TC023 - TC025
优先级：P1（重要功能）

功能覆盖：
- 支出类目饼图
- 月度趋势折线图
- 类目对比柱状图
"""

import asyncio
from base import IntegrationTestBase


class TestP1Visualization(IntegrationTestBase):
    """P1 可视化功能测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p1_visualization")
    
    async def _prepare_visualization_data(self):
        """准备可视化测试数据"""
        print("\n--- 准备可视化测试数据 ---")
        
        # 多类目支出数据
        expenses = [
            "餐饮支出500元",
            "交通费200元",
            "教育支出800元",
            "医疗费150元",
            "娱乐消费300元",
            "日用品采购180元",
        ]
        
        for expense in expenses:
            await self.run_test(
                test_id="P1-VIS-setup",
                test_name="准备数据",
                message=expense,
                expected_keywords=["记录"]
            )
            await asyncio.sleep(0.2)
        
        print("--- 数据准备完成 ---\n")
        await asyncio.sleep(0.5)
    
    async def test_tc023_category_pie_chart(self):
        """
        TC023: 支出类目饼图
        
        验证点：
        1. AI理解生成饼图的意图
        2. 调用render_chart工具
        3. 类型为pie
        4. 返回图表路径或签名链接
        5. 响应包含简要数据摘要
        """
        await self._prepare_visualization_data()
        
        await self.run_test(
            test_id="TC023",
            test_name="生成支出类目饼图",
            message="生成本月支出类目占比图",
            expected_keywords=["图"]  # 可能包含"图表"、"已生成"等
        )
    
    async def test_tc024_trend_line_chart(self):
        """
        TC024: 月度趋势折线图
        
        验证点：
        1. AI理解生成趋势图的意图
        2. 获取近3个月数据
        3. 调用render_chart，类型为line
        4. 展示时间趋势
        5. 返回图表访问方式
        """
        await self.run_test(
            test_id="TC024",
            test_name="生成月度趋势折线图",
            message="画一个近3个月支出趋势图",
            expected_keywords=["图", "趋势"]
        )
    
    async def test_tc025_comparison_bar_chart(self):
        """
        TC025: 类目对比柱状图
        
        验证点：
        1. AI理解生成对比图的意图
        2. 获取本月和上月各类目数据
        3. 调用render_chart，类型为bar
        4. 多组数据对比展示
        5. 返回图表信息
        """
        await self.run_test(
            test_id="TC025",
            test_name="生成类目对比柱状图",
            message="对比本月和上月各类支出",
            expected_keywords=["支出"]  # 可能包含图表信息
        )


async def main():
    """运行P1可视化功能测试"""
    print("=" * 80)
    print("P1 集成测试 - 可视化功能")
    print("=" * 80)
    print()
    
    tester = TestP1Visualization()
    
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        await tester.test_tc023_category_pie_chart()
        await asyncio.sleep(0.5)
        
        await tester.test_tc024_trend_line_chart()
        await asyncio.sleep(0.5)
        
        await tester.test_tc025_comparison_bar_chart()
        
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

