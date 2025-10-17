#!/usr/bin/env python3
"""
测试 Provider 配置系统

验证：
1. Provider 预配置加载
2. 限流策略
3. 使用量追踪
4. Embedding 策略
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.core.llm_providers import ProviderRegistry, UsageTracker


def test_provider_registry():
    """测试 Provider 注册表"""
    print("=" * 60)
    print("测试 Provider 注册表")
    print("=" * 60)

    # 列出所有可用的 provider
    providers = ProviderRegistry.list_providers()
    print("\n可用的 Providers:")
    for name, desc in providers.items():
        print(f"  - {name}: {desc}")

    # 获取特定 provider
    print("\n\nProvider 详细配置:")
    for provider_name in ["qwen", "deepseek", "doubao", "kimi"]:
        config = ProviderRegistry.get_provider(provider_name)
        if config:
            print(f"\n{provider_name.upper()}:")
            print(f"  Provider Type: {config.provider_type}")
            print(f"  Base URL: {config.default_base_url}")
            print(f"  Default Model: {config.default_model}")
            print(f"  RPM Limit: {config.rpm_limit}")
            print(f"  Concurrency: {config.concurrency_limit}")
            print(f"  Embedding Strategy: {config.embedding_strategy}")
            print(f"  Region: {config.region}")


def test_usage_tracker():
    """测试使用量追踪器"""
    print("\n" + "=" * 60)
    print("测试使用量追踪器")
    print("=" * 60)

    tracker = UsageTracker()

    # 模拟各个 provider 的调用
    test_cases = [
        ("qwen", 1000, 500),
        ("qwen", 2000, 1000),
        ("deepseek", 500, 200),
        ("kimi", 100, 50),
    ]

    print("\n模拟 API 调用:")
    for provider, input_tokens, output_tokens in test_cases:
        tracker.record(provider, input_tokens, output_tokens)
        print(
            f"  {provider}: input={input_tokens}, output={output_tokens}"
        )

    # 获取统计摘要
    print("\n\n使用量统计摘要:")
    summary = tracker.get_summary()
    for key, value in summary.items():
        if key == "by_provider":
            continue
        print(f"  {key}: {value}")

    # 按 provider 分类
    if "by_provider" in summary:
        print("\n按 Provider 分类:")
        for provider, stats in summary["by_provider"].items():
            print(f"  {provider}:")
            for key, value in stats.items():
                print(f"    {key}: {value}")


def test_pricing_guide():
    """显示定价指导"""
    print("\n" + "=" * 60)
    print("官方定价信息（需查看最新）")
    print("=" * 60)

    pricing_guide = UsageTracker().get_pricing_guide()
    for provider, info in pricing_guide.items():
        print(f"\n{provider.upper()}:")
        print(f"  名称: {info['name']}")
        print(f"  定价链接: {info['pricing_url']}")
        print(f"  说明: {info['note']}")


if __name__ == "__main__":
    test_provider_registry()
    test_usage_tracker()
    test_pricing_guide()

    print("\n" + "=" * 60)
    print("所有测试完成！")
    print("=" * 60)
    
    print("\n💡 成本计算:")
    print("  运行: python3 examples/cost_calculator.py")
    print("  可以根据实际 token 数计算成本")
