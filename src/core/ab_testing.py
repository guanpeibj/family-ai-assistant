"""
A/B 测试框架

支持 Prompt 版本的 A/B 测试，让 FAA 能够安全地尝试新的 AI 行为模式。

核心功能：
1. 用户分流：基于 user_id 的一致性分流
2. 版本管理：支持多版本 Prompt 同时运行
3. 指标收集：自动收集关键指标（响应时间、成功率、用户满意度等）
4. 安全回退：支持快速切换和紧急回退
5. 配置热更新：无需重启即可调整实验参数

设计原则：
- 对用户透明：用户感受不到 A/B 测试的存在
- 数据驱动：基于真实数据做决策
- 安全优先：确保实验不影响核心功能
"""
import hashlib
import json
import time
from typing import Dict, Any, Optional, List, Tuple, Set
from enum import Enum
from dataclasses import dataclass, asdict
import structlog

from .exceptions import ConfigurationError, create_error_context

logger = structlog.get_logger(__name__)


class ExperimentStatus(Enum):
    """实验状态"""
    DRAFT = "draft"          # 草稿状态，未启动
    RUNNING = "running"      # 运行中
    PAUSED = "paused"        # 暂停
    COMPLETED = "completed"  # 已完成
    TERMINATED = "terminated" # 提前终止


@dataclass
class ExperimentConfig:
    """实验配置"""
    id: str                                    # 实验 ID
    name: str                                  # 实验名称
    description: str                           # 实验描述
    status: ExperimentStatus                   # 实验状态
    
    # 版本配置
    control_version: str                       # 对照组版本（如 v4_default）
    treatment_versions: List[str]              # 实验组版本列表
    
    # 流量分配（百分比，总和应为100）
    traffic_allocation: Dict[str, int]         # {"control": 80, "treatment_a": 20}
    
    # 目标用户
    target_channels: List[str] = None          # 目标渠道（如 ["threema"]）
    target_user_groups: List[str] = None       # 目标用户组
    exclude_users: List[str] = None            # 排除用户列表
    
    # 时间控制
    start_time: Optional[float] = None         # 开始时间戳
    end_time: Optional[float] = None           # 结束时间戳
    max_duration_hours: int = 168              # 最大运行时间（小时，默认7天）
    
    # 安全控制
    max_error_rate: float = 0.05               # 最大错误率阈值（5%）
    min_sample_size: int = 100                 # 最小样本量
    
    # 指标定义
    primary_metrics: List[str] = None          # 主要指标
    secondary_metrics: List[str] = None        # 次要指标
    
    def __post_init__(self):
        if self.target_channels is None:
            self.target_channels = []
        if self.target_user_groups is None:
            self.target_user_groups = []
        if self.exclude_users is None:
            self.exclude_users = []
        if self.primary_metrics is None:
            self.primary_metrics = ["response_time", "success_rate"]
        if self.secondary_metrics is None:
            self.secondary_metrics = ["clarification_rate", "tool_call_count"]


@dataclass
class ExperimentResult:
    """实验结果记录"""
    user_id: str
    experiment_id: str
    variant: str                               # control 或 treatment_xxx
    
    # 请求信息
    trace_id: str
    channel: str
    timestamp: float
    
    # 性能指标
    response_time_ms: int
    success: bool
    error_type: Optional[str] = None
    
    # 业务指标
    need_clarification: bool = False
    tool_calls_count: int = 0
    response_length: int = 0
    
    # 用户反馈（如果有）
    user_rating: Optional[int] = None          # 1-5分评分
    user_feedback: Optional[str] = None        # 用户反馈文本


