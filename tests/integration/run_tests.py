#!/usr/bin/env python3
"""
FAA 集成测试运行器

统一运行和管理所有集成测试，生成测试报告。

使用方式：
    # 运行P0核心测试
    python tests/integration/run_tests.py --priority P0
    
    # 运行P1重要功能测试
    python tests/integration/run_tests.py --priority P1
    
    # 运行P2增强功能测试
    python tests/integration/run_tests.py --priority P2
    
    # 运行所有测试
    python tests/integration/run_tests.py --all
    
    # 运行特定测试套件
    python tests/integration/run_tests.py --suite accounting
"""

import asyncio
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict
import json

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 导入所有P0测试套件
from test_p0_accounting import TestP0Accounting
from test_p0_budget import TestP0Budget
from test_p0_query import TestP0Query
from test_p0_health import TestP0Health
from test_p0_reminder import TestP0Reminder
from test_p0_info import TestP0Info
from test_p0_clarification import TestP0Clarification
from test_p0_data_accuracy import TestP0DataAccuracy
from test_p0_scenarios import TestP0Scenarios

# 导入所有P1测试套件
from test_p1_advanced_query import TestP1AdvancedQuery
from test_p1_visualization import TestP1Visualization
from test_p1_health_analysis import TestP1HealthAnalysis
from test_p1_reminder_management import TestP1ReminderManagement
from test_p1_multimodal_voice import TestP1MultimodalVoice
from test_p1_multimodal_image import TestP1MultimodalImage
from test_p1_complex_query import TestP1ComplexQuery
from test_p1_proactive_analysis import TestP1ProactiveAnalysis
from test_p1_deep_analysis import TestP1DeepAnalysis
from test_p1_monthly_scenarios import TestP1MonthlyScenarios

# 导入所有P2测试套件
from test_p2_multimodal_combined import TestP2MultimodalCombined
from test_p2_boundary_handling import TestP2BoundaryHandling
from test_p2_data_correlation import TestP2DataCorrelation
from test_p2_exception_handling import TestP2ExceptionHandling
from test_p2_performance import TestP2Performance
from test_p2_综合场景 import TestP2ComprehensiveScenarios

# 测试套件配置
TEST_SUITES = {
    'P0': {
        'name': '核心必测功能',
        'suites': [
            ('accounting', TestP0Accounting, '基础记账功能', 'TC001-TC008'),
            ('budget', TestP0Budget, '预算管理核心', 'TC009-TC013'),
            ('query', TestP0Query, '基础查询功能', 'TC015-TC018'),
            ('health', TestP0Health, '基础健康记录', 'TC026-TC028'),
            ('reminder', TestP0Reminder, '基础提醒功能', 'TC038-TC041'),
            ('info', TestP0Info, '基础信息管理', 'TC052-TC055'),
            ('clarification', TestP0Clarification, '澄清功能', 'TC070-TC073'),
            ('data_accuracy', TestP0DataAccuracy, '数据准确性', 'TC090-TC096'),
            ('scenarios', TestP0Scenarios, '日常场景与性能', 'TC104-TC109'),
        ]
    },
    'P1': {
        'name': '重要功能',
        'suites': [
            ('advanced_query', TestP1AdvancedQuery, '高级查询功能', 'TC019-TC022'),
            ('visualization', TestP1Visualization, '可视化功能', 'TC023-TC025'),
            ('health_analysis', TestP1HealthAnalysis, '健康分析功能', 'TC032-TC037'),
            ('reminder_mgmt', TestP1ReminderManagement, '提醒管理功能', 'TC044-TC048'),
            ('voice', TestP1MultimodalVoice, '语音输入处理', 'TC059-TC062'),
            ('image', TestP1MultimodalImage, '图片识别处理', 'TC063-TC067'),
            ('complex_query', TestP1ComplexQuery, '复杂查询能力', 'TC074-TC077'),
            ('proactive', TestP1ProactiveAnalysis, '主动分析能力', 'TC082-TC085'),
            ('deep_analysis', TestP1DeepAnalysis, '深度分析能力', 'TC086-TC089'),
            ('monthly', TestP1MonthlyScenarios, '月度场景', 'TC110-TC112'),
        ]
    },
    'P2': {
        'name': '增强功能',
        'suites': [
            ('combined', TestP2MultimodalCombined, '组合输入处理', 'TC068-TC069'),
            ('boundary', TestP2BoundaryHandling, '边界处理', 'TC078-TC081'),
            ('correlation', TestP2DataCorrelation, '数据关联性', 'TC097-TC099'),
            ('exception', TestP2ExceptionHandling, '异常处理', 'TC100-TC103'),
            ('performance', TestP2Performance, '性能测试', 'TC105'),
            ('comprehensive', TestP2ComprehensiveScenarios, '综合场景', 'TC113-TC116'),
        ]
    }
}


