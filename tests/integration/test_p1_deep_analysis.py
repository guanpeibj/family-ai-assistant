#!/usr/bin/env python3
"""
P1 集成测试 - 深度分析能力

测试用例：TC341 - TC344
优先级：P1（重要功能）

功能覆盖：
- 财务健康综合分析
- 成长发育评估
- 家庭支出模式识别
- 优化建议生成
"""

import asyncio
from base import IntegrationTestBase


class TestP1DeepAnalysis(IntegrationTestBase):
    """P1 深度分析能力测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p1_deep_analysis")
    
    async def _prepare_comprehensive_data(self):
        """准备综合分析所需的丰富数据"""
        print("\n--- 准备综合数据 ---")
        
        # 多类目支出
        expenses = [
            "餐饮支出1200元",
            "交通费800元",
            "教育支出1500元",
            "医疗费600元",
            "娱乐500元",
            "居住费2000元",
        ]
        
        # 收入
        income = "本月工资收入10000元"
        
        for record in expenses + [income]:
            await self.run_test(
                test_id="P1-DEEP-setup",
                test_name="准备数据",
                message=record,
                expected_keywords=["记录"]
            )
            await asyncio.sleep(0.2)
        
        print("--- 数据准备完成 ---\n")
        await asyncio.sleep(0.5)
    
    async def test_tc341_financial_health_analysis(self):
        """
        TC341: 财务健康综合分析
        
        验证点：
        1. 分析收支平衡
        2. 评估预算执行情况
        3. 分析支出结构
        4. 识别趋势
        5. 给出财务健康评分和建议
        """
        await self._prepare_comprehensive_data()
        
        await self.run_test(
            test_id="TC341",
            test_name="财务健康综合分析",
            message="分析我们家的财务状况",
            expected_keywords=["财务", "支出", "收入"]
        )
    
    async def test_tc342_growth_development_assessment(self):
        """
        TC342: 成长发育评估
        
        验证点：
        1. 综合身高、体重等数据
        2. 对比标准曲线
        3. 评估发育状况
        4. 识别异常或优势
        5. 给出专业评估和建议
        """
        # 先记录健康数据
        print("\n--- 准备健康数据 ---")
        health_records = [
            "儿子身高92cm",
            "儿子体重17kg",
        ]
        
        for record in health_records:
            await self.run_test(
                test_id="TC342-setup",
                test_name="记录健康数据",
                message=record,
                expected_keywords=["记录"]
            )
            await asyncio.sleep(0.2)
        
        await asyncio.sleep(0.5)
        
        print("\n--- 主测试：成长评估 ---")
        await self.run_test(
            test_id="TC342",
            test_name="成长发育评估",
            message="评估一下儿子的成长发育情况",
            expected_keywords=["儿子", "身高", "体重"]
        )
    
    async def test_tc343_spending_pattern_recognition(self):
        """
        TC343: 家庭支出模式识别
        
        验证点：
        1. 分析时间分布（月初/月末、工作日/周末）
        2. 识别周期模式
        3. 发现消费习惯
        4. 给出模式描述
        5. 建议优化方向
        """
        await self.run_test(
            test_id="TC343",
            test_name="家庭支出模式识别",
            message="我们家主要在什么时候花钱比较多？",
            expected_keywords=["支出", "时间"]
        )
    
    async def test_tc344_optimization_recommendations(self):
        """
        TC344: 优化建议生成
        
        验证点：
        1. 基于支出分析
        2. 给出可操作的节省建议
        3. 建议具体且合理
        4. 考虑家庭实际情况
        5. 优先级排序
        """
        await self.run_test(
            test_id="TC344",
            test_name="优化建议生成",
            message="有什么省钱建议吗？",
            expected_keywords=["建议", "支出"]
        )


async def main():
    """运行P1深度分析能力测试"""
    print("=" * 80)
    print("P1 集成测试 - 深度分析能力")
    print("=" * 80)
    print()
    
    tester = TestP1DeepAnalysis()
    
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        await tester.test_tc341_financial_health_analysis()
        await asyncio.sleep(0.5)
        
        await tester.test_tc342_growth_development_assessment()
        await asyncio.sleep(0.5)
        
        await tester.test_tc343_spending_pattern_recognition()
        await asyncio.sleep(0.5)
        
        await tester.test_tc344_optimization_recommendations()
        
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