class ABTestingManager:
    """A/B 测试管理器"""
    
    def __init__(self):
        self._experiments: Dict[str, ExperimentConfig] = {}
        self._results: List[ExperimentResult] = []
        self._user_assignments: Dict[str, Dict[str, str]] = {}  # {user_id: {exp_id: variant}}
        
    def create_experiment(self, config: ExperimentConfig) -> bool:
        """创建新实验"""
        try:
            # 验证配置
            self._validate_experiment_config(config)
            
            # 存储实验配置
            self._experiments[config.id] = config
            
            logger.info(
                "experiment.created",
                experiment_id=config.id,
                name=config.name,
                control=config.control_version,
                treatments=config.treatment_versions
            )
            return True
            
        except Exception as e:
            logger.error("experiment.create_failed", experiment_id=config.id, error=str(e))
            return False
    
    def _validate_experiment_config(self, config: ExperimentConfig):
        """验证实验配置"""
        # 检查流量分配
        total_traffic = sum(config.traffic_allocation.values())
        if total_traffic != 100:
            raise ConfigurationError(f"流量分配总和必须为100%，当前为{total_traffic}%")
        
        # 检查版本存在性（这里简化处理，实际应该检查 prompt manager）
        all_versions = [config.control_version] + config.treatment_versions
        for version in all_versions:
            if not version:
                raise ConfigurationError(f"版本名称不能为空")
        
        # 检查时间设置
        if config.start_time and config.end_time:
            if config.start_time >= config.end_time:
                raise ConfigurationError("实验开始时间必须早于结束时间")
    
    def get_variant_for_user(
        self, 
        user_id: str, 
        experiment_id: str,
        *,
        channel: Optional[str] = None,
        user_group: Optional[str] = None
    ) -> Tuple[str, str]:
        """为用户获取实验版本
        
        Returns:
            Tuple[variant_name, prompt_version]: 变量名称和对应的 Prompt 版本
        """
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            # 实验不存在，返回默认版本
            return "control", "v4_default"
        
        # 检查实验是否有效
        if not self._is_experiment_active(experiment):
            return "control", experiment.control_version
        
        # 检查用户是否在目标范围内
        if not self._is_user_eligible(user_id, experiment, channel, user_group):
            return "control", experiment.control_version
        
        # 获取或分配用户到变量
        variant = self._assign_user_to_variant(user_id, experiment)
        
        # 返回对应的 Prompt 版本
        if variant == "control":
            return variant, experiment.control_version
        else:
            # treatment_xxx 映射到实际版本
            variant_index = int(variant.split('_')[1]) if '_' in variant else 0
            if variant_index < len(experiment.treatment_versions):
                return variant, experiment.treatment_versions[variant_index]
            else:
                # 回退到对照组
                return "control", experiment.control_version
    
    def _is_experiment_active(self, experiment: ExperimentConfig) -> bool:
        """检查实验是否处于活跃状态"""
        if experiment.status != ExperimentStatus.RUNNING:
            return False
        
        now = time.time()
        
        # 检查开始时间
        if experiment.start_time and now < experiment.start_time:
            return False
        
        # 检查结束时间
        if experiment.end_time and now > experiment.end_time:
            return False
        
        # 检查最大运行时间
        if experiment.start_time:
            elapsed_hours = (now - experiment.start_time) / 3600
            if elapsed_hours > experiment.max_duration_hours:
                return False
        
        return True
    
    def _is_user_eligible(
        self, 
        user_id: str, 
        experiment: ExperimentConfig,
        channel: Optional[str] = None,
        user_group: Optional[str] = None
    ) -> bool:
        """检查用户是否符合实验目标条件"""
        # 检查排除列表
        if user_id in experiment.exclude_users:
            return False
        
        # 检查目标渠道
        if experiment.target_channels and channel:
            if channel not in experiment.target_channels:
                return False
        
        # 检查目标用户组
        if experiment.target_user_groups and user_group:
            if user_group not in experiment.target_user_groups:
                return False
        
        return True
    
    def _assign_user_to_variant(self, user_id: str, experiment: ExperimentConfig) -> str:
        """为用户分配实验变量（一致性哈希）"""
        # 检查是否已经分配过
        if user_id in self._user_assignments:
            existing_assignment = self._user_assignments[user_id].get(experiment.id)
            if existing_assignment:
                return existing_assignment
        
        # 使用一致性哈希分配
        hash_input = f"{user_id}:{experiment.id}"
        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest()[:8], 16)
        percentage = hash_value % 100
        
        # 根据流量分配决定变量
        cumulative = 0
        for variant, allocation in experiment.traffic_allocation.items():
            cumulative += allocation
            if percentage < cumulative:
                # 记录分配结果
                if user_id not in self._user_assignments:
                    self._user_assignments[user_id] = {}
                self._user_assignments[user_id][experiment.id] = variant
                
                logger.debug(
                    "user.assigned_to_variant",
                    user_id=user_id,
                    experiment_id=experiment.id,
                    variant=variant,
                    hash_percentage=percentage
                )
                return variant
        
        # 回退到对照组
        return "control"
    
    def record_result(self, result: ExperimentResult):
        """记录实验结果"""
        self._results.append(result)
        
        # 检查安全阈值
        experiment = self._experiments.get(result.experiment_id)
        if experiment and experiment.status == ExperimentStatus.RUNNING:
            self._check_safety_thresholds(experiment)
    
    def _check_safety_thresholds(self, experiment: ExperimentConfig):
        """检查安全阈值，必要时暂停实验"""
        recent_results = [
            r for r in self._results[-1000:]  # 最近1000个结果
            if r.experiment_id == experiment.id and 
               r.timestamp > time.time() - 3600  # 最近1小时
        ]
        
        if len(recent_results) < experiment.min_sample_size:
            return  # 样本量不足
        
        # 检查错误率
        for variant in experiment.traffic_allocation.keys():
            variant_results = [r for r in recent_results if r.variant == variant]
            if not variant_results:
                continue
            
            error_rate = sum(1 for r in variant_results if not r.success) / len(variant_results)
            if error_rate > experiment.max_error_rate:
                logger.warning(
                    "experiment.safety_threshold_exceeded",
                    experiment_id=experiment.id,
                    variant=variant,
                    error_rate=error_rate,
                    threshold=experiment.max_error_rate
                )
                # 暂停实验
                experiment.status = ExperimentStatus.PAUSED
                break
    
    def get_experiment_stats(self, experiment_id: str) -> Dict[str, Any]:
        """获取实验统计数据"""
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            return {}
        
        # 获取实验结果
        exp_results = [r for r in self._results if r.experiment_id == experiment_id]
        
        if not exp_results:
            return {
                "experiment_id": experiment_id,
                "status": experiment.status.value,
                "total_samples": 0,
                "variants": {}
            }
        
        # 按变量分组统计
        stats = {
            "experiment_id": experiment_id,
            "name": experiment.name,
            "status": experiment.status.value,
            "total_samples": len(exp_results),
            "start_time": experiment.start_time,
            "variants": {}
        }
        
        # 统计各变量的指标
        for variant in experiment.traffic_allocation.keys():
            variant_results = [r for r in exp_results if r.variant == variant]
            if not variant_results:
                continue
            
            success_rate = sum(1 for r in variant_results if r.success) / len(variant_results)
            avg_response_time = sum(r.response_time_ms for r in variant_results) / len(variant_results)
            clarification_rate = sum(1 for r in variant_results if r.need_clarification) / len(variant_results)
            avg_tool_calls = sum(r.tool_calls_count for r in variant_results) / len(variant_results)
            
            stats["variants"][variant] = {
                "sample_size": len(variant_results),
                "success_rate": round(success_rate, 3),
                "avg_response_time_ms": round(avg_response_time, 2),
                "clarification_rate": round(clarification_rate, 3),
                "avg_tool_calls": round(avg_tool_calls, 2)
            }
        
        return stats
    
    def list_active_experiments(self) -> List[Dict[str, Any]]:
        """列出所有活跃实验"""
        active = []
        for exp_id, experiment in self._experiments.items():
            if self._is_experiment_active(experiment):
                active.append({
                    "id": exp_id,
                    "name": experiment.name,
                    "status": experiment.status.value,
                    "control_version": experiment.control_version,
                    "treatment_versions": experiment.treatment_versions,
                    "traffic_allocation": experiment.traffic_allocation
                })
        return active
    
    def pause_experiment(self, experiment_id: str) -> bool:
        """暂停实验"""
        if experiment_id in self._experiments:
            self._experiments[experiment_id].status = ExperimentStatus.PAUSED
            logger.info("experiment.paused", experiment_id=experiment_id)
            return True
        return False
    
    def resume_experiment(self, experiment_id: str) -> bool:
        """恢复实验"""
        if experiment_id in self._experiments:
            self._experiments[experiment_id].status = ExperimentStatus.RUNNING
            logger.info("experiment.resumed", experiment_id=experiment_id)
            return True
        return False


# 全局 A/B 测试管理器实例
ab_testing_manager = ABTestingManager()


def get_experiment_version(
    user_id: str,
    *,
    channel: Optional[str] = None,
    user_group: Optional[str] = None,
    default_version: str = "v4_default"
) -> str:
    """便捷函数：为用户获取实验版本
    
    这个函数会检查所有活跃的实验，返回用户应该使用的 Prompt 版本。
    如果用户没有参与任何实验，返回默认版本。
    
    Args:
        user_id: 用户ID
        channel: 用户渠道（如 threema, api）
        user_group: 用户组（如 family, premium）
        default_version: 默认 Prompt 版本
        
    Returns:
        应该使用的 Prompt 版本名称
    """
    # 检查所有活跃实验
    active_experiments = ab_testing_manager.list_active_experiments()
    
    for experiment in active_experiments:
        variant, version = ab_testing_manager.get_variant_for_user(
            user_id, 
            experiment["id"],
            channel=channel,
            user_group=user_group
        )
        
        # 如果用户参与了实验且不是对照组，返回实验版本
        if variant != "control":
            logger.debug(
                "user.in_experiment",
                user_id=user_id,
                experiment_id=experiment["id"],
                variant=variant,
                version=version
            )
            return version
    
    return default_version
