# LLM Provider 快速参考卡

## 🎯 3 秒快速开始

```bash
# 在 .env 中设置
LLM_PROVIDER_NAME=qwen          # 选择 provider
OPENAI_API_KEY=sk-xxx           # 设置 API Key

# 重启应用 ✅ 完成！
```

## 📊 Provider 对比速查表

| Provider | 成本 | 速度 | 推荐场景 | RPM |
|----------|------|------|---------|-----|
| **Qwen** ⭐ | ¥ | ⚡ | **生产环境** | 2000 |
| **DeepSeek** | ¥ | ⚡ | 成本控制 | 500 |
| **Doubao** | ¥ | ⚡ | 字节技术栈 | 1000 |
| **Kimi** | ¥¥¥¥ | ⚡⚡ | 长文本 | 60 |
| **OpenAI** | $$$ | ⚡⚡⚡ | 国际版 | 500 |
| **Claude** | $$$ | ⚡⚡ | 特殊推理 | 100 |

## 🔧 完整配置示例

### Qwen（推荐）
```bash
LLM_PROVIDER_NAME=qwen
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=qwen-turbo
```

### DeepSeek（最便宜）
```bash
LLM_PROVIDER_NAME=deepseek
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

### Doubao（字节系）
```bash
LLM_PROVIDER_NAME=doubao
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
OPENAI_MODEL=ep-20250101000000-xxxxx
```

### Kimi（长文本）
```bash
LLM_PROVIDER_NAME=kimi
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.moonshot.cn/v1
OPENAI_MODEL=moonshot-v1-128k
```

## 💰 成本计算

### 查询成本（代码）
```python
from src.core.llm_client import LLMClient

summary = LLMClient.get_usage_summary()
print(f"Total: ${summary['total_cost_usd']:.6f}")
print(f"Tokens: {summary['total_tokens']:,}")
```

### 成本预估表（1M tokens）

| Provider | 输入 | 输出 | 总计 |
|----------|------|------|------|
| Qwen | ¥300 | ¥900 | ¥1200 ≈ $167 |
| DeepSeek | ¥140 | ¥280 | ¥420 ≈ $58 |
| Doubao | ¥400 | ¥1200 | ¥1600 ≈ $222 |
| Kimi | ¥2000 | ¥6000 | ¥8000 ≈ $1111 |
| OpenAI | $0.15 | $0.60 | $0.75 |

## ⚙️ 配置速查

### 限流设置
```bash
LLM_RPM_LIMIT=0         # 0 = 自动，>0 = 覆盖
LLM_CONCURRENCY=0       # 0 = 自动，>0 = 覆盖
```

### 缓存设置
```bash
LLM_ENABLE_CACHE=true
LLM_CACHE_TTL_SECONDS=30.0
LLM_CACHE_MAX_ITEMS=512
```

### Embedding 配置
```bash
EMBED_PROVIDER=local_fastembed
FASTEMBED_MODEL=BAAI/bge-small-zh-v1.5
```

## 🧪 测试

```bash
# 测试配置是否正确
python3 examples/test_provider_config.py

# 查看所有 provider
python3 examples/test_provider_config.py | grep "可用的"

# 查看成本对比
python3 examples/test_provider_config.py | grep "成本对比" -A 10
```

## 🔀 快速切换

从 Kimi 到 DeepSeek（节省 95%）：

```bash
# 原配置
LLM_PROVIDER_NAME=kimi
OPENAI_API_KEY=sk-moonshot-xxx

# 改为
LLM_PROVIDER_NAME=deepseek
OPENAI_API_KEY=sk-deepseek-xxx
OPENAI_BASE_URL=https://api.deepseek.com/v1

# 重启 ✅
```

## 🐛 常见问题速解

| 问题 | 原因 | 解决 |
|------|------|------|
| "Unknown provider" | 拼写错误 | 检查 `LLM_PROVIDER_NAME` 的值 |
| 限流了 | 超过 RPM | 降低请求频率或增加 `LLM_RPM_LIMIT` |
| Embedding 慢 | 回退到 OpenAI | 等待本地模型加载或检查网络 |
| 成本很高 | 用了贵的 provider | 切换到 DeepSeek 或 Qwen |

## 📖 完整文档

- 详细配置：[LLM_PROVIDER_CONFIGURATION.md](docs/LLM_PROVIDER_CONFIGURATION.md)
- 迁移指南：[MIGRATION_TO_NEW_LLM_SYSTEM.md](docs/MIGRATION_TO_NEW_LLM_SYSTEM.md)
- 实现总结：[IMPLEMENTATION_SUMMARY_LLM_PROVIDERS.md](IMPLEMENTATION_SUMMARY_LLM_PROVIDERS.md)

## 🚀 Pro 技巧

### 技巧 1: 多环境配置
```bash
# .env.dev
LLM_PROVIDER_NAME=deepseek

# .env.prod
LLM_PROVIDER_NAME=qwen

# 加载指定环境
source .env.dev
```

### 技巧 2: 成本告警
```python
from src.core.llm_client import LLMClient

summary = LLMClient.get_usage_summary()
if summary['total_cost_usd'] > 100:
    send_alert(f"High cost: ${summary['total_cost_usd']}")
```

### 技巧 3: 不同任务用不同 provider
```python
# 复杂推理用 Kimi
kimi_client = LLMClient(provider_name="kimi")

# 普通任务用 DeepSeek
cheap_client = LLMClient(provider_name="deepseek")
```

---

**保存此文件以供快速参考！** 📌
