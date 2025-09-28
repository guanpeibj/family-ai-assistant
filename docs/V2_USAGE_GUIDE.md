# FAA V2 使用指南

## 🚀 重构后的新功能使用说明

经过全面重构，FAA V2 提供了更强大的功能和更好的开发体验。本指南将帮你充分利用这些新能力。

## 📋 快速验证重构成功

### 1. 运行验证测试
```bash
# 进入项目目录
cd /Users/guanpei/Develop/family-ai-assistant

# 运行重构验证测试
python tests/test_refactored_engine.py
```

### 2. 检查新文件结构
```bash
# 查看新增的核心模块
ls -la src/core/
# 应该看到：
# - exceptions.py    (异常处理体系)
# - tool_helper.py   (工具辅助模块)  
# - ab_testing.py    (A/B 测试框架)

# 查看备份文件
ls -la src/ai_engine_backup.py  # 原版本备份
```

## 🧪 A/B 测试使用指南

### 创建实验版本

1. **在 prompts.yaml 中定义新版本**
```yaml
# prompts/family_assistant_prompts.yaml
prompts:
  v4_default:
    # 现有默认版本
    
  v4_friendly:  # 🆕 新的实验版本
    name: "友善对话版本"
    description: "测试更友善的对话风格"
    inherits: "v4_default"
    profiles:
      default:
        response_blocks: [response_contract, response_voice_friendly]
        
blocks:
  response_voice_friendly: |
    回复语气：温暖、亲切、鼓励性，多使用表情符号(😊🌟💖)增加亲和力。
    像家庭中的贴心管家一样，关心家庭成员的感受。
```

2. **创建和启动实验**
```python
# examples/create_experiment.py
from src.core.ab_testing import ABTestingManager, ExperimentConfig, ExperimentStatus

ab_manager = ABTestingManager()

# 创建友善风格实验
config = ExperimentConfig(
    id="friendly_style_test",
    name="友善对话风格实验",
    description="测试更友善的对话风格是否提升用户满意度",
    status=ExperimentStatus.RUNNING,
    
    control_version="v4_default",
    treatment_versions=["v4_friendly"],
    
    traffic_allocation={
        "control": 70,      # 70% 用户使用默认版本
        "treatment_0": 30   # 30% 用户测试友善版本
    },
    
    target_channels=["threema"],
    max_duration_hours=168,  # 运行一周
    max_error_rate=0.05      # 错误率超过5%自动暂停
)

success = ab_manager.create_experiment(config)
print(f"实验创建: {'成功' if success else '失败'}")
```

3. **运行实验演示**
```bash
# 体验完整的 A/B 测试流程
python examples/ab_testing_example.py
```

### 监控实验结果

```python
# 获取实验统计
stats = ab_manager.get_experiment_stats("friendly_style_test")

print(f"实验: {stats['name']}")
print(f"总样本: {stats['total_samples']}")

for variant, metrics in stats['variants'].items():
    print(f"{variant}: 成功率 {metrics['success_rate']*100:.1f}%")
```

## 🛡️ 异常处理使用

### 自定义异常处理
```python
from src.core.exceptions import AIEngineError, MCPToolError, get_user_friendly_message

try:
    # 你的业务逻辑
    result = await ai_engine.process_message(content, user_id)
except AIEngineError as e:
    # 记录详细错误信息
    logger.error("ai_engine.error", **e.to_dict())
    
    # 返回用户友好消息
    user_message = get_user_friendly_message(e)
    return {"success": False, "message": user_message}
except MCPToolError as e:
    # 工具调用错误的特殊处理
    logger.error("mcp_tool.error", tool=e.context.get('tool_name'), **e.to_dict())
    return {"success": False, "message": "操作暂时不可用，请稍后重试"}
```

### 创建自定义异常
```python
from src.core.exceptions import FAError

class CustomBusinessError(FAError):
    """自定义业务异常"""
    pass

# 使用时提供丰富上下文
raise CustomBusinessError(
    "自定义错误描述",
    error_code="CUSTOM_001",
    trace_id=trace_id,
    user_id=user_id,
    context={"business_data": "additional_info"}
)
```

## 📊 性能监控使用

### 查看工具调用统计
```python
# 获取工具执行统计
from src.ai_engine import ai_engine

monitor = ai_engine.tool_executor.execution_monitor
stats = monitor.get_all_stats()

for stat in stats:
    print(f"工具 {stat['tool_name']}:")
    print(f"  调用次数: {stat['total_calls']}")
    print(f"  成功率: {stat['success_rate']*100:.1f}%")  
    print(f"  平均耗时: {stat['avg_duration_ms']:.0f}ms")
```

