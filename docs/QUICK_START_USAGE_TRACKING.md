# 快速开始：使用量追踪与成本计算

## 📊 一句话总结

系统自动追踪 token 消耗，用户根据官方定价手动计算成本。

## 🚀 快速开始（3 分钟）

### 第1步：启用追踪（默认已启用）

```bash
# .env 中确认
ENABLE_USAGE_TRACKING=true
```

### 第2步：获取使用统计

```python
from src.core.llm_client import LLMClient

summary = LLMClient.get_usage_summary()
print(f"已调用 {summary['total_calls']} 次")
print(f"消耗 {summary['total_tokens']:,} tokens")
# 输出:
# 已调用 42 次
# 消耗 150000 tokens
```

### 第3步：计算成本

**方式 A：交互式（推荐新手）**
```bash
python3 examples/cost_calculator.py
# 菜单选择 1-5 进行各种计算
```

**方式 B：快速命令行**
```bash
# 计算单次成本
python3 examples/cost_calculator.py calc qwen-turbo 1000 500
# 输出: Cost: $0.000525
```

**方式 C：编程调用（推荐集成）**
```python
from examples.cost_calculator import CostCalculator

# 单次计算
cost = CostCalculator.calculate(
    model="qwen-turbo",
    input_tokens=summary['total_input_tokens'],
    output_tokens=summary['total_output_tokens']
)
print(f"总成本: ${cost:.6f}")

# 批量计算多个模型
result = CostCalculator.calculate_batch([
    {"model": "qwen-turbo", "input_tokens": 50000, "output_tokens": 15000, "count": 1},
    {"model": "deepseek-chat", "input_tokens": 20000, "output_tokens": 5000, "count": 1},
])
print(f"总成本: ${result['total_cost_usd']:.6f}")
```

## 💡 使用场景

### 场景 1：每周成本统计

```python
import json
from src.core.llm_client import LLMClient
from examples.cost_calculator import CostCalculator

# 获取统计
summary = LLMClient.get_usage_summary()

# 假设这周主要用 qwen-turbo
weekly_cost = CostCalculator.calculate(
    "qwen-turbo",
    summary['total_input_tokens'],
    summary['total_output_tokens']
)

print(f"""
周报
====
调用次数: {summary['total_calls']}
总 tokens: {summary['total_tokens']:,}
估计成本: ${weekly_cost:.6f}
""")
```

### 场景 2：多模型成本对比

```python
from examples.cost_calculator import CostCalculator

usage = 150000  # 假设总共 150k tokens（100k input, 50k output）

models = ["qwen-turbo", "qwen-max", "deepseek-chat", "gpt-4o-mini"]

print("相同 150k tokens 用不同模型的成本对比：")
for model in models:
    cost = CostCalculator.calculate(model, 100000, 50000)
    print(f"  {model:<20} ${cost:.6f}")

# 输出示例:
#   qwen-turbo          $0.000525
#   qwen-max            $0.001200
#   deepseek-chat       $0.000294
#   gpt-4o-mini         $0.000195
```

### 场景 3：成本告警

```python
from src.core.llm_client import LLMClient
from examples.cost_calculator import CostCalculator

# 成本阈值（USD）
DAILY_BUDGET = 10.0
MODEL_IN_USE = "qwen-turbo"

summary = LLMClient.get_usage_summary()
cost = CostCalculator.calculate(
    MODEL_IN_USE,
    summary['total_input_tokens'],
    summary['total_output_tokens']
)

if cost > DAILY_BUDGET:
    print(f"⚠️ 超预算！成本 ${cost:.2f} > ${DAILY_BUDGET:.2f}")
    # 发送告警、降低使用频率等
else:
    print(f"✓ 成本 ${cost:.6f}，未超预算")
```

## 📋 支持的模型

### 查看所有支持的模型和定价

```bash
python3 examples/cost_calculator.py list
```

### 当前支持（15+个模型）

