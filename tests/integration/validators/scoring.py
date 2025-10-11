"""
评分系统

计算和汇总测试评分：
- 数据层 (40分)
- 智能层 (40分)
- 体验层 (20分)
- 总分 (100分)
"""

from typing import Dict, Any, List
from dataclasses import dataclass, asdict


@dataclass
class TestScore:
    """单个测试的评分"""
    test_id: str
    test_name: str
    
    # 三层评分
    data_score: float  # 满分40
    intelligence_score: float  # 满分40
    experience_score: float  # 满分20
    total_score: float  # 满分100
    
    # 详细维度
    data_details: Dict[str, Any]
    intelligence_details: Dict[str, Any]
    experience_details: Dict[str, Any]
    
    # 元信息
    duration: float
    success: bool
    issues: List[str]
    
    # ✅ 对话记录（支持单轮和多轮）
    # 格式：["user(user_id)- xxx", "faa- xxx", "user(user_id)- yyy", "faa- yyy"]
    conversation: List[str] = None
    
    def __post_init__(self):
        """确保conversation始终是列表"""
        if self.conversation is None:
            self.conversation = []
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def get_grade(self) -> str:
        """获取等级"""
        if self.total_score >= 90:
            return "A"
        elif self.total_score >= 80:
            return "B"
        elif self.total_score >= 70:
            return "C"
        elif self.total_score >= 60:
            return "D"
        else:
            return "F"


@dataclass
class TestSuiteSummary:
    """测试套件总结"""
    total_cases: int
    passed: int
    failed: int
    pass_rate: float
    
    # 平均分数
    avg_total_score: float
    avg_data_score: float
    avg_intelligence_score: float
    avg_experience_score: float
    
    # 性能
    avg_duration: float
    total_duration: float
    
    # 维度详情
    dimension_averages: Dict[str, float]
    
    # 失败用例
    failed_cases: List[Dict[str, Any]]
    
    def to_dict(self) -> Dict:
        return asdict(self)


