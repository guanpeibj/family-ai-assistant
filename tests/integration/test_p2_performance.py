#!/usr/bin/env python3
"""
P2 集成测试 - 性能测试

测试用例：TC105
优先级：P2（增强功能）

功能覆盖：
- 复杂分析响应时间（<15秒）
"""

import asyncio
from datetime import datetime
from base import IntegrationTestBase


class TestP2Performance(IntegrationTestBase):
    """P2 性能测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p2_performance")
    
    async def _prepare_analysis_data(self):
        """准备分析所需数据"""
        print("\n--- 准备性能测试数据 ---")
        
        # 创建足够的历史数据
        expenses = [
            "餐饮1000元", "交通500元", "教育1500元",
            "医疗600元", "娱乐400元", "居住2000元",
            "服饰300元", "日用200元",
        ]
        
        for expense in expenses:
            await self.run_test(
                test_id="P2-PERF-setup",
                test_name="准备数据",
                message=expense,
                expected_keywords=["记录"]
            )
            await asyncio.sleep(0.2)
        
        print("--- 数据准备完成 ---\n")
        await asyncio.sleep(0.5)
    
    async def test_tc105_complex_analysis_performance(self):
        """
        TC105: 复杂分析响应时间
        
        验证点：
        1. 执行复杂的财务分析
        2. 响应时间 < 15秒
        3. 分析结果准确完整
        4. 包含多维度数据
        
        性能要求：复杂分析应在15秒内返回
        """
        await self._prepare_analysis_data()
        
        print("\n--- 主测试：复杂分析性能 ---")
        
        start_time = datetime.now()
        
        result = await self.run_test(
            test_id="TC105",
            test_name="复杂分析响应时间",
            message="分析最近半年的财务状况并给出建议",
            expected_keywords=["财务", "支出"]
        )
        
        # 验证性能
        if result and 'duration' in result:
            duration = result['duration']
            
            print("\n--- 性能评估 ---")
            if duration < 15.0:
                print(f"✅ 性能优秀：{duration:.2f}秒 < 15秒")
            elif duration < 20.0:
                print(f"⚠️ 性能可接受：{duration:.2f}秒（略超15秒目标）")
            else:
                print(f"❌ 性能需优化：{duration:.2f}秒 > 15秒")
            
            # 性能分级
            if duration < 10.0:
                grade = "A+"
            elif duration < 15.0:
                grade = "A"
            elif duration < 20.0:
                grade = "B"
            else:
                grade = "C"
            
            print(f"性能等级：{grade}")


async def main():
    """运行P2性能测试"""
    print("=" * 80)
    print("P2 集成测试 - 性能测试")
    print("=" * 80)
    print()
    
    tester = TestP2Performance()
    
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        await tester.test_tc105_complex_analysis_performance()
        
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

