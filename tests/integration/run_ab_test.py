#!/usr/bin/env python3
"""
运行AB测试对比

对比两个不同的配置（Prompt版本、模型等）
"""

import asyncio
import sys
import argparse
from pathlib import Path
from datetime import datetime
import yaml
import json
import os

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from base_new import IntegrationTestBase
from reporters import ABComparisonReporter
from validators.scoring import ScoringSystem


class ABTestRunner:
    """AB测试运行器"""
    
    def __init__(self, test_cases_file: Path):
        self.test_cases_file = test_cases_file
        self.test_cases = []
        
    def load_test_cases(self):
        """加载测试用例"""
        with open(self.test_cases_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        # 收集所有测试用例
        self.test_cases = []
        for category_name, cases in data.items():
            if isinstance(cases, list) and category_name not in ['test_suite_name', 'test_suite_version', 'total_cases']:
                self.test_cases.extend(cases)
        
        return len(self.test_cases)
    
    async def run_variant(
        self,
        variant_name: str,
        config: dict,
        limit: int = None
    ) -> IntegrationTestBase:
        """
        运行一个变体
        
        Args:
            variant_name: 变体名称
            config: 配置（可能包含prompt、model等）
            limit: 限制测试用例数量
            
        Returns:
            测试运行器实例（包含所有评分）
        """
        print(f"\n{'='*80}")
        print(f"运行变体: {variant_name}")
        print(f"配置: {config}")
        print(f"{'='*80}\n")
        
        # 设置环境变量（如果配置中有）
        original_env = {}
        if 'prompt_version' in config:
            # 可以设置环境变量来切换prompt版本
            pass
        if 'model' in config:
            original_env['OPENAI_MODEL'] = os.environ.get('OPENAI_MODEL')
            os.environ['OPENAI_MODEL'] = config['model']
        
        # 初始化运行器
        runner = IntegrationTestBase(test_suite_name=f"ab_{variant_name}")
        
        # 设置
        if not await runner.setup():
            raise Exception(f"{variant_name} 初始化失败")
        
        try:
            # 运行测试
            cases_to_run = self.test_cases[:limit] if limit else self.test_cases
            
            for i, test_case in enumerate(cases_to_run, 1):
                print(f"[{variant_name}] [{i}/{len(cases_to_run)}] {test_case['test_id']}...")
                
                await runner.run_test(
                    test_id=test_case['test_id'],
                    test_name=test_case['test_name'],
                    message=test_case['user_input'],
                    expected_behavior=test_case['expected_behavior'],
                    data_verification=test_case.get('data_verification')
                )
                
                await asyncio.sleep(0.3)
            
            return runner
            
        finally:
            # 恢复环境变量
            for key, value in original_env.items():
                if value is not None:
                    os.environ[key] = value
                elif key in os.environ:
                    del os.environ[key]


async def main():
    parser = argparse.ArgumentParser(description='运行FAA AB测试')
    parser.add_argument('--variant-a', type=str, required=True,
                       help='变体A配置（JSON格式，如 \'{"name":"v4_default","prompt":"v4_default"}\'）')
    parser.add_argument('--variant-b', type=str, required=True,
                       help='变体B配置（JSON格式，如 \'{"name":"v4_optimized","prompt":"v4_optimized"}\'）')
    parser.add_argument('--limit', type=int, default=20,
                       help='限制运行的用例数量（默认20，用于快速对比）')
    parser.add_argument('--test-suite', type=str, default='golden_set',
                       help='测试套件（默认golden_set）')
    parser.add_argument('--output-dir', type=str, default='tests/integration/reports',
                       help='报告输出目录')
    
    args = parser.parse_args()
    
    # 解析配置
    config_a = json.loads(args.variant_a)
    config_b = json.loads(args.variant_b)
    
    # 生成对比ID
    comparison_id = f"{config_a.get('name', 'A')}_vs_{config_b.get('name', 'B')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    print("=" * 80)
    print("FAA AB测试对比")
    print("=" * 80)
    print(f"对比ID: {comparison_id}")
    print(f"测试套件: {args.test_suite}")
    print(f"用例数量: {args.limit}")
    print("=" * 80)
    
    # 初始化AB测试运行器
    test_cases_file = Path(__file__).parent / "test_cases" / f"{args.test_suite}.yaml"
    ab_runner = ABTestRunner(test_cases_file)
    
    # 加载测试用例
    total_cases = ab_runner.load_test_cases()
    print(f"✅ 加载了 {total_cases} 个测试用例")
    
    try:
        # 运行变体A
        print(f"\n🅰️  开始运行变体A...")
        runner_a = await ab_runner.run_variant("A", config_a, limit=args.limit)
        
        # 运行变体B
        print(f"\n🅱️  开始运行变体B...")
        runner_b = await ab_runner.run_variant("B", config_b, limit=args.limit)
        
        # 计算总结
        summary_a = ScoringSystem.calculate_suite_summary(runner_a.test_scores)
        summary_b = ScoringSystem.calculate_suite_summary(runner_b.test_scores)
        
        # 打印对比结果
        print("\n" + "=" * 80)
        print("对比结果")
        print("=" * 80)
        
        print(f"\n🅰️  变体A ({config_a.get('name', 'A')}):")
        print(f"   平均分: {summary_a.avg_total_score:.1f}/100")
        print(f"   通过率: {summary_a.pass_rate*100:.1f}%")
        print(f"   平均耗时: {summary_a.avg_duration:.1f}秒")
        
        print(f"\n🅱️  变体B ({config_b.get('name', 'B')}):")
        print(f"   平均分: {summary_b.avg_total_score:.1f}/100")
        print(f"   通过率: {summary_b.pass_rate*100:.1f}%")
        print(f"   平均耗时: {summary_b.avg_duration:.1f}秒")
        
        print(f"\n📊 差异:")
        print(f"   分数: {summary_b.avg_total_score - summary_a.avg_total_score:+.1f}")
        print(f"   耗时: {summary_b.avg_duration - summary_a.avg_duration:+.1f}秒")
        print(f"   通过率: {(summary_b.pass_rate - summary_a.pass_rate)*100:+.1f}%")
        
        # 生成报告
        output_dir = Path(args.output_dir)
        report_file = ABComparisonReporter.generate_report(
            comparison_id=comparison_id,
            description=f"对比 {config_a.get('name')} vs {config_b.get('name')}",
            variant_a_config=config_a,
            variant_b_config=config_b,
            summary_a=summary_a,
            summary_b=summary_b,
            output_dir=output_dir
        )
        
        print(f"\n📄 对比报告已生成:")
        print(f"   JSON: {report_file}")
        print(f"   TXT:  {report_file.with_suffix('.txt')}")
        
        # 读取推荐
        with open(report_file, 'r', encoding='utf-8') as f:
            report_data = json.load(f)
        
        rec = report_data['recommendation']
        print(f"\n💡 推荐:")
        winner_map = {"variant_a": f"变体A ({config_a.get('name')})", 
                     "variant_b": f"变体B ({config_b.get('name')})", 
                     "tie": "两者相当"}
        print(f"   选择: {winner_map[rec['overall']]}")
        print(f"   理由: {rec['reason']}")
        print(f"   置信度: {rec['confidence']*100:.0f}%")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ AB测试异常：{e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

