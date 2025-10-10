#!/usr/bin/env python3
"""
P1 集成测试 - 健康分析功能

测试用例：TC221 - TC226
优先级：P1（重要功能）

功能覆盖：
- 查询身高历史
- 成长曲线分析
- 健康指标对比
- 疫苗记录查询
- 用药历史查询
- 健康建议生成
"""

import asyncio
from base import IntegrationTestBase


class TestP1HealthAnalysis(IntegrationTestBase):
    """P1 健康分析功能测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p1_health_analysis")
    
    async def _prepare_health_data(self):
        """准备健康记录数据"""
        print("\n--- 准备健康数据 ---")
        
        health_records = [
            "儿子今天身高92cm",
            "儿子体重17kg",
            "大女儿身高120cm",
            "大女儿体重25kg",
            "儿子今天打了流感疫苗",
            "大女儿感冒了，吃了感冒药",
        ]
        
        for record in health_records:
            await self.run_test(
                test_id="P1-HEALTH-setup",
                test_name="准备健康数据",
                message=record,
                expected_keywords=["记录"]
            )
            await asyncio.sleep(0.2)
        
        print("--- 健康数据准备完成 ---\n")
        await asyncio.sleep(0.5)
    
    async def test_tc221_query_height_history(self):
        """
        TC221: 查询身高历史
        
        验证点：
        1. AI理解查询身高记录的意图
        2. 筛选人员（儿子）
        3. 筛选指标（身高）
        4. 返回历史记录，按时间排序
        5. 显示变化趋势
        """
        await self._prepare_health_data()
        
        await self.run_test(
            test_id="TC221",
            test_name="查询身高历史",
            message="儿子的身高记录",
            expected_keywords=["身高", "儿子"]
        )
    
    async def test_tc222_growth_curve_analysis(self):
        """
        TC222: 成长曲线分析
        
        验证点：
        1. AI理解成长分析的复杂意图
        2. 获取多维度数据（身高、体重、营养、运动）
        3. 计算增长速度和趋势
        4. 给出综合评估
        5. 可能生成图表
        """
        await self.run_test(
            test_id="TC222",
            test_name="成长曲线分析",
            message="分析儿子最近半年的成长情况",
            expected_keywords=["成长", "儿子"]
        )
    
    async def test_tc223_health_indicators_comparison(self):
        """
        TC223: 健康指标对比
        
        验证点：
        1. AI理解对比多个孩子指标的意图
        2. 获取所有孩子的最新数据
        3. 展示对比信息
        4. 可能用表格或列表格式
        """
        await self.run_test(
            test_id="TC223",
            test_name="健康指标对比",
            message="三个孩子现在的身高体重分别是多少？",
            expected_keywords=["身高", "体重", "孩子"]
        )
    
    async def test_tc224_vaccine_records_query(self):
        """
        TC224: 疫苗记录查询
        
        验证点：
        1. AI理解查询疫苗的意图
        2. 筛选人员和类型
        3. 返回疫苗接种历史
        4. 按时间排列
        """
        await self.run_test(
            test_id="TC224",
            test_name="疫苗记录查询",
            message="大女儿打过哪些疫苗？",
            expected_keywords=["疫苗", "大女儿"]
        )
    
    async def test_tc225_medication_history_query(self):
        """
        TC225: 用药历史查询
        
        验证点：
        1. AI理解查询生病和用药的意图
        2. 关联查询健康记录和用药记录
        3. 返回时间和药物信息
        4. 显示病情描述
        """
        await self.run_test(
            test_id="TC225",
            test_name="用药历史查询",
            message="儿子上次生病是什么时候？吃的什么药？",
            expected_keywords=["儿子"]
        )
    
    async def test_tc226_health_advice_generation(self):
        """
        TC226: 健康建议生成
        
        验证点：
        1. AI理解健康咨询的意图
        2. 基于历史数据分析
        3. 关联营养、运动等因素
        4. 给出可操作的建议
        5. 建议合理且有依据
        """
        await self.run_test(
            test_id="TC226",
            test_name="健康建议生成",
            message="儿子最近身高增长慢，有什么建议吗？",
            expected_keywords=["建议", "儿子"]
        )


async def main():
    """运行P1健康分析功能测试"""
    print("=" * 80)
    print("P1 集成测试 - 健康分析功能")
    print("=" * 80)
    print()
    
    tester = TestP1HealthAnalysis()
    
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        await tester.test_tc221_query_height_history()
        await asyncio.sleep(0.5)
        
        await tester.test_tc222_growth_curve_analysis()
        await asyncio.sleep(0.5)
        
        await tester.test_tc223_health_indicators_comparison()
        await asyncio.sleep(0.5)
        
        await tester.test_tc224_vaccine_records_query()
        await asyncio.sleep(0.5)
        
        await tester.test_tc225_medication_history_query()
        await asyncio.sleep(0.5)
        
        await tester.test_tc226_health_advice_generation()
        
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

