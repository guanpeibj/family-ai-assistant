# FAA 集成测试完整指南

> **最后更新**：2025-10-11  
> **版本**：V2.1 - 支持多轮对话

## 📋 目录

1. [快速开始](#快速开始)
2. [核心特性](#核心特性)
3. [测试用例编写](#测试用例编写)
4. [运行测试](#运行测试)
5. [报告分析](#报告分析)
6. [最佳实践](#最佳实践)

---

## 🚀 快速开始

### 配置评估器LLM（可选）

测试系统使用独立的评估器LLM（用AI评估AI），默认配置已经优化：

```bash
# .env 文件中的配置（通常不需要修改）
EVALUATOR_LLM_PROVIDER=openai_compatible
EVALUATOR_LLM_MODEL=gpt-4o-mini
EVALUATOR_LLM_BASE_URL=https://api.openai.com/v1
# EVALUATOR_LLM_API_KEY=  # 留空则使用OPENAI_API_KEY
```

**为什么独立配置？**
- 主项目可以使用任意LLM（kimi、claude等）
- 评估器使用成本最优的模型（gpt-4o-mini）
- 不影响主项目的模型选择
- LLMClient支持参数化初始化，简洁优雅

### 30秒运行测试

```bash
cd /Users/guanpei/Develop/family-ai-assistant/tests/integration

# 运行所有测试（单轮 + 多轮）
python run_golden_set.py

# 只运行单轮测试
python run_golden_set.py --no-multi-turn

# 快速验证（限制10个用例）
python run_golden_set.py --limit 10
```

---

## 🎯 核心特性

### 1. 三层验证体系（100分制）

```
📊 数据层 (40分) → 验证AI是否正确存储数据
🧠 智能层 (40分) → AI评估AI的理解能力  
✨ 体验层 (20分) → AI评估用户体验质量
```

### 2. 成本优化

- **数据层<90%时跳过AI评估**：节省约30%成本
- **多轮测试只评估最后一轮**：避免重复评估
- **评估器独立配置LLM**：默认使用gpt-4o-mini（成本低、速度快），可在.env中配置

### 3. 支持单轮和多轮对话

- **单轮测试**：适合独立功能验证
- **多轮测试**：适合真实对话场景（追问、澄清、修改）

### 4. 完整对话记录

每次测试都记录完整对话，格式：
```json
{
  "conversation": [
    "user(xxx-xxx-xxx)- 今天买菜花了80元",
    "faa- 好的，已为您记录食材支出80元"
  ]
}
```

---

## 📝 测试用例编写

### golden_set.yaml 文件结构

```yaml
test_suite_name: "golden_set"
test_suite_version: "1.2"
total_cases: 61  # 55个单轮 + 6个多轮

# ===== 单轮测试 =====
accounting_basic:
  - test_id: "TC001"
    test_name: "简单记账-完整信息"
    priority: "P0"
    difficulty: "simple"
    user_input: "今天买菜花了80元"
    expected_behavior:
      intent: "记录支出"
      key_actions: ["存储账目", "识别类目为食材", "记录金额80元"]
      response_should: "确认记账成功，告知类目和金额"
    data_verification:
      should_store: true
    expected_data:
      type: "expense"
      amount: 80.0
      category: "食材"
      sub_category: "蔬菜"
      occurred_at: "today"
    tolerance:
      amount: 0
    required_fields: ["type", "category", "sub_category", "amount"]

# ===== 多轮对话测试 =====
multi_turn_tests:
  - test_id: "MT001"
    test_name: "多轮记账-追问补全信息"
    priority: "P0"
    difficulty: "medium"
    turns:  # 多轮定义
      - turn: 1
        user_input: "记账，花了100元"
        expected_behavior:
          intent: "记账意图，但信息不完整"
          key_actions: ["识别缺少类目信息", "主动追问"]
          response_should: "询问购买了什么或支出类目"
        data_verification:
          should_store: false  # 第一轮不应该存储
      
      - turn: 2
        user_input: "买了手套，送给妻子"
        expected_behavior:
          intent: "补全信息并完成记账"
          key_actions: ["存储账目", "关联到妻子", "识别为衣服或日用品"]
          response_should: "确认记账成功，告知金额和类目"
          data_verification:
            should_store: true
            expected_data:
              type: "expense"
              amount: 100.0
              category: "衣服"
              occurred_at: "today"
            tolerance:
              amount: 0
```

### 字段说明

#### 单轮测试字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `test_id` | ✅ | 测试ID，格式：TC001, TC002... |
| `test_name` | ✅ | 测试名称，简洁描述 |
| `priority` | ✅ | 优先级：P0/P1/P2 |
| `difficulty` | ✅ | 难度：simple/medium/complex |
| `user_input` | ✅ | 用户输入内容 |
| `expected_behavior` | ✅ | 预期行为描述 |
| `data_verification` | ⚠️  | 数据层验证规则（可选） |
| `context` | ⚪ | 额外上下文（可选） |

#### expected_behavior 详细说明

```yaml
expected_behavior:
  intent: "AI应该识别的意图"
  key_actions: ["关键动作1", "关键动作2", "关键动作3"]
  response_should: "AI回复应该包含的内容或做的事"
```

#### data_verification 详细说明

```yaml
data_verification:
  should_store: true  # 是否应该存储数据
  expected_data:      # 预期的数据内容
    type: "expense"   # 记录类型
    amount: 80.0      # 金额
    category: "食材"  # 一级类目
    sub_category: "蔬菜"  # 二级类目
    occurred_at: "today"  # 时间（today/recent/last_month_28等）
  tolerance:          # 容差范围
    amount: 0         # 金额容差（0表示必须精确）
    sub_category: ["蔬菜"]  # （可选）允许的子类目取值
  required_fields: ["type", "category", "sub_category", "amount"]  # 必须字段
```

- 如果配置中存在子类目，expected_data 必须同时填写 `category` 与 `sub_category`，并在 `required_fields` 中加入 `sub_category`，确保一级/二级类目都被验证。

#### 多轮测试字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `test_id` | ✅ | 测试ID，格式：MT001, MT002... |
| `test_name` | ✅ | 测试名称 |
| `turns` | ✅ | 轮次列表 |

每个`turn`包含：
- `turn`: 轮次编号（1, 2, 3...）
- `user_input`: 用户输入
- `expected_behavior`: 预期行为
- `data_verification`: 数据验证（可选）

### 编写测试用例的最佳实践

#### 1. 单轮测试用例

**适用场景**：
- 独立的功能验证
- 不需要上下文的操作
- 快速回归测试

**示例：简单记账**

```yaml
- test_id: "TC001"
  test_name: "简单记账-完整信息"
  priority: "P0"
  difficulty: "simple"
  user_input: "今天买菜花了80元"
  expected_behavior:
    intent: "记录支出"
    key_actions: ["存储账目", "识别类目为食材", "记录金额80元"]
    response_should: "确认记账成功，告知类目和金额"
  data_verification:
    should_store: true
    expected_data:
      type: "expense"
      amount: 80.0
      category: "食材"
      sub_category: "蔬菜"
      occurred_at: "today"
    required_fields: ["type", "category", "sub_category", "amount"]
```

#### 2. 多轮测试用例

**适用场景**：
- 需要追问澄清的场景
- 信息分步输入
- 修改已有信息
- 连续的对话上下文

**示例：追问补全信息**

```yaml
- test_id: "MT001"
  test_name: "多轮记账-追问补全信息"
  priority: "P0"
  difficulty: "medium"
  turns:
    - turn: 1
      user_input: "记账，花了100元"
      expected_behavior:
        intent: "记账意图，但信息不完整"
        key_actions: ["识别缺少类目信息", "主动追问"]
        response_should: "询问购买了什么或支出类目"
      data_verification:
        should_store: false  # 第一轮不应该存储
    
    - turn: 2
      user_input: "买了手套，送给妻子"
      expected_behavior:
        intent: "补全信息并完成记账"
        key_actions: ["存储账目", "识别为衣服或日用品"]
        response_should: "确认记账成功"
      data_verification:
        should_store: true
        expected_data:
          type: "expense"
          amount: 100.0
          category: "衣服"
        tolerance:
          amount: 0
```

**示例：修改信息**

```yaml
- test_id: "MT002"
  test_name: "多轮提醒-修改时间"
  priority: "P0"
  difficulty: "medium"
  turns:
    - turn: 1
      user_input: "提醒我，大女儿家长会在下周三"
      expected_behavior:
        intent: "设置提醒"
        key_actions: ["存储提醒", "识别大女儿", "识别时间为下周三"]
        response_should: "确认提醒已设置"
      data_verification:
        should_store: true
        expected_data:
          type: "reminder"
    
    - turn: 2
      user_input: "学校通知，改到下周五了"
      expected_behavior:
        intent: "修改提醒时间"
        key_actions: ["更新提醒时间", "识别为下周五"]
        response_should: "确认时间已修改"
      data_verification:
        should_store: true  # 应该更新记录
    
    - turn: 3
      user_input: "大女儿家长会是哪天？"
      expected_behavior:
        intent: "查询提醒"
        key_actions: ["查询相关提醒", "返回正确时间"]
        response_should: "回答下周五"
      data_verification:
        should_store: false
```

#### 3. 测试用例分类建议

建议按功能模块分类：

```yaml
# 基础记账（10个）
accounting_basic:
  - TC001: 简单记账
  - TC002: 大额支出
  - TC003-TC010: 类目映射

# 查询功能（10个）
query_basic:
  - TC011: 本月支出查询
  - TC012: 类目查询
  - TC013-TC020: 其他查询

# 提醒功能（5个）
reminder:
  - TC021: 创建提醒
  - TC022-TC025: 查询/修改提醒

# 健康记录（5个）
health:
  - TC026-TC030: 健康数据记录和查询

# 预算管理（5个）
budget:
  - TC031-TC035: 预算设置和查询

# 信息管理（5个）
information:
  - TC036-TC040: 信息存储和查询

# 澄清对话（5个）
clarification:
  - TC041-TC045: 缺失信息追问

# 边界情况（5个）
edge_cases:
  - TC046-TC050: 特殊情况处理

# 多轮对话（6个）
multi_turn_tests:
  - MT001-MT006: 多轮场景
```

---

## 🏃 运行测试

### 命令行选项

```bash
# 运行所有测试
python run_golden_set.py

# 限制数量（快速测试）
python run_golden_set.py --limit 10

# 跳过多轮测试（只运行单轮）
python run_golden_set.py --no-multi-turn

# 指定输出目录
python run_golden_set.py --output-dir ./custom_reports

# 传递配置参数
python run_golden_set.py --config '{"prompt_version":"v4"}'
```

### 测试执行流程

```
1. 加载测试用例（golden_set.yaml）
2. 初始化AI引擎和数据库
3. 逐个执行测试用例
   - 发送消息给AI引擎
   - 三层验证（数据/智能/体验）
   - 记录评分和对话
4. 生成测试报告
5. 打印总结
```

### 多轮测试优化

- ✅ **独立线程ID**：每个多轮测试使用独立的`thread_id`，避免污染
- ✅ **每轮验证反馈**：实时显示每轮的数据验证结果
- ✅ **只评估最后一轮**：智能层和体验层只评估最后一轮，节省成本
- ✅ **提前终止支持**：如果某轮严重失败，可以选择提前终止（`fail_fast=True`）

---

## 📊 报告分析

### 报告文件

测试完成后会生成两个文件：

```
tests/integration/reports/
├── golden_20251011_131901.json  # 完整数据
└── golden_20251011_131901.txt   # 人类可读摘要
```

### JSON报告结构

```json
{
  "test_run_id": "golden_20251011_131901",
  "timestamp": "2025-10-11T13:19:01",
  "version_info": {
    "test_date": "2025-10-11 13:19:01",
    "llm": {
      "provider": "openai_compatible",
      "model": "kimi-k2-0905-preview",
      "embedding_provider": "local_fastembed",
      "embedding_model": "BAAI/bge-small-zh-v1.5"
    },
    "evaluator_llm": {
      "provider": "openai",
      "model": "gpt-4o-mini",
      "base_url": "https://api.openai.com/v1"
    },
    "prompts": {
      "version": "4.1",
      "current_profile": "v4_optimized"
    }
  },
  "config": {
    "test_suite": "golden_set",
    "test_file": "run_golden_set.py"
  },
  "summary": {
    "total_cases": 61,
    "passed": 58,
    "failed": 3,
    "pass_rate": 0.95,
    "avg_total_score": 89.2,
    "avg_data_score": 37.5,
    "avg_intelligence_score": 34.8,
    "avg_experience_score": 16.9
  },
  "test_scores": [
    {
      "test_id": "TC001",
      "test_name": "简单记账-完整信息",
      "data_score": 38,
      "intelligence_score": 35,
      "experience_score": 18,
      "total_score": 91,
      "conversation": [
        "user(xxx-xxx)- 今天买菜花了80元",
        "faa- 好的，已为您记录食材支出80元"
      ],
      "duration": 24.5,
      "success": true,
      "issues": []
    }
  ]
}
```

### TXT报告示例

```
================================================================================
FAA 集成测试报告
================================================================================
运行ID: golden_20251011_131901
时间: 2025-10-11T13:19:01

版本信息:
  测试时间: 2025-10-11 13:19:01
  主项目LLM: openai_compatible / kimi-k2-0905-preview
  Embedding: local_fastembed / BAAI/bge-small-zh-v1.5
  评估器LLM: gpt-4o-mini
  Prompts版本: 4.1 (v4_optimized)

总体统计:
  总测试数: 61
  ✅ 通过: 58 (95.1%)
  ❌ 失败: 3
  ⏱️  总耗时: 1845.2秒
  📈 平均耗时: 30.2秒

平均分数:
  总分: 89.2/100
  数据层: 37.5/40
  智能层: 34.8/40
  体验层: 16.9/20

失败用例 (3):
  1. [TC028] 健康查询 - 41.0分
     问题: 未找到记录，需要先录入数据
  2. [MT003] 多轮查询-澄清对象 - 55.0分
     问题: 第一轮未能识别需要澄清
  3. [TC050] 超长输入 - 58.0分
     问题: 金额提取不准确
================================================================================
```

### 关键指标说明

| 指标 | 说明 | 目标值 |
|------|------|--------|
| 通过率 | passed / total_cases | ≥ 90% |
| 平均总分 | avg_total_score | ≥ 80分 |
| 数据层分数 | avg_data_score | ≥ 36分（90%） |
| 智能层分数 | avg_intelligence_score | ≥ 32分（80%） |
| 体验层分数 | avg_experience_score | ≥ 16分（80%） |

---

## 💡 最佳实践

### 1. 测试用例设计原则

✅ **DO**：
- 覆盖真实使用场景（来自readme.MD）
- 多轮测试优于单轮测试（更接近真实对话）
- 预期行为要清晰具体
- 数据验证要严格

❌ **DON'T**：
- 不要测试AI的具体措辞（让AI自由发挥）
- 不要过度依赖关键词匹配
- 不要设置过于严格的tolerance

### 2. 多轮测试设计建议

**场景识别**：
- 需要追问 → 多轮测试
- 需要修改 → 多轮测试
- 需要澄清 → 多轮测试
- 独立操作 → 单轮测试

**轮次设置**：
- 2-3轮最佳（测试对话能力）
- 避免超过5轮（成本和时间）

**验证策略**：
- 第一轮通常不存储（追问场景）
- 最后一轮必须验证（完整性）
- 中间轮可以简化验证

### 3. 成本控制

**节省成本的方法**：
1. 数据层<90%时自动跳过AI评估（已实现）
2. 多轮测试只评估最后一轮（已实现）
3. 使用`--limit`快速验证
4. 使用`--no-multi-turn`跳过多轮测试
5. 评估器使用gpt-4o-mini（已实现）

**成本估算**：
- 单轮测试：约$0.02/用例
- 多轮测试：约$0.03-0.05/用例
- 50个单轮 + 6个多轮：约$1.2

### 4. 持续集成

**每次提交代码后运行**：
```bash
# 快速验证（5分钟）
python run_golden_set.py --limit 20

# 完整测试（每天一次）
python run_golden_set.py
```

**AB测试对比**：
```bash
# 对比不同配置
python run_ab_test.py --variant-a "v4" --variant-b "v4.1"
```

---

## 🔧 故障排查

### 常见问题

#### 1. 测试失败率高

**可能原因**：
- AI模型能力不足
- Prompts配置不当
- 数据验证规则过严

**解决方案**：
- 查看失败用例的conversation字段
- 分析data_details和intelligence_details
- 调整tolerance和expected_data

#### 2. 数据层评分低

**可能原因**：
- AI没有正确存储数据
- 数据字段不匹配
- 时间识别错误

**解决方案**：
- 检查MCP工具是否正常
- 查看data_details中的actual vs expected
- 调整Prompts中的工具使用指南

#### 3. 智能层或体验层评分低

**可能原因**：
- AI理解不准确
- 回复不够专业
- 未遵循人设

**解决方案**：
- 查看intelligence_details中的reasoning
- 查看experience_details中的suggestions
- 调整Prompts中的人设定义

#### 4. 多轮测试失败

**可能原因**：
- 上下文丢失
- 线程混乱
- 追问逻辑不对

**解决方案**：
- 检查thread_id是否一致
- 查看每轮的对话记录
- 调整Prompts中的澄清策略

---

## 📚 参考资料

- [项目核心理念](../../readme.MD)
- [Prompts配置](../../prompts/family_assistant_prompts.yaml)
- [AI引擎实现](../../src/ai_engine.py)
- [MCP工具服务](../../mcp-server/generic_mcp_server.py)

---

## 🎯 设计理念

本测试系统遵循FAA的三个核心原则：

1. **以readme.MD为导向**：测试用例覆盖所有实际使用场景
2. **AI驱动**：不测AI怎么说，测AI做了什么；用AI评估AI
3. **简洁直接稳定**：代码简洁，逻辑清晰，不过度设计

**核心价值**：
- ✅ 工程代码固定，能力随AI进化
- ✅ 每次测试都充分利用（记录完整对话）
- ✅ 成本可控，效果可衡量
- ✅ 支持单轮和多轮，贴近真实场景

---

**祝测试愉快！有问题请查看报告中的详细分析。** 🎉
