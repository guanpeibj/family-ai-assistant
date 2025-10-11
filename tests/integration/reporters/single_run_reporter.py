"""
单次测试运行报告生成器
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from validators.scoring import TestScore, TestSuiteSummary

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.integration.version_tracker import VersionTracker


class SingleRunReporter:
    """单次测试运行报告生成器"""
    
    @staticmethod
    def generate_report(
        run_id: str,
        config: Dict[str, Any],
        summary: TestSuiteSummary,
        test_scores: List[TestScore],
        output_dir: Path
    ) -> Path:
        """
        生成单次测试运行报告
        
        Args:
            run_id: 运行ID
            config: 配置信息
            summary: 测试总结
            test_scores: 所有测试评分
            output_dir: 输出目录
            
        Returns:
            报告文件路径
        """
        # 收集版本信息
        version_info = VersionTracker.get_version_info()
        
        report = {
            "test_run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "version_info": version_info,  # ✅ 新增：完整的版本信息
            "config": config,
            "summary": summary.to_dict(),
            "test_scores": [score.to_dict() for score in test_scores],
            "performance": SingleRunReporter._calculate_performance_stats(test_scores)
        }
        
        # 保存JSON报告
        output_dir.mkdir(parents=True, exist_ok=True)
        report_file = output_dir / f"{run_id}.json"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        # 生成人类可读的文本报告
        text_report = SingleRunReporter._generate_text_report(report)
        text_file = output_dir / f"{run_id}.txt"
        
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write(text_report)
        
        return report_file
    
    @staticmethod
    def _calculate_performance_stats(test_scores: List[TestScore]) -> Dict:
        """计算性能统计"""
        if not test_scores:
            return {}
        
        durations = [s.duration for s in test_scores]
        durations.sort()
        
        n = len(durations)
        p50_idx = n // 2
        p95_idx = int(n * 0.95)
        p99_idx = int(n * 0.99)
        
        return {
            "avg_response_time": sum(durations) / n,
            "min_response_time": min(durations),
            "max_response_time": max(durations),
            "p50": durations[p50_idx],
            "p95": durations[p95_idx] if p95_idx < n else durations[-1],
            "p99": durations[p99_idx] if p99_idx < n else durations[-1]
        }
    
    @staticmethod
    def _generate_text_report(report: Dict) -> str:
        """生成文本报告"""
        summary = report["summary"]
        config = report["config"]
        perf = report["performance"]
        version_info = report.get("version_info", {})
        
        lines = []
        lines.append("=" * 80)
        lines.append(f"FAA 集成测试报告")
        lines.append("=" * 80)
        lines.append(f"运行ID: {report['test_run_id']}")
        lines.append(f"时间: {report['timestamp']}")
        lines.append("")
        
        # ✅ 新增：版本信息部分
        if version_info:
            lines.append("版本信息:")
            lines.append(f"  测试时间: {version_info.get('test_date', 'N/A')}")
            
            # 主LLM
            llm = version_info.get('llm', {})
            lines.append(f"  主项目LLM: {llm.get('provider', 'N/A')} / {llm.get('model', 'N/A')}")
            lines.append(f"  Embedding: {llm.get('embedding_provider', 'N/A')} / {llm.get('embedding_model', 'N/A')}")
            
            # 评估器LLM
            eval_llm = version_info.get('evaluator_llm', {})
            lines.append(f"  评估器LLM: {eval_llm.get('model', 'N/A')}")
            
            # Prompts版本
            prompts = version_info.get('prompts', {})
            lines.append(f"  Prompts版本: {prompts.get('version', 'N/A')} ({prompts.get('current_profile', 'N/A')})")
            lines.append("")
        
        lines.append("配置信息:")
        for key, value in config.items():
            lines.append(f"  {key}: {value}")
        lines.append("")
        
        lines.append("总体统计:")
        lines.append(f"  总测试数: {summary['total_cases']}")
        lines.append(f"  通过: {summary['passed']} ({summary['pass_rate']*100:.1f}%)")
        lines.append(f"  失败: {summary['failed']}")
        lines.append("")
        
        lines.append("平均分数:")
        lines.append(f"  总分: {summary['avg_total_score']:.1f}/100")
        lines.append(f"  数据层: {summary['avg_data_score']:.1f}/40")
        lines.append(f"  智能层: {summary['avg_intelligence_score']:.1f}/40")
        lines.append(f"  体验层: {summary['avg_experience_score']:.1f}/20")
        lines.append("")
        
        if perf:
            lines.append("性能统计:")
            lines.append(f"  平均响应时间: {perf['avg_response_time']:.2f}秒")
            lines.append(f"  P50: {perf['p50']:.2f}秒")
            lines.append(f"  P95: {perf['p95']:.2f}秒")
            lines.append(f"  P99: {perf['p99']:.2f}秒")
            lines.append("")
        
        if summary['failed_cases']:
            lines.append(f"失败用例 ({len(summary['failed_cases'])}):")
            for i, case in enumerate(summary['failed_cases'], 1):
                lines.append(f"  {i}. [{case['test_id']}] {case['test_name']}")
                lines.append(f"     分数: {case['score']:.1f}/100")
                if case['issues']:
                    lines.append(f"     问题: {', '.join(case['issues'][:2])}")
            lines.append("")
        
        lines.append("=" * 80)
        
        return "\n".join(lines)