| Provider | 模型 | 单位 |
|----------|------|------|
| Qwen | qwen-turbo, qwen-plus, qwen-max, qwen-long | ¥/1K |
| DeepSeek | deepseek-chat | ¥/1K |
| Doubao | doubao-pro, doubao-lite | ¥/1K |
| Kimi | moonshot-v1, moonshot-v1-8k, moonshot-v1-32k, moonshot-v1-128k | ¥/1K |
| OpenAI | gpt-4o, gpt-4o-mini, gpt-3.5-turbo | $/1K |
| Claude | claude-3-5-sonnet, claude-3-opus | $/1K |

## 🔄 定期更新定价

### 为什么需要更新？

官方定价会变化（通常会更便宜）。要保持成本计算的准确性，需要定期更新。

### 如何更新？

1. **查看官方定价**

   ```
   Qwen:    https://help.aliyun.com/zh/dashscope/developer-reference/model-square
   DeepSeek: https://platform.deepseek.com/api-docs
   OpenAI:  https://openai.com/pricing/
   ```

2. **更新代码**

   编辑 `examples/cost_calculator.py` 中的 `PRICING` 字典

   ```python
   PRICING = {
       "qwen-turbo": {"input": 0.0003, "output": 0.0009, "currency": "CNY"},
       # 如果官方更新了价格，改这里
   }
   ```

3. **验证**

   ```bash
   # 重新运行计算器，确认新定价已生效
   python3 examples/cost_calculator.py calc qwen-turbo 1000 500
   ```

## 🎯 最佳实践

### 1. 定期检查使用量

```python
# 每周运行一次
summary = LLMClient.get_usage_summary()
print(json.dumps(summary, indent=2))
```

### 2. 按 provider 分类查看

```python
summary = LLMClient.get_usage_summary()

# 看每个 provider 的使用量
for provider, stats in summary.get('by_provider', {}).items():
    print(f"{provider}: {stats['total_tokens']} tokens")
```

### 3. 基于实际模型计算

```python
# ❌ 不要这样做
cost = CostCalculator.calculate(
    "default_model",  # 可能不准确
    ...
)

# ✅ 应该这样做
cost = CostCalculator.calculate(
    "qwen-turbo",  # 实际使用的模型
    ...
)
```

### 4. 定期验证

```python
# 周初获取统计
summary_before = LLMClient.get_usage_summary()

# ... 运行一周 ...

# 周末计算成本
cost = CostCalculator.calculate(
    "your-model",
    summary_before['total_input_tokens'],
    summary_before['total_output_tokens']
)

# 与实际账单对比
# 误差应该 < 5%（除非有缓存或其他因素）
```

## 📊 数据结构参考

### get_usage_summary() 返回值

```python
{
    "total_calls": 42,              # API 调用总次数
    "total_input_tokens": 50000,    # 输入 token 总数
    "total_output_tokens": 15000,   # 输出 token 总数
    "total_tokens": 65000,          # 总 token 数
    "avg_tokens_per_call": 1547,    # 平均每次调用的 token 数
    "by_provider": {                # 按 provider 分类
        "qwen": {
            "calls": 30,
            "input_tokens": 40000,
            "output_tokens": 10000,
            "total_tokens": 50000,
            "avg_tokens_per_call": 1667,
        },
        "deepseek": {
            "calls": 12,
            "input_tokens": 10000,
            "output_tokens": 5000,
            "total_tokens": 15000,
            "avg_tokens_per_call": 1250,
        },
    }
}
```

## 🔍 常见问题

**Q: 为什么不自动计算成本？**
A: 因为定价不断变化，硬编码会过时导致误导。用户自己查最新定价更准确。

**Q: 如何知道实际用的是哪个模型？**
A: 查看 env 中的 `OPENAI_MODEL` 配置，或从应用日志查看。

**Q: 可以追踪缓存成本吗？**
A: 目前不追踪。但你可以通过对比 token 数变化来评估缓存效果。

**Q: token 数与官方显示的一样吗？**
A: 大部分情况一样，但某些情况（如 Vision API）会有差异。

**Q: 汇率怎么设置？**
A: `CostCalculator.calculate()` 的 `exchange_rate` 参数，默认 7.2。

---

需要帮助？查看完整文档：[USAGE_TRACKING_NOT_COST_TRACKING.md](./USAGE_TRACKING_NOT_COST_TRACKING.md)
