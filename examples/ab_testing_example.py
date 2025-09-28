"""
A/B 测试框架使用示例

这个示例展示了如何在 FAA 中设置和管理 A/B 测试，
用于安全地测试新的 Prompt 版本和 AI 行为模式。

使用场景：
1. 测试新的对话风格（更友善 vs 更专业）
2. 测试不同的澄清策略（主动澄清 vs 智能推断）
3. 测试新的工具使用策略（保守 vs 积极使用工具）
"""
import asyncio
from datetime import datetime, timedelta
from src.core.ab_testing import (
    ABTestingManager, ExperimentConfig, ExperimentStatus, 
    ExperimentResult, get_experiment_version
)

# 初始化 A/B 测试管理器
ab_manager = ABTestingManager()


def create_conversational_style_experiment():
    """示例1: 测试对话风格的 A/B 实验"""
    
    # 创建实验配置
    config = ExperimentConfig(
        id="conversation_style_v1",
        name="对话风格测试：友善 vs 专业",
        description="测试更友善的对话风格是否能提升用户满意度",
        status=ExperimentStatus.DRAFT,
        
        # 版本设置
        control_version="v4_default",           # 对照组：当前默认版本
        treatment_versions=["v4_friendly"],     # 实验组：更友善的版本
        
        # 流量分配
        traffic_allocation={
            "control": 70,      # 70% 用户使用默认版本
            "treatment_0": 30   # 30% 用户使用友善版本
        },
        
        # 目标设置
        target_channels=["threema"],            # 只在 Threema 渠道测试
        target_user_groups=[],                  # 所有用户组
        exclude_users=[],                       # 不排除任何用户
        
        # 时间设置
        max_duration_hours=168,                 # 最多运行7天
        
        # 安全设置
        max_error_rate=0.05,                   # 错误率超过5%则暂停
        min_sample_size=50,                    # 至少50个样本
        
        # 指标设置
        primary_metrics=["user_rating", "response_time"],
        secondary_metrics=["clarification_rate", "tool_call_count"]
    )
    
    return config


def create_clarification_strategy_experiment():
    """示例2: 测试澄清策略的 A/B 实验"""
    
    config = ExperimentConfig(
        id="clarification_strategy_v1", 
        name="澄清策略测试：主动 vs 智能推断",
        description="测试更智能的推断是否能减少澄清次数并提升体验",
        status=ExperimentStatus.DRAFT,
        
        control_version="v4_default",
        treatment_versions=["v4_smart_inference"],
        
        traffic_allocation={
            "control": 50,
            "treatment_0": 50
        },
        
        target_channels=["threema", "api"],
        
        max_duration_hours=120,  # 5天
        max_error_rate=0.03,     # 更严格的错误率
        min_sample_size=100,
        
        primary_metrics=["clarification_rate", "success_rate"],
        secondary_metrics=["user_rating", "response_length"]
    )
    
    return config


async def setup_experiments():
    """设置实验"""
    
    print("🧪 设置 A/B 测试实验...")
    
    # 创建实验配置
    style_exp = create_conversational_style_experiment()
    clarification_exp = create_clarification_strategy_experiment()
    
    # 注册实验
    success1 = ab_manager.create_experiment(style_exp)
    success2 = ab_manager.create_experiment(clarification_exp)
    
    if success1:
        print(f"✅ 实验 '{style_exp.name}' 创建成功")
    if success2:
        print(f"✅ 实验 '{clarification_exp.name}' 创建成功")
    
    # 启动第一个实验
    style_exp.status = ExperimentStatus.RUNNING
    style_exp.start_time = datetime.now().timestamp()
    ab_manager._experiments[style_exp.id] = style_exp
    
    print(f"🚀 实验 '{style_exp.name}' 已启动")
    
    return success1 and success2