### 查看缓存状态
```python
# 检查向量缓存效果
cache_size = len(ai_engine._emb_cache_global)
print(f"全局向量缓存: {cache_size} 项")

# 检查当前活跃的 trace
active_traces = len(ai_engine._emb_cache_by_trace)
print(f"活跃追踪: {active_traces} 个")
```

## 🔧 开发与调试

### 启用详细日志
```python
# 在代码中启用更详细的日志
import structlog

logger = structlog.get_logger(__name__)

# 重构后的日志包含完整的上下文
logger.info(
    "custom.operation",
    trace_id=trace_id,
    user_id=user_id,
    operation="your_operation",
    details={"key": "value"}
)
```

### 追踪请求流程
```python
# 每个请求都有唯一的 trace_id
# 可以通过 trace_id 追踪整个处理流程：

# 1. message.received (请求到达)
# 2. ai.analysis.start (AI 分析开始)
# 3. tool.call.start (工具调用开始)
# 4. tool.call.end (工具调用结束)
# 5. response.generated (响应生成)
# 6. message.completed (处理完成)
```

### 单元测试新模块
```python
# 测试工具能力分析器
from src.core.tool_helper import ToolCapabilityAnalyzer

async def test_tool_analyzer():
    analyzer = ToolCapabilityAnalyzer()
    
    # 模拟 HTTP 客户端
    mock_client = AsyncMock()
    mock_client.get.return_value.json.return_value = {
        "tools": [
            {
                "name": "store",
                "x_capabilities": {"uses_database": True},
                "x_time_budget": 2.0
            }
        ]
    }
    
    # 测试能力判断
    requires_user = await analyzer.requires_user_id("store", mock_client, "http://test")
    assert requires_user
    
    time_budget = await analyzer.get_time_budget("store", mock_client, "http://test")
    assert time_budget == 2.0
```

## 📈 性能优化建议

### 1. 向量缓存调优
```python
# 在环境变量中调整缓存参数
export EMB_CACHE_MAX_ITEMS=2000      # 增加缓存容量
export EMB_CACHE_TTL_SECONDS=7200    # 延长缓存时间
```

### 2. 工具时间预算优化
```python
# 在 MCP 工具定义中设置时间预算
{
  "name": "your_tool",
  "x_time_budget": 1.5,    # 秒
  "x_latency_hint": "low"  # low/medium/high
}
```

### 3. A/B 测试配置优化
```python
# 调整实验安全参数
config.max_error_rate = 0.03    # 更严格的错误率
config.min_sample_size = 200    # 更大的最小样本量
```

## 🎯 最佳实践

### 1. Prompt 版本管理
- **渐进式变更**：先创建继承版本，小幅调整
- **A/B 测试验证**：新版本先小流量测试
- **数据驱动决策**：基于实际指标决定是否全量

### 2. 错误处理
- **分层处理**：不同类型错误采用不同策略
- **用户友好**：面向用户的错误消息要清晰易懂
- **上下文丰富**：异常包含足够的调试信息

### 3. 性能监控
- **关键指标**：响应时间、成功率、工具调用统计
- **趋势分析**：观察性能变化趋势
- **预警机制**：设置合理的阈值和告警

## 🔍 故障排查指南

### 1. 常见问题
```python
# 问题：AI 分析失败
# 排查：检查 LLM 配置和 Prompt 格式
# 解决：查看 analysis.error 日志，检查 JSON 格式

# 问题：工具调用超时
# 排查：检查 MCP 服务状态和网络连接
# 解决：调整工具时间预算或优化查询

# 问题：A/B 测试不生效
# 排查：检查实验状态和用户是否在目标范围
# 解决：确认实验配置和流量分配
```

### 2. 日志分析
```bash
# 过滤特定 trace 的日志
grep "trace_123" application.log

# 查看工具调用统计
grep "tool.call.end" application.log | tail -20

# 监控实验状态
grep "experiment." application.log
```

## 🎉 总结

重构后的 FAA V2 提供了：

1. **🏗️ 更好的架构**：模块化、职责清晰、易于维护
2. **🧪 科学实验能力**：A/B 测试让 AI 行为优化有数据支撑  
3. **🛡️ 生产级稳定性**：完善的错误处理和监控
4. **⚡ 更高的性能**：智能缓存和优化的工具调用
5. **📚 完善的文档**：从代码到使用的全面指导

现在你可以：
- ✨ 安全地实验新的 AI 行为模式
- 🔍 轻松追踪和调试任何问题
- 📊 基于真实数据优化系统性能
- 🎯 专注于 AI 能力提升而不是工程复杂度

**FAA 已经进化为一个真正智能、优雅、可持续发展的 AI 驱动系统！** 🎊

---
*使用指南版本：V2.0*  
*更新时间：2025年1月28日*
