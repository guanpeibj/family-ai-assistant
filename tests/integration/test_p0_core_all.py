#!/usr/bin/env python3
"""
P0 核心功能完整测试 (V2框架)

包含所有P0级别的核心测试用例
从golden_set.yaml加载并运行所有P0优先级的用例

这是日常开发验证的主要测试文件
"""

import asyncio
import sys
from pathlib import Path
import yaml

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from base_new import IntegrationTestBase
from reporters import SingleRunReporter
from validators.scoring import ScoringSystem
from datetime import datetime


class TestP0CoreAll(IntegrationTestBase):
    """P0核心功能完整测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p0_core_all")
        self.test_cases = []
        
    def load_p0_test_cases(self):
        """从golden_set.yaml加载所有P0优先级的测试用例"""
        yaml_file = Path(__file__).parent / "test_cases" / "golden_set.yaml"
        
        with open(yaml_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        # 收集所有P0优先级的测试用例
        self.test_cases = []
        for category_name, cases in data.items():
            if isinstance(cases, list):
                for case in cases:
                    if case.get('priority') == 'P0':
                        self.test_cases.append(case)
        
        print(f"✅ 加载了 {len(self.test_cases)} 个P0核心测试用例")
        return len(self.test_cases)
    
    async def run_all_tests(self):
        """运行所有P0测试"""
        for i, test_case in enumerate(self.test_cases, 1):
            print(f"\n{'='*80}")
            print(f"进度: [{i}/{len(self.test_cases)}]")
            print(f"{'='*80}")
            
            await self.run_test(
                test_id=test_case['test_id'],
                test_name=test_case['test_name'],
                message=test_case['user_input'],
                expected_behavior=test_case['expected_behavior'],
                data_verification=test_case.get('data_verification')
            )
            
            # 短暂延迟
            await asyncio.sleep(0.3)


async def main():
    """运行P0核心功能完整测试"""
    print("=" * 80)
    print("FAA P0核心功能完整测试 (V2框架)")
    print("三层验证：数据层(40分) + 智能层(40分) + 体验层(20分)")
    print("=" * 80)
    print()
    
    tester = TestP0CoreAll()
    
    # 加载测试用例
    count = tester.load_p0_test_cases()
    print(f"预计耗时：约{count * 0.15:.0f}分钟")
    print()
    
    # 设置
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        # 运行所有测试
        await tester.run_all_tests()
        
        # 打印总结
        print("\n" + "=" * 80)
        print("正在生成测试报告...")
        print("=" * 80)
        
        # 生成报告
        summary = ScoringSystem.calculate_suite_summary(tester.test_scores)
        run_id = f"p0_core_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 先打印摘要
        summary_dict = tester.print_summary()
        
        output_dir = Path(__file__).parent / "reports"
        report_file = SingleRunReporter.generate_report(
            run_id=run_id,
            config={"test_suite": "P0核心功能", "test_file": "test_p0_core_all.py"},
            summary=summary,
            test_scores=tester.test_scores,
            output_dir=output_dir
        )
        
        print(f"\n📄 报告已生成:")
        print(f"   JSON: {report_file}")
        print(f"   TXT:  {report_file.with_suffix('.txt')}")
        
        # 判断是否通过
        if summary.pass_rate >= 0.80 and summary.avg_total_score >= 70:
            print("\n🎉 P0核心测试通过！")
            print(f"   通过率: {summary.pass_rate*100:.1f}% (需要≥80%)")
            print(f"   平均分: {summary.avg_total_score:.1f} (需要≥70)")
            return 0
        else:
            print("\n⚠️  P0核心测试未达标")
            print(f"   通过率: {summary.pass_rate*100:.1f}% (需要≥80%)")
            print(f"   平均分: {summary.avg_total_score:.1f} (需要≥70)")
            return 1
        
    except Exception as e:
        print(f"\n❌ 测试异常：{e}")
        import traceback
        traceback.print_exc()
        return 1
        
    finally:
        await tester.teardown()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