class ScoringSystem:
    """评分系统"""
    
    @staticmethod
    def calculate_test_score(
        test_id: str,
        test_name: str,
        data_result: Dict,
        intelligence_result: Dict,
        experience_result: Dict,
        duration: float,
        conversation: List[str] = None
    ) -> TestScore:
        """
        计算单个测试的评分
        
        Args:
            test_id: 测试ID
            test_name: 测试名称
            data_result: 数据层验证结果
            intelligence_result: 智能层评估结果
            experience_result: 体验层评估结果
            duration: 耗时（秒）
            conversation: 对话记录列表
            
        Returns:
            TestScore对象
        """
        data_score = data_result.get("score", 0)
        intelligence_score = intelligence_result.get("score", 0)
        experience_score = experience_result.get("score", 0)
        total_score = data_score + intelligence_score + experience_score
        
        # 收集所有问题
        issues = []
        issues.extend(data_result.get("issues", []))
        issues.extend(intelligence_result.get("suggestions", []))
        issues.extend(experience_result.get("suggestions", []))
        
        # 判断是否成功（60分及格）
        success = total_score >= 60 and data_score >= 24  # 数据层至少60%
        
        return TestScore(
            test_id=test_id,
            test_name=test_name,
            data_score=data_score,
            intelligence_score=intelligence_score,
            experience_score=experience_score,
            total_score=total_score,
            data_details=data_result.get("details", {}),
            intelligence_details=intelligence_result.get("dimensions", {}),
            experience_details=experience_result.get("dimensions", {}),
            duration=duration,
            success=success,
            issues=issues,
            conversation=conversation or []
        )
    
    @staticmethod
    def calculate_suite_summary(
        test_scores: List[TestScore]
    ) -> TestSuiteSummary:
        """
        计算测试套件总结
        
        Args:
            test_scores: 所有测试的评分列表
            
        Returns:
            TestSuiteSummary对象
        """
        if not test_scores:
            return TestSuiteSummary(
                total_cases=0,
                passed=0,
                failed=0,
                pass_rate=0.0,
                avg_total_score=0.0,
                avg_data_score=0.0,
                avg_intelligence_score=0.0,
                avg_experience_score=0.0,
                avg_duration=0.0,
                total_duration=0.0,
                dimension_averages={},
                failed_cases=[]
            )
        
        total_cases = len(test_scores)
        passed = sum(1 for s in test_scores if s.success)
        failed = total_cases - passed
        pass_rate = passed / total_cases
        
        # 平均分数
        avg_total_score = sum(s.total_score for s in test_scores) / total_cases
        avg_data_score = sum(s.data_score for s in test_scores) / total_cases
        avg_intelligence_score = sum(s.intelligence_score for s in test_scores) / total_cases
        avg_experience_score = sum(s.experience_score for s in test_scores) / total_cases
        
        # 性能统计
        avg_duration = sum(s.duration for s in test_scores) / total_cases
        total_duration = sum(s.duration for s in test_scores)
        
        # 维度平均分
        dimension_averages = ScoringSystem._calculate_dimension_averages(test_scores)
        
        # 失败用例
        failed_cases = [
            {
                "test_id": s.test_id,
                "test_name": s.test_name,
                "score": s.total_score,
                "issues": s.issues[:3]  # 只取前3个问题
            }
            for s in test_scores if not s.success
        ]
        
        return TestSuiteSummary(
            total_cases=total_cases,
            passed=passed,
            failed=failed,
            pass_rate=pass_rate,
            avg_total_score=avg_total_score,
            avg_data_score=avg_data_score,
            avg_intelligence_score=avg_intelligence_score,
            avg_experience_score=avg_experience_score,
            avg_duration=avg_duration,
            total_duration=total_duration,
            dimension_averages=dimension_averages,
            failed_cases=failed_cases
        )
    
    @staticmethod
    def _calculate_dimension_averages(test_scores: List[TestScore]) -> Dict[str, float]:
        """计算各个维度的平均分"""
        
        # 收集所有维度的分数
        dimensions = {}
        
        # 数据层维度（从details中提取）
        for score in test_scores:
            for key, value in score.data_details.items():
                if isinstance(value, dict) and "score" in value:
                    if key not in dimensions:
                        dimensions[f"data_{key}"] = []
                    dimensions[f"data_{key}"].append(value["score"])
        
        # 智能层维度
        for score in test_scores:
            for key, value in score.intelligence_details.items():
                if key not in dimensions:
                    dimensions[key] = []
                dimensions[key].append(value)
        
        # 体验层维度
        for score in test_scores:
            for key, value in score.experience_details.items():
                if key not in dimensions:
                    dimensions[key] = []
                dimensions[key].append(value)
        
        # 计算平均值
        averages = {}
        for key, values in dimensions.items():
            if values:
                averages[key] = sum(values) / len(values)
        
        return averages
    
    @staticmethod
    def compare_summaries(
        summary_a: TestSuiteSummary,
        summary_b: TestSuiteSummary,
        name_a: str = "A",
        name_b: str = "B"
    ) -> Dict[str, Any]:
        """
        对比两个测试套件的总结
        
        Returns:
            对比结果字典
        """
        return {
            "variant_a": {
                "name": name_a,
                "avg_score": summary_a.avg_total_score,
                "avg_duration": summary_a.avg_duration,
                "pass_rate": summary_a.pass_rate
            },
            "variant_b": {
                "name": name_b,
                "avg_score": summary_b.avg_total_score,
                "avg_duration": summary_b.avg_duration,
                "pass_rate": summary_b.pass_rate
            },
            "comparison": {
                "score_diff": summary_b.avg_total_score - summary_a.avg_total_score,
                "duration_diff": summary_b.avg_duration - summary_a.avg_duration,
                "pass_rate_diff": summary_b.pass_rate - summary_a.pass_rate,
                "layer_comparison": {
                    "data_layer": {
                        "a": summary_a.avg_data_score,
                        "b": summary_b.avg_data_score,
                        "diff": summary_b.avg_data_score - summary_a.avg_data_score
                    },
                    "intelligence_layer": {
                        "a": summary_a.avg_intelligence_score,
                        "b": summary_b.avg_intelligence_score,
                        "diff": summary_b.avg_intelligence_score - summary_a.avg_intelligence_score
                    },
                    "experience_layer": {
                        "a": summary_a.avg_experience_score,
                        "b": summary_b.avg_experience_score,
                        "diff": summary_b.avg_experience_score - summary_a.avg_experience_score
                    }
                }
            }
        }

