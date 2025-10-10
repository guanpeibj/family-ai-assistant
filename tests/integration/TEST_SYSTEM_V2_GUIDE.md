# FAA 集成测试系统 V2 使用指南

## 一、系统概述

### 1.1 这是什么？

FAA集成测试系统V2是一个**AI驱动的评估系统**，用于：

1. ✅ **功能验证** - 每次修改代码/Prompt后，确保核心功能正常
2. 📊 **Prompt优化** - 对比不同Prompt版本，选择最优方案
3. 🤖 **模型选择** - 对比不同LLM模型，找到最佳模型
4. 📈 **持续改进** - 跟踪评分趋势，发现退化和改进

### 1.2 核心理念

```
不测AI怎么说，测AI做了什么
用AI评估AI，支持能力进化
量化评分，可对比
```

### 1.3 三层验证体系（100分制）

```
┌─────────────────────────────────┐
│   数据层验证 (40分)              │
│   验证：AI是否正确执行了任务      │
│   方法：直接查询数据库            │
└─────────────────────────────────┘
┌─────────────────────────────────┐
│   智能层评估 (40分)              │
│   验证：AI是否聪明地理解和处理    │
│   方法：用AI评估AI（gpt-4o-mini）│
└─────────────────────────────────┘
┌─────────────────────────────────┐
│   体验层评估 (20分)              │
│   验证：AI是否提供良好用户体验    │
│   方法：用AI评估AI（gpt-4o-mini）│
└─────────────────────────────────┘
```

---

## 二、快速开始

### 2.1 运行单个测试文件（新框架）

```bash
cd /path/to/family-ai-assistant

# 运行P0记账测试（新框架示例）
python tests/integration/test_p0_accounting_v2.py
```

**输出示例**：
```
================================================================================
[TC001] 简单记账-完整信息
================================================================================
📝 输入：今天买菜花了80元

🤖 AI回复：
已记录您的支出：买菜80元，归入餐饮类目。

⏱️  耗时：7.23秒

📊 数据层验证中...
   分数: 38.0/40
🧠 智能层评估中...
   分数: 36.5/40
✨ 体验层评估中...
   分数: 17.0/20

================================================================================
✅ 测试通过 - 总分: 91.5/100 (等级A)
   数据层: 38.0/40
   智能层: 36.5/40
   体验层: 17.0/20
================================================================================
```

### 2.2 运行黄金测试集

```bash
# 运行完整黄金测试集（50个用例）
python tests/integration/run_golden_set.py

# 快速测试（只运行前10个）
python tests/integration/run_golden_set.py --limit 10

# 指定输出目录
python tests/integration/run_golden_set.py --output-dir ./my_reports
```

**输出**：
- JSON报告：`reports/golden_20251010_143000.json`
- 文本报告：`reports/golden_20251010_143000.txt`

### 2.3 运行AB测试

```bash
# 对比两个Prompt版本
python tests/integration/run_ab_test.py \
  --variant-a '{"name":"v4_default","prompt":"v4_default"}' \
  --variant-b '{"name":"v4_optimized","prompt":"v4_optimized"}' \
  --limit 20

# 对比两个模型
python tests/integration/run_ab_test.py \
  --variant-a '{"name":"GPT-4","model":"gpt-4"}' \
  --variant-b '{"name":"Claude","model":"claude-sonnet-4-20250514"}' \
  --limit 20
```

**输出**：
```
🅰️  变体A (v4_default):
   平均分: 87.5/100
   通过率: 95.0%
   平均耗时: 12.3秒

🅱️  变体B (v4_optimized):
   平均分: 85.2/100
   通过率: 90.0%
   平均耗时: 8.5秒

📊 差异:
   分数: -2.3
   耗时: -3.8秒
   通过率: -5.0%

💡 推荐:
   选择: 变体B (v4_optimized)
   理由: 速度显著更快（3.8秒），质量差异可接受
   置信度: 75%
```

---

## 三、编写测试用例

### 3.1 测试用例结构

每个测试用例需要包含：

```python
await self.run_test(
    # 基本信息
    test_id="TC001",
    test_name="简单记账-完整信息",
    message="今天买菜花了80元",  # 用户输入
    
    # 预期行为（人类语言描述，不是具体措辞）
    expected_behavior={
        "intent": "记录支出",
        "key_actions": ["存储账目", "识别类目为餐饮", "记录金额80元"],
        "response_should": "确认记账成功，告知类目和金额"
    },
    
    # 数据层验证规则（可选）
    data_verification={
        "should_store": True,
        "expected_data": {
            "type": "expense",
            "amount": 80.0,
            "category": "餐饮",
            "occurred_at": "today"
        },
        "tolerance": {
            "amount": 0,  # 金额必须精确
            "category": ["餐饮", "食品"]  # 类目可接受范围
        },
        "required_fields": ["type", "category", "amount"]
    },
    
    # 智能层和体验层会自动用AI评估
)
```

### 3.2 创建新的测试文件

