#!/usr/bin/env python3
"""
P1 集成测试 - 复杂查询能力

测试用例：TC301 - TC304
优先级：P1（重要功能）

功能覆盖：
- 多维度组合查询
- 趋势对比分析
- 假设性查询
- 推理性查询
"""

import asyncio
from base import IntegrationTestBase


class TestP1ComplexQuery(IntegrationTestBase):
    """P1 复杂查询能力测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p1_complex_query")
    
    async def _prepare_complex_data(self):
        """准备复杂查询所需数据"""
        print("\n--- 准备复杂测试数据 ---")
        
        # 多月份、多类目、多人员的数据
        records = [
            "给大女儿买教材120元",
            "二女儿钢琴课200元",
            "儿子游泳课150元",
            "家庭聚餐380元",
            "给大女儿买衣服180元",
            "儿子看病150元",
            "家庭旅游2000元",
        ]
        
        for record in records:
            await self.run_test(
                test_id="P1-COMPLEX-setup",
                test_name="准备数据",
                message=record,
                expected_keywords=["记录"]
            )
            await asyncio.sleep(0.2)
        
        print("--- 数据准备完成 ---\n")
        await asyncio.sleep(0.5)
    
    async def test_tc301_multi_dimension_query(self):
        """
        TC301: 多维度组合查询
        
        验证点：
        1. 时间范围：最近三个月
        2. 人员范围：孩子们（多人）
        3. 类目范围：教育
        4. 三维交叉筛选准确
        5. 结果展示清晰
        """
        await self._prepare_complex_data()
        
        await self.run_test(
            test_id="TC301",
            test_name="多维度组合查询",
            message="最近三个月给孩子们在教育方面花了多少钱？",
            expected_keywords=["教育", "孩子"]
        )
    
    async def test_tc302_trend_comparison_analysis(self):
        """
        TC302: 趋势对比分析
        
        验证点：
        1. 获取多月数据
        2. 计算趋势（增长/减少）
        3. 分析原因
        4. 识别关键变化点
        5. 给出有价值的洞察
        """
        await self.run_test(
            test_id="TC302",
            test_name="趋势对比分析",
            message="最近三个月餐饮支出是增加还是减少？为什么？",
            expected_keywords=["餐饮", "趋势"]
        )
    
    async def test_tc303_hypothetical_query(self):
        """
        TC303: 假设性查询
        
        验证点：
        1. 理解假设性问题
        2. 基于历史数据分析
        3. 计算并给出建议
        4. 建议具体可执行
        5. 考虑多个类目调整
        """
        await self.run_test(
            test_id="TC303",
            test_name="假设性查询",
            message="如果下个月预算只有8000，我该怎么调整？",
            expected_keywords=["预算", "建议", "调整"]
        )
    
    async def test_tc304_inference_query(self):
        """
        TC304: 推理性查询
        
        验证点：
        1. 理解需要推理的问题
        2. 关联多维度数据（身高、营养、运动）
        3. 分析可能原因
        4. 给出合理推测
        5. 建议具体行动
        """
        await self.run_test(
            test_id="TC304",
            test_name="推理性查询",
            message="儿子最近身高增长加速，可能是什么原因？",
            expected_keywords=["身高", "儿子", "原因"]
        )


async def main():
    """运行P1复杂查询能力测试"""
    print("=" * 80)
    print("P1 集成测试 - 复杂查询能力")
    print("=" * 80)
    print()
    
    tester = TestP1ComplexQuery()
    
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        await tester.test_tc301_multi_dimension_query()
        await asyncio.sleep(0.5)
        
        await tester.test_tc302_trend_comparison_analysis()
        await asyncio.sleep(0.5)
        
        await tester.test_tc303_hypothetical_query()
        await asyncio.sleep(0.5)
        
        await tester.test_tc304_inference_query()
        
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

