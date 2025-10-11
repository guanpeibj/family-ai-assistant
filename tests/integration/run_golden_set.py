#!/usr/bin/env python3
"""
运行黄金测试集

黄金测试集是用于AB测试和模型对比的标准测试集
包含50个最具代表性的测试用例
"""

import asyncio
import sys
import argparse
from pathlib import Path
from datetime import datetime
import yaml

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from base_new import IntegrationTestBase
from reporters import SingleRunReporter


class GoldenSetRunner(IntegrationTestBase):
    """黄金测试集运行器"""
    
    def __init__(self, test_cases_file: Path):
        super().__init__(test_suite_name="golden_set")
        self.test_cases_file = test_cases_file
        self.test_cases = []
        self.multi_turn_tests = []  # ✅ 新增：多轮对话测试
        
    def load_test_cases(self):
        """加载测试用例（包括单轮和多轮）"""
        with open(self.test_cases_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        # 收集单轮测试用例
        self.test_cases = []
        self.multi_turn_tests = []
        
        for category_name, cases in data.items():
            if isinstance(cases, list):
                if category_name == 'multi_turn_tests':
                    # ✅ 多轮对话测试
                    self.multi_turn_tests.extend(cases)
                elif category_name not in ['test_suite_name', 'test_suite_version', 'total_cases']:
                    # 普通单轮测试
                    self.test_cases.extend(cases)
        
        print(f"✅ 加载了 {len(self.test_cases)} 个单轮测试用例")
        print(f"✅ 加载了 {len(self.multi_turn_tests)} 个多轮对话测试")
        return len(self.test_cases) + len(self.multi_turn_tests)
    
    async def run_all_tests(self, limit: int = None, include_multi_turn: bool = True):
        """
        运行所有测试用例（单轮 + 多轮）
        
        Args:
            limit: 限制运行的用例数量（用于快速测试）
            include_multi_turn: 是否包含多轮对话测试
        """
        # 单轮测试
        cases_to_run = self.test_cases[:limit] if limit else self.test_cases
        
        print(f"\n开始运行 {len(cases_to_run)} 个单轮测试用例...")
        print("=" * 80)
        
        for i, test_case in enumerate(cases_to_run, 1):
            print(f"\n[{i}/{len(cases_to_run)}] 运行中...")
            
            await self.run_test(
                test_id=test_case['test_id'],
                test_name=test_case['test_name'],
                message=test_case['user_input'],
                expected_behavior=test_case['expected_behavior'],
                data_verification=test_case.get('data_verification'),
                intelligence_check=test_case.get('intelligence_check'),
                experience_check=test_case.get('experience_check')
            )
            
            # 短暂延迟避免过快
            await asyncio.sleep(0.5)
        
        # ✅ 多轮对话测试
        if include_multi_turn and self.multi_turn_tests:
            print(f"\n\n开始运行 {len(self.multi_turn_tests)} 个多轮对话测试...")
            print("=" * 80)
            
            for i, test_case in enumerate(self.multi_turn_tests, 1):
                print(f"\n[多轮 {i}/{len(self.multi_turn_tests)}] 运行中...")
                
                await self.run_multi_turn_test(
                    test_id=test_case['test_id'],
                    test_name=test_case['test_name'],
                    turns=test_case['turns'],
                    context=test_case.get('context')
                )
                
                # 多轮测试之间延迟更长，避免线程混乱
                await asyncio.sleep(1.0)


async def main():
    parser = argparse.ArgumentParser(description='运行FAA黄金测试集')
    parser.add_argument('--config', type=str, help='配置参数（JSON格式）')
    parser.add_argument('--limit', type=int, help='限制运行的用例数量（仅限单轮测试）')
    parser.add_argument('--output-dir', type=str, default='tests/integration/reports',
                       help='报告输出目录')
    parser.add_argument('--no-multi-turn', action='store_true',
                       help='跳过多轮对话测试（只运行单轮测试）')
    
    args = parser.parse_args()
    
    # 生成运行ID
    run_id = f"golden_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # 读取配置
    config = {
        "prompt_version": "current",
        "llm_model": "current",
        "test_suite": "golden_50"
    }
    if args.config:
        import json
        config.update(json.loads(args.config))
    
    print("=" * 80)
    print("FAA 黄金测试集")
    print("=" * 80)
    print(f"运行ID: {run_id}")
    print(f"配置: {config}")
    print("=" * 80)
    
    # 初始化运行器
    test_cases_file = Path(__file__).parent / "test_cases" / "golden_set.yaml"
    runner = GoldenSetRunner(test_cases_file)
    
    # 加载测试用例
    runner.load_test_cases()
    
    # 设置
    if not await runner.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        # 运行测试
        await runner.run_all_tests(
            limit=args.limit,
            include_multi_turn=not args.no_multi_turn
        )
        
        # 打印总结
        print("\n" + "=" * 80)
        print("测试完成，正在生成报告...")
        print("=" * 80)
        
        summary_dict = runner.print_summary()
        
        # 生成正确的summary对象
        from validators.scoring import ScoringSystem
        summary = ScoringSystem.calculate_suite_summary(runner.test_scores)
        
        # 生成报告
        output_dir = Path(args.output_dir)
        report_file = SingleRunReporter.generate_report(
            run_id=run_id,
            config=config,
            summary=summary,
            test_scores=runner.test_scores,
            output_dir=output_dir
        )
        
        print(f"\n📄 报告已生成:")
        print(f"   JSON: {report_file}")
        print(f"   TXT:  {report_file.with_suffix('.txt')}")
        
        # 返回码
        if summary.pass_rate >= 0.9 and summary.avg_total_score >= 80:
            print("\n🎉 黄金测试集通过！")
            return 0
        else:
            print("\n⚠️  黄金测试集未达标")
            print(f"   通过率: {summary.pass_rate*100:.1f}% (需要>=90%)")
            print(f"   平均分: {summary.avg_total_score:.1f} (需要>=80)")
            return 1
        
    except Exception as e:
        print(f"\n❌ 测试异常：{e}")
        import traceback
        traceback.print_exc()
        return 1
        
    finally:
        await runner.teardown()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