def simulate_user_interactions():
    """模拟用户交互和实验数据收集"""
    
    print("\n📊 模拟用户交互...")
    
    # 模拟不同用户的交互
    test_users = [
        {"id": "user_001", "channel": "threema"},
        {"id": "user_002", "channel": "threema"}, 
        {"id": "user_003", "channel": "api"},
        {"id": "user_004", "channel": "threema"},
        {"id": "user_005", "channel": "api"},
    ]
    
    for user in test_users:
        # 获取用户的实验版本
        version = get_experiment_version(
            user_id=user["id"],
            channel=user["channel"]
        )
        
        print(f"👤 用户 {user['id']} ({user['channel']}) → 版本: {version}")
        
        # 模拟实验结果
        variant, _ = ab_manager.get_variant_for_user(
            user["id"], 
            "conversation_style_v1", 
            channel=user["channel"]
        )
        
        if variant != "control":
            result = ExperimentResult(
                user_id=user["id"],
                experiment_id="conversation_style_v1",
                variant=variant,
                trace_id=f"trace_{user['id']}_001",
                channel=user["channel"],
                timestamp=datetime.now().timestamp(),
                response_time_ms=1200,  # 模拟响应时间
                success=True,
                need_clarification=False,
                tool_calls_count=1,
                response_length=85,
                user_rating=4 if variant == "treatment_0" else 3  # 友善版本评分更高
            )
            
            ab_manager.record_result(result)


def analyze_experiment_results():
    """分析实验结果"""
    
    print("\n📈 分析实验结果...")
    
    # 获取实验统计
    stats = ab_manager.get_experiment_stats("conversation_style_v1")
    
    print(f"\n实验: {stats.get('name', 'Unknown')}")
    print(f"状态: {stats.get('status', 'Unknown')}")
    print(f"总样本量: {stats.get('total_samples', 0)}")
    
    if stats.get('variants'):
        print("\n各变量表现:")
        for variant, metrics in stats['variants'].items():
            print(f"  {variant}:")
            print(f"    样本量: {metrics['sample_size']}")
            print(f"    成功率: {metrics['success_rate']*100:.1f}%")
            print(f"    平均响应时间: {metrics['avg_response_time_ms']:.0f}ms")
            print(f"    澄清率: {metrics['clarification_rate']*100:.1f}%")


def demonstrate_safety_features():
    """演示安全特性"""
    
    print("\n🛡️  演示安全特性...")
    
    # 模拟一个有问题的实验结果（高错误率）
    for i in range(10):
        bad_result = ExperimentResult(
            user_id=f"test_user_{i}",
            experiment_id="conversation_style_v1", 
            variant="treatment_0",
            trace_id=f"trace_bad_{i}",
            channel="threema",
            timestamp=datetime.now().timestamp(),
            response_time_ms=5000,  # 响应很慢
            success=False,          # 失败
            error_type="AnalysisError"
        )
        
        ab_manager.record_result(bad_result)
    
    print("⚠️  检测到实验组错误率过高，实验可能会被自动暂停")
    
    # 检查实验状态
    experiment = ab_manager._experiments.get("conversation_style_v1")
    if experiment and experiment.status == ExperimentStatus.PAUSED:
        print("🔴 实验已被自动暂停以保护用户体验")
    else:
        print("🟡 实验仍在运行中（安全检查可能需要更多样本）")


async def main():
    """主函数：演示 A/B 测试的完整流程"""
    
    print("🎯 FAA A/B 测试框架演示\n")
    
    # 1. 设置实验
    await setup_experiments()
    
    # 2. 模拟用户交互
    simulate_user_interactions()
    
    # 3. 分析结果
    analyze_experiment_results()
    
    # 4. 演示安全特性
    demonstrate_safety_features()
    
    print("\n✨ A/B 测试演示完成!")
    print("\n💡 实际使用中，你可以:")
    print("   1. 在 prompts/family_assistant_prompts.yaml 中定义新版本")
    print("   2. 使用此框架安全地测试新版本")
    print("   3. 基于数据决定是否采用新版本")


if __name__ == "__main__":
    asyncio.run(main())