```python
#!/usr/bin/env python3
"""
测试套件描述
"""

import asyncio
from base_new import IntegrationTestBase


class MyTestSuite(IntegrationTestBase):
    """我的测试套件"""
    
    def __init__(self):
        super().__init__(test_suite_name="my_suite")
    
    async def test_case_001(self):
        """测试用例1"""
        await self.run_test(
            test_id="TC001",
            test_name="测试名称",
            message="用户输入",
            expected_behavior={...},
            data_verification={...}
        )


async def main():
    tester = MyTestSuite()
    
    if not await tester.setup():
        return 1
    
    try:
        await tester.test_case_001()
        # ... 更多测试
        
        tester.print_summary()
        return 0
    finally:
        await tester.teardown()


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
```

---

## 四、黄金测试集

### 4.1 什么是黄金测试集？

黄金测试集是50个最具代表性的测试用例，用于：
- AB测试的标准对比集
- 模型选择的基准集
- 快速验证核心功能

### 4.2 黄金测试集结构

位置：`tests/integration/test_cases/golden_set.yaml`

包含8大类共50个用例：
1. 基础记账 (10个) - TC001-TC010
2. 查询功能 (10个) - TC011-TC020
3. 提醒功能 (5个) - TC021-TC025
4. 健康记录 (5个) - TC026-TC030
5. 预算管理 (5个) - TC031-TC035
6. 信息管理 (5个) - TC036-TC040
7. 澄清对话 (5个) - TC041-TC045
8. 边界情况 (5个) - TC046-TC050

### 4.3 添加新用例到黄金集

编辑 `test_cases/golden_set.yaml`：

```yaml
my_new_category:
  - test_id: "TC051"
    test_name: "我的测试"
    priority: "P0"
    difficulty: "simple"
    user_input: "测试输入"
    expected_behavior:
      intent: "意图"
      key_actions: ["动作1", "动作2"]
      response_should: "应该怎样回复"
    data_verification:
      should_store: true
      expected_data:
        type: "expense"
        amount: 100.0
```

---

## 五、评分系统详解

### 5.1 数据层（40分）

自动评分，程序直接查询数据库：

| 项目 | 满分 | 评分规则 |
|-----|------|---------|
| 数据存储 | 10 | 有记录=10，无记录=0 |
| 金额准确 | 5 | 精确=5，误差<10%=3，误差>10%=0 |
| 类目正确 | 5 | 完全正确=5，可接受=3，错误=0 |
| 时间合理 | 5 | 准确=5，近似=3，错误=0 |
| 数据结构 | 10 | 字段完整+关联正确+AI扩展 |
| 幂等性 | 5 | 无重复=5 |

### 5.2 智能层（40分）

AI评估，使用gpt-4o-mini评分：

| 维度 | 满分 | 评分标准 |
|-----|------|---------|
| 意图理解 | 10 | 9-10=完全理解，7-8=基本理解，5-6=不准确，0-2=误解 |
| 信息提取 | 10 | 9-10=完整准确，7-8=大部分，5-6=遗漏，0-2=错误 |
| 上下文运用 | 10 | 9-10=充分利用，7-8=有运用，5-6=很少，0-2=忽略 |
| 回复相关性 | 10 | 9-10=切题有价值，7-8=相关，5-6=偏题，0-2=无关 |

### 5.3 体验层（20分）

AI评估，使用gpt-4o-mini评分：

| 维度 | 满分 | 评分标准 |
|-----|------|---------|
| 人设契合 | 5 | 5=完全符合老管家，3-4=基本符合，0-2=不符 |
| 语言质量 | 5 | 5=简洁礼貌，3-4=合格，0-2=啰嗦/混乱 |
| 信息完整 | 5 | 5=完整，3-4=基本完整，0-2=不完整 |
| 用户友好 | 5 | 5=易懂有用，3-4=可用，0-2=困惑 |

### 5.4 及格标准

- **单个测试**：总分≥60，数据层≥24（60%）
- **测试套件**：通过率≥80%，平均分≥70
- **黄金测试集**：通过率≥90%，平均分≥80

---

## 六、报告解读

### 6.1 单次测试报告

JSON报告包含：

```json
{
  "test_run_id": "golden_20251010_143000",
  "config": {
    "prompt_version": "v4_optimized",
    "llm_model": "gpt-4"
  },
  "summary": {
    "total_cases": 50,
    "passed": 45,
    "pass_rate": 0.90,
    "avg_total_score": 85.2,
    "avg_data_score": 36.5,
    "avg_intelligence_score": 34.0,
    "avg_experience_score": 14.7
  },
  "dimension_averages": {
    "intent_understanding": 8.5,
    "information_extraction": 8.3,
    ...
  },
  "failed_cases": [...],
  "performance": {
    "avg_response_time": 8.5,
    "p95": 15.3
  }
}
```

### 6.2 AB对比报告

重点关注：

1. **分数差异** - 哪个变体质量更高？
2. **耗时差异** - 哪个变体速度更快？
3. **显著性** - 差异是否显著？
4. **推荐结果** - 系统综合推荐哪个？

