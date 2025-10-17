#!/usr/bin/env python3
"""
LLM 成本计算器

根据实际 token 消耗计算成本。
用户需要填入实际使用的模型名称和 token 数。

使用方式：
    python3 examples/cost_calculator.py

或编程使用：
    from examples.cost_calculator import CostCalculator
    calc = CostCalculator()
    cost = calc.calculate("qwen-turbo", input_tokens=1000, output_tokens=500)
    print(f"Cost: ¥{cost:.6f}")
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.llm_client import LLMClient


class CostCalculator:
    """成本计算器 - 根据实际模型和 token 计算成本"""

    # 官方定价信息（建议定期更新）
    # 数据来源：各 provider 官网
    PRICING = {
        # Qwen 定价（¥/1K tokens）
        "qwen-turbo": {"input": 0.0003, "output": 0.0009, "currency": "CNY"},
        "qwen-plus": {"input": 0.00015, "output": 0.0006, "currency": "CNY"},
        "qwen-max": {"input": 0.0008, "output": 0.0024, "currency": "CNY"},
        "qwen-long": {"input": 0.0001, "output": 0.0002, "currency": "CNY"},

        # DeepSeek 定价（¥/1K tokens）
        "deepseek-chat": {"input": 0.00014, "output": 0.00028, "currency": "CNY"},

        # Doubao 定价（¥/1K tokens）
        "doubao-pro": {"input": 0.0004, "output": 0.0012, "currency": "CNY"},
        "doubao-lite": {"input": 0.0002, "output": 0.0006, "currency": "CNY"},

        # Kimi 定价（¥/1K tokens）
        "moonshot-v1": {"input": 0.002, "output": 0.006, "currency": "CNY"},
        "moonshot-v1-8k": {"input": 0.002, "output": 0.006, "currency": "CNY"},
        "moonshot-v1-32k": {"input": 0.002, "output": 0.006, "currency": "CNY"},
        "moonshot-v1-128k": {"input": 0.002, "output": 0.006, "currency": "CNY"},

        # OpenAI 定价（$/1K tokens）
        "gpt-4o": {"input": 0.005, "output": 0.015, "currency": "USD"},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006, "currency": "USD"},
        "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015, "currency": "USD"},

        # Claude 定价（$/1K tokens）
        "claude-3-5-sonnet": {"input": 0.003, "output": 0.015, "currency": "USD"},
        "claude-3-opus": {"input": 0.015, "output": 0.075, "currency": "USD"},
    }

    # 汇率（用于 CNY 转 USD）
    EXCHANGE_RATE = 7.2

    @classmethod
    def calculate(
        cls,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        exchange_rate: float = 7.2,
    ) -> float:
        """计算单次 API 调用的成本

        Args:
            model_name: 模型名称（如 'qwen-turbo'）
            input_tokens: 输入 token 数
            output_tokens: 输出 token 数
            exchange_rate: 汇率（CNY -> USD），默认 7.2

        Returns:
            成本（USD）
        """
        model_name = model_name.lower()

        if model_name not in cls.PRICING:
            raise ValueError(f"Unknown model: {model_name}")

        pricing = cls.PRICING[model_name]
        input_cost = (input_tokens / 1000) * pricing["input"]
        output_cost = (output_tokens / 1000) * pricing["output"]
        total_cost = input_cost + output_cost

        # 如果是 CNY，转换为 USD
        if pricing["currency"] == "CNY":
            total_cost = total_cost / exchange_rate

        return total_cost

    @classmethod
    def calculate_batch(
        cls, calls: list, exchange_rate: float = 7.2
    ) -> dict:
        """批量计算成本

        Args:
            calls: 列表，每项是 {
                'model': 模型名,
                'input_tokens': 输入token数,
                'output_tokens': 输出token数,
                'count': 调用次数（可选），
            }
            exchange_rate: 汇率

        Returns:
            {
                'total_cost_usd': 总成本（USD）,
                'by_model': 按模型的成本分类,
            }
        """
        total_cost = 0.0
        by_model = {}

        for call in calls:
            model = call["model"]
            input_tokens = call.get("input_tokens", 0)
            output_tokens = call.get("output_tokens", 0)
            count = call.get("count", 1)

            cost_per_call = cls.calculate(
                model, input_tokens, output_tokens, exchange_rate
            )
            total_cost_for_calls = cost_per_call * count

            if model not in by_model:
                by_model[model] = 0.0

            by_model[model] += total_cost_for_calls
            total_cost += total_cost_for_calls

        return {
            "total_cost_usd": round(total_cost, 6),
            "by_model": {model: round(cost, 6) for model, cost in by_model.items()},
        }

    @classmethod
    def print_available_models(cls):
        """打印所有支持的模型"""
        print("\n" + "=" * 70)
        print("支持的模型和定价")
        print("=" * 70)

        # 按 provider 分组
        by_provider = {}
        for model, pricing in cls.PRICING.items():
            provider = model.split("-")[0]
            if provider not in by_provider:
                by_provider[provider] = []
            by_provider[provider].append((model, pricing))

        for provider in sorted(by_provider.keys()):
            models = by_provider[provider]
            currency = models[0][1]["currency"]

            print(f"\n{provider.upper()} ({currency}):")
            print(f"{'Model':<25} {'Input':<15} {'Output':<15}")
            print("-" * 55)

            for model, pricing in models:
                input_price = pricing["input"]
                output_price = pricing["output"]
                print(f"{model:<25} {input_price:<15.6f} {output_price:<15.6f}")

    @classmethod
    def get_usage_summary(cls) -> dict:
        """从 LLMClient 获取实际使用量统计"""
        return LLMClient.get_usage_summary()

    @classmethod
    def estimate_from_usage(
        cls, usage_summary: dict, model_name: str, exchange_rate: float = 7.2
    ) -> dict:
        """基于 LLMClient 的使用统计估算成本

        Args:
            usage_summary: 从 LLMClient.get_usage_summary() 获取
            model_name: 实际使用的模型名
            exchange_rate: 汇率

        Returns:
            {
                'model': 模型名,
                'total_cost_usd': 总成本,
                'breakdown': {
                    'by_provider': {...}
                },
            }
        """
        result = {
            "model": model_name,
            "breakdown": {},
        }

        # 如果有按 provider 分类的统计
        if "by_provider" in usage_summary:
            total_cost = 0.0
            for provider, stats in usage_summary["by_provider"].items():
                # 这里只能粗估，因为不知道实际用的是哪个模型
                # 建议用户自己用 calculate() 或 calculate_batch()
                cost = cls.calculate(
                    model_name,
                    stats["input_tokens"],
                    stats["output_tokens"],
                    exchange_rate,
                )
                result["breakdown"][provider] = {
                    "tokens": stats["total_tokens"],
                    "calls": stats["calls"],
                    "estimated_cost_usd": round(cost, 6),
                }
                total_cost += cost

            result["total_cost_usd"] = round(total_cost, 6)

        return result


def interactive_calculator():
    """交互式计算器"""
    print("\n" + "=" * 70)
    print("LLM 成本计算器 - 交互式模式")
    print("=" * 70)

    CostCalculator.print_available_models()

    while True:
        print("\n" + "-" * 70)
        print("选项：")
        print("  1. 计算单次调用成本")
        print("  2. 计算多次调用成本")
        print("  3. 基于实际使用量估算")
        print("  4. 查看当前使用统计")
        print("  5. 退出")
        print("-" * 70)

        choice = input("请选择 (1-5): ").strip()

        if choice == "1":
            # 单次计算
            model = input("请输入模型名 (如 qwen-turbo): ").strip()
            try:
                input_tokens = int(input("输入 tokens: ").strip())
                output_tokens = int(input("输出 tokens: ").strip())

                cost = CostCalculator.calculate(model, input_tokens, output_tokens)
                print(f"\n✓ 成本: ${cost:.6f}")
            except ValueError as e:
                print(f"✗ 错误: {e}")

        elif choice == "2":
            # 批量计算
            print("\n输入多次调用（每次一行，格式: 模型名 输入tokens 输出tokens [调用次数]）")
            print("例如: qwen-turbo 1000 500")
            print("输入空行结束")

            calls = []
            while True:
                line = input().strip()
                if not line:
                    break

                parts = line.split()
                if len(parts) < 3:
                    print("格式错误，请输入至少 3 个字段")
                    continue

                try:
                    call = {
                        "model": parts[0],
                        "input_tokens": int(parts[1]),
                        "output_tokens": int(parts[2]),
                        "count": int(parts[3]) if len(parts) > 3 else 1,
                    }
                    calls.append(call)
                except ValueError:
                    print("解析错误，请重新输入")

            if calls:
                result = CostCalculator.calculate_batch(calls)
                print(f"\n✓ 总成本: ${result['total_cost_usd']:.6f}")
                print("按模型分类:")
                for model, cost in result["by_model"].items():
                    print(f"  {model}: ${cost:.6f}")

        elif choice == "3":
            # 基于使用量
            try:
                usage = CostCalculator.get_usage_summary()
                if usage.get("total_tokens", 0) == 0:
                    print("✗ 没有使用数据")
                else:
                    model = input("请输入实际使用的模型名: ").strip()
                    result = CostCalculator.estimate_from_usage(usage, model)
                    print(f"\n✓ 估算成本: ${result['total_cost_usd']:.6f}")
                    if result["breakdown"]:
                        print("按 provider 分类:")
                        for provider, stats in result["breakdown"].items():
                            print(
                                f"  {provider}: {stats['calls']} calls, "
                                f"{stats['tokens']} tokens, "
                                f"${stats['estimated_cost_usd']:.6f}"
                            )
            except Exception as e:
                print(f"✗ 错误: {e}")

        elif choice == "4":
            # 查看统计
            try:
                usage = CostCalculator.get_usage_summary()
                print("\n当前使用统计:")
                print(f"  总调用数: {usage.get('total_calls', 0)}")
                print(f"  输入 tokens: {usage.get('total_input_tokens', 0):,}")
                print(f"  输出 tokens: {usage.get('total_output_tokens', 0):,}")
                print(f"  总 tokens: {usage.get('total_tokens', 0):,}")
                print(f"  平均每次调用: {usage.get('avg_tokens_per_call', 0):,} tokens")

                if usage.get("by_provider"):
                    print("\n按 provider 分类:")
                    for provider, stats in usage["by_provider"].items():
                        print(
                            f"  {provider}: {stats['calls']} calls, "
                            f"{stats['total_tokens']} tokens"
                        )
            except Exception as e:
                print(f"✗ 错误: {e}")

        elif choice == "5":
            print("退出")
            break
        else:
            print("✗ 无效选择")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "list":
            # 列出所有模型
            CostCalculator.print_available_models()
        elif sys.argv[1] == "calc":
            # 计算: python3 cost_calculator.py calc qwen-turbo 1000 500
            if len(sys.argv) >= 5:
                model = sys.argv[2]
                input_tokens = int(sys.argv[3])
                output_tokens = int(sys.argv[4])
                cost = CostCalculator.calculate(model, input_tokens, output_tokens)
                print(f"Model: {model}")
                print(f"Input: {input_tokens}, Output: {output_tokens}")
                print(f"Cost: ${cost:.6f}")
            else:
                print("Usage: python3 cost_calculator.py calc <model> <input_tokens> <output_tokens>")
        else:
            print(f"Unknown command: {sys.argv[1]}")
    else:
        # 交互式模式
        interactive_calculator()