class TestRunner:
    """集成测试运行器"""
    
    def __init__(self):
        self.results = []
        self.start_time = None
        self.end_time = None
    
    async def run_suite(self, suite_name: str, suite_class, description: str, test_ids: str):
        """
        运行单个测试套件
        
        Args:
            suite_name: 套件名称
            suite_class: 测试类
            description: 描述
            test_ids: 测试用例ID范围
        """
        print()
        print("╔" + "═" * 78 + "╗")
        print(f"║ 测试套件: {description:<40} {test_ids:>26} ║")
        print("╚" + "═" * 78 + "╝")
        print()
        
        try:
            # 创建测试实例
            tester = suite_class()
            
            # 设置
            if not await tester.setup():
                print(f"❌ {suite_name} 初始化失败")
                return None
            
            # 运行该套件的main函数
            # 注：每个测试类都有自己的测试方法，这里简化处理
            # 实际执行通过调用各个test_方法
            await self._run_test_methods(tester)
            
            # 打印总结
            summary = tester.print_summary()
            
            # 清理
            await tester.teardown()
            
            return {
                'suite': suite_name,
                'description': description,
                'test_ids': test_ids,
                'summary': summary,
                'results': tester.test_results
            }
            
        except Exception as e:
            print(f"❌ {suite_name} 执行异常：{e}")
            return {
                'suite': suite_name,
                'error': str(e)
            }
    
    async def _run_test_methods(self, tester):
        """运行测试类中的所有test_开头的方法"""
        import inspect
        
        # 获取所有test_开头的方法
        test_methods = [
            method for method in dir(tester)
            if method.startswith('test_') and callable(getattr(tester, method))
        ]
        
        # 按名称排序
        test_methods.sort()
        
        # 依次执行
        for method_name in test_methods:
            method = getattr(tester, method_name)
            try:
                await method()
                # 测试之间短暂延迟
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"❌ {method_name} 执行失败：{e}")
    
    async def run_priority(self, priority: str):
        """
        运行指定优先级的所有测试
        
        Args:
            priority: P0, P1 或 P2
        """
        if priority not in TEST_SUITES:
            print(f"❌ 未知优先级：{priority}")
            return
        
        config = TEST_SUITES[priority]
        suites = config['suites']
        
        if not suites:
            print(f"⚠️ {priority} 测试套件尚未实现")
            return
        
        print()
        print("=" * 80)
        print(f"{priority} 集成测试 - {config['name']}")
        print("=" * 80)
        print(f"共 {len(suites)} 个测试套件")
        print()
        
        self.start_time = datetime.now()
        
        # 运行所有套件
        for suite_name, suite_class, description, test_ids in suites:
            result = await self.run_suite(suite_name, suite_class, description, test_ids)
            if result:
                self.results.append(result)
        
        self.end_time = datetime.now()
        
        # 生成汇总报告
        self.print_summary(priority)
    
    async def run_all(self):
        """运行所有测试"""
        print()
        print("=" * 80)
        print("运行所有集成测试")
        print("=" * 80)
        print()
        
        self.start_time = datetime.now()
        
        for priority in ['P0', 'P1', 'P2']:
            await self.run_priority(priority)
        
        self.end_time = datetime.now()
        
        # 生成总体报告
        self.print_summary('ALL')
    
    def print_summary(self, scope: str):
        """
        打印测试总结
        
        Args:
            scope: P0, P1, P2 或 ALL
        """
        print()
        print("=" * 80)
        print(f"测试总结 - {scope}")
        print("=" * 80)
        
        if not self.results:
            print("没有测试结果")
            return
        
        # 统计
        total_suites = len(self.results)
        total_tests = 0
        total_passed = 0
        total_failed = 0
        
        for result in self.results:
            if 'summary' in result:
                summary = result['summary']
                total_tests += summary['total']
                total_passed += summary['passed']
                total_failed += summary['failed']
        
        # 总体统计
        print(f"\n📊 总体统计")
        print(f"   测试套件: {total_suites}")
        print(f"   测试用例: {total_tests}")
        print(f"   ✅ 通过: {total_passed} ({total_passed/total_tests*100:.1f}%)" if total_tests > 0 else "   ✅ 通过: 0")
        print(f"   ❌ 失败: {total_failed} ({total_failed/total_tests*100:.1f}%)" if total_tests > 0 else "   ❌ 失败: 0")
        
        if self.start_time and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()
            print(f"   ⏱️ 总耗时: {duration:.1f}秒")
        
        # 各套件详情
        print(f"\n📋 各套件详情")
        for i, result in enumerate(self.results, 1):
            suite_name = result.get('suite', 'Unknown')
            description = result.get('description', '')
            
            if 'error' in result:
                print(f"{i}. ❌ {suite_name} ({description})")
                print(f"   错误: {result['error']}")
            elif 'summary' in result:
                summary = result['summary']
                status = "✅" if summary['failed'] == 0 else "⚠️"
                print(f"{i}. {status} {suite_name} ({description})")
                print(f"   通过: {summary['passed']}/{summary['total']}")
        
        print()
        
        # 保存报告
        self.save_report(scope)
    
    def save_report(self, scope: str):
        """
        保存测试报告到文件
        
        Args:
            scope: 测试范围
        """
        report_dir = Path(__file__).parent / 'reports'
        report_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = report_dir / f'test_report_{scope}_{timestamp}.json'
        
        report_data = {
            'scope': scope,
            'timestamp': timestamp,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'results': self.results
        }
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
        
        print(f"📄 测试报告已保存: {report_file}")


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='FAA 集成测试运行器')
    parser.add_argument('--priority', choices=['P0', 'P1', 'P2'], 
                       help='运行指定优先级的测试')
    parser.add_argument('--all', action='store_true',
                       help='运行所有测试')
    parser.add_argument('--suite', 
                       help='运行指定的测试套件（如：accounting, budget）')
    
    args = parser.parse_args()
    
    runner = TestRunner()
    
    try:
        if args.all:
            await runner.run_all()
        elif args.priority:
            await runner.run_priority(args.priority)
        elif args.suite:
            # 查找指定套件
            suite_found = False
            for priority, config in TEST_SUITES.items():
                for suite_name, suite_class, description, test_ids in config['suites']:
                    if suite_name == args.suite:
                        await runner.run_suite(suite_name, suite_class, description, test_ids)
                        suite_found = True
                        break
                if suite_found:
                    break
            
            if not suite_found:
                print(f"❌ 未找到测试套件：{args.suite}")
                return 1
        else:
            # 默认运行P0
            print("未指定参数，默认运行 P0 核心测试")
            await runner.run_priority('P0')
        
        return 0
        
    except Exception as e:
        print(f"❌ 测试运行异常：{e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