**决策规则**：
- 质量权重70%，速度权重30%
- 分数差异≥3分认为显著
- 耗时差异≥2秒认为显著

---

## 七、最佳实践

### 7.1 日常开发流程

```bash
# 1. 修改代码或Prompt
vim prompts/family_assistant_prompts.yaml

# 2. 快速验证（运行部分用例）
python tests/integration/run_golden_set.py --limit 10

# 3. 确认通过后完整测试
python tests/integration/run_golden_set.py

# 4. 提交代码
git add .
git commit -m "优化Prompt"
```

### 7.2 Prompt优化流程

```bash
# 1. 准备两个Prompt版本
# - prompts/family_assistant_prompts.yaml (v4_default)
# - prompts/family_assistant_prompts.yaml (v4_optimized)

# 2. AB测试对比
python tests/integration/run_ab_test.py \
  --variant-a '{"name":"v4_default","prompt":"v4_default"}' \
  --variant-b '{"name":"v4_optimized","prompt":"v4_optimized"}' \
  --limit 30

# 3. 查看报告，决策使用哪个版本
cat tests/integration/reports/ab_*.txt

# 4. 如果B更好，切换到B
# 修改配置使用v4_optimized
```

### 7.3 模型选择流程

```bash
# 对比不同模型
python tests/integration/run_ab_test.py \
  --variant-a '{"name":"GPT-4","model":"gpt-4"}' \
  --variant-b '{"name":"Claude","model":"claude-sonnet-4-20250514"}' \
  --limit 30

# 查看性价比
# GPT-4: 87.5分, 8.5秒, $1.50
# Claude: 89.2分, 7.8秒, $0.75
# → 推荐Claude
```

### 7.4 CI/CD集成

```yaml
# .github/workflows/test.yml
name: Integration Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Setup
        run: |
          docker-compose up -d
          sleep 15
      
      - name: Run Golden Set
        run: |
          docker-compose exec -T faa-api \
            python tests/integration/run_golden_set.py --limit 20
      
      - name: Upload Reports
        uses: actions/upload-artifact@v2
        with:
          name: test-reports
          path: tests/integration/reports/
```

---

## 八、成本控制

### 8.1 成本预估

**黄金测试集（50个用例）**：
- 主AI调用：50次 × $0.03 = **$1.50**
- 评估AI调用：50次 × $0.003 = **$0.15**
- **总成本：约$1.65 / 次**

**AB测试（30个用例对比）**：
- 两个变体：30 × 2 = 60次主AI调用
- 评估：60次评估AI调用
- **总成本：约$2.00 / 次**

### 8.2 节约成本的方法

1. **使用limit参数** - 快速测试时只运行部分用例
   ```bash
   --limit 10  # 只跑10个，成本降到$0.35
   ```

2. **使用缓存** - AI评估结果自动缓存，相同回复不重复评估

3. **分级测试** - P0每次必测，P1/P2按需测试

---

## 九、常见问题

### Q1: 测试为什么这么慢？

A: 每个测试需要：
1. 调用主AI（5-10秒）
2. 调用评估AI两次（2-4秒）
3. 数据库查询（<1秒）

总计约8-15秒/用例。50个用例需要约10-15分钟。

**解决方案**：
- 日常开发用`--limit 10`快速测试
- 完整测试在提交前或CI/CD中运行

### Q2: 评分不稳定怎么办？

A: AI评估有一定随机性（已设置低温度0.3），可能±1-2分波动。

**解决方案**：
- 关注趋势而非单次绝对值
- 多次运行取平均
- 只关注显著差异（±3分以上）

### Q3: 如何判断一个测试失败是AI问题还是测试问题？

A: 查看详细评分：
- 数据层低分 → AI没正确执行任务 → **AI问题**
- 数据层高分但智能层低分 → AI执行了但不够智能 → **AI问题**
- 所有层都低分 → 可能**测试用例设计问题**

### Q4: 现有的旧测试文件怎么办？

A: 两种选择：
1. **保留旧测试** - 作为快速检查，不计入评分
2. **迁移到新框架** - 参考`test_p0_accounting_v2.py`改写

建议：核心P0用例迁移到新框架，其他保留旧版本。

---

## 十、总结

### 核心价值

1. **客观量化** - 100分制，可对比
2. **AI驱动** - 用AI评估AI，不限制表达
3. **成本可控** - 精心设计，每次<$2
4. **持续改进** - 跟踪趋势，数据驱动

### 推荐工作流

```
日常开发：
├─ 修改代码/Prompt
├─ 快速测试（10个用例，$0.35）
├─ 通过后完整测试（50个用例，$1.65）
└─ 提交代码

Prompt优化：
├─ 准备两个版本
├─ AB测试（30个用例，$2.00）
├─ 查看推荐
└─ 切换到更优版本

模型选择：
├─ 对比候选模型
├─ AB测试（30个用例，$2.00）
├─ 综合考虑质量/速度/成本
└─ 选择最佳模型
```

---

**文档版本**: 1.0  
**最后更新**: 2025-10-10  
**维护者**: FAA测试团队

