"""
AB测试对比报告生成器
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from validators.scoring import TestSuiteSummary, ScoringSystem


class ABComparisonReporter:
    """AB测试对比报告生成器"""
    
    @staticmethod
    def generate_report(
        comparison_id: str,
        description: str,
        variant_a_config: Dict[str, Any],
        variant_b_config: Dict[str, Any],
        summary_a: TestSuiteSummary,
        summary_b: TestSuiteSummary,
        output_dir: Path
    ) -> Path:
        """
        生成AB对比报告
        
        Args:
            comparison_id: 对比ID
            description: 描述
            variant_a_config: A变体配置
            variant_b_config: B变体配置
            summary_a: A变体测试总结
            summary_b: B变体测试总结
            output_dir: 输出目录
            
        Returns:
            报告文件路径
        """
        # 使用评分系统计算对比
        comparison = ScoringSystem.compare_summaries(
            summary_a, summary_b,
            name_a=variant_a_config.get("name", "A"),
            name_b=variant_b_config.get("name", "B")
        )
        
        # 生成推荐
        recommendation = ABComparisonReporter._generate_recommendation(
            summary_a, summary_b, comparison
        )
        
        report = {
            "comparison_id": comparison_id,
            "timestamp": datetime.now().isoformat(),
            "description": description,
            "variant_a": {
                **comparison["variant_a"],
                "config": variant_a_config
            },
            "variant_b": {
                **comparison["variant_b"],
                "config": variant_b_config
            },
            "comparison": comparison["comparison"],
            "recommendation": recommendation
        }
        
        # 保存JSON报告
        output_dir.mkdir(parents=True, exist_ok=True)
        report_file = output_dir / f"ab_{comparison_id}.json"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        # 生成文本报告
        text_report = ABComparisonReporter._generate_text_report(report)
        text_file = output_dir / f"ab_{comparison_id}.txt"
        
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write(text_report)
        
        return report_file
    
    @staticmethod
    def _generate_recommendation(
        summary_a: TestSuiteSummary,
        summary_b: TestSuiteSummary,
        comparison: Dict
    ) -> Dict[str, Any]:
        """生成推荐"""
        score_diff = comparison["comparison"]["score_diff"]
        duration_diff = comparison["comparison"]["duration_diff"]
        
        # 计算综合得分（质量权重0.7，速度权重0.3）
        # 质量归一化：分数/100
        # 速度归一化：-时间差/10（负值表示更快更好）
        quality_a = summary_a.avg_total_score / 100
        quality_b = summary_b.avg_total_score / 100
        
        speed_a = 1.0  # 基准
        speed_b = 1.0 - (duration_diff / summary_a.avg_duration) if summary_a.avg_duration > 0 else 1.0
        
        value_a = quality_a * 0.7 + speed_a * 0.3
        value_b = quality_b * 0.7 + speed_b * 0.3
        
        # 判断显著性
        score_significant = abs(score_diff) >= 3  # 3分以上认为显著
        speed_significant = abs(duration_diff) >= 2  # 2秒以上认为显著
        
        # 生成推荐
        if value_b > value_a + 0.05:  # 5%以上的优势
            winner = "variant_b"
            reason = ABComparisonReporter._build_reason(
                summary_b, summary_a, score_diff, duration_diff,
                score_significant, speed_significant, True
            )
        elif value_a > value_b + 0.05:
            winner = "variant_a"
            reason = ABComparisonReporter._build_reason(
                summary_a, summary_b, -score_diff, -duration_diff,
                score_significant, speed_significant, False
            )
        else:
            winner = "tie"
            reason = "两个变体表现相当，差异不显著"
        
        return {
            "overall": winner,
            "reason": reason,
            "confidence": min(abs(value_b - value_a) * 2, 0.95),
            "score_significant": score_significant,
            "speed_significant": speed_significant
        }
    
    @staticmethod
    def _build_reason(
        winner_summary: TestSuiteSummary,
        loser_summary: TestSuiteSummary,
        score_diff: float,
        duration_diff: float,
        score_significant: bool,
        speed_significant: bool,
        is_b: bool
    ) -> str:
        """构建推荐理由"""
        reasons = []
        
        if score_significant:
            if score_diff > 0:
                reasons.append(f"质量显著更高（+{score_diff:.1f}分）")
            else:
                reasons.append(f"质量略低（{score_diff:.1f}分）")
        
        if speed_significant:
            if duration_diff < 0:
                reasons.append(f"速度显著更快（{-duration_diff:.1f}秒）")
            else:
                reasons.append(f"速度较慢（+{duration_diff:.1f}秒）")
        
        if not reasons:
            reasons.append("综合表现更优")
        
        return "，".join(reasons)
    
    @staticmethod
    def _generate_text_report(report: Dict) -> str:
        """生成文本报告"""
        lines = []
        lines.append("=" * 80)
        lines.append("FAA AB测试对比报告")
        lines.append("=" * 80)
        lines.append(f"对比ID: {report['comparison_id']}")
        lines.append(f"描述: {report['description']}")
        lines.append(f"时间: {report['timestamp']}")
        lines.append("")
        
        # 变体A
        lines.append("🅰️  变体A:")
        lines.append(f"  配置: {report['variant_a']['config']}")
        lines.append(f"  平均分: {report['variant_a']['avg_score']:.1f}/100")
        lines.append(f"  平均耗时: {report['variant_a']['avg_duration']:.1f}秒")
        lines.append(f"  通过率: {report['variant_a']['pass_rate']*100:.1f}%")
        lines.append("")
        
        # 变体B
        lines.append("🅱️  变体B:")
        lines.append(f"  配置: {report['variant_b']['config']}")
        lines.append(f"  平均分: {report['variant_b']['avg_score']:.1f}/100")
        lines.append(f"  平均耗时: {report['variant_b']['avg_duration']:.1f}秒")
        lines.append(f"  通过率: {report['variant_b']['pass_rate']*100:.1f}%")
        lines.append("")
        
        # 对比分析
        comp = report['comparison']
        lines.append("📊 对比分析:")
        lines.append(f"  分数差异: {comp['score_diff']:+.1f}分")
        lines.append(f"  耗时差异: {comp['duration_diff']:+.1f}秒")
        lines.append(f"  通过率差异: {comp['pass_rate_diff']:+.1%}")
        lines.append("")
        
        # 分层对比
        lines.append("分层对比:")
        layer_comp = comp['layer_comparison']
        for layer_name, layer_data in layer_comp.items():
            lines.append(f"  {layer_name}:")
            lines.append(f"    A: {layer_data['a']:.1f}  B: {layer_data['b']:.1f}  差异: {layer_data['diff']:+.1f}")
        lines.append("")
        
        # 推荐
        rec = report['recommendation']
        lines.append("💡 推荐:")
        winner_name = {"variant_a": "变体A", "variant_b": "变体B", "tie": "两者相当"}
        lines.append(f"  选择: {winner_name[rec['overall']]}")
        lines.append(f"  理由: {rec['reason']}")
        lines.append(f"  置信度: {rec['confidence']*100:.0f}%")
        lines.append("")
        
        lines.append("=" * 80)
        
        return "\n".join(lines)

