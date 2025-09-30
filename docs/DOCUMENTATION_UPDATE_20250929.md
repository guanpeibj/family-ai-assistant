# 文档更新记录 - 2025.09.29

## 更新概览
本次全面更新了FAA项目文档，确保所有文档反映最新的AI引擎V2工作流程和优化改进。

## 更新的文档清单

### 1. 核心规则文档 (`.cursor/rules/`)
- ✅ **01-ai-engine.mdc** - 完全重写，详细记录了V2引擎的6步骤流程
- ✅ **project-core.mdc** - 更新为最新架构和工作流

### 2. 项目架构文档
- ✅ **ARCHITECTURE.md** - 全面更新，包含详细的架构图、工作流、性能指标
- ✅ **docs/AI_ENGINE_TECHNICAL.md** - 新增技术文档，详细记录代码结构

### 3. AI引擎工作流 (最新版本)

```
用户输入 → 预处理 → [思考循环] AI分析 → 工具执行 → 响应生成 → 持久化
```

#### 6步骤主流程:
1. **预处理** - 合并附件文本 (OCR/STT/Vision)
2. **实验版本** - A/B测试支持 (v4_optimized)
3. **AI分析** - 多轮思考循环 (最多3轮)
4. **澄清处理** - 需要时生成澄清问题
5. **执行响应** - 工具执行+响应生成
6. **实验记录** - 记录A/B测试结果

## 关键更新内容

### 1. 增强的日志系统
```python
# 主流程日志
"step1.preprocess.completed"     # 含duration_ms
"step3.analysis.completed"       # 含intent, tool_steps_count
"step5.execution.completed"      # 含response_length, total_duration_ms

# AI分析详细日志
"analysis.round.started"         # 思考轮次开始
"llm.response.summary"           # LLM响应(含耗时)
"llm.understanding.details"      # 理解的实体和意图
"llm.tool_plan.details"         # 工具调用计划

# 上下文管理日志
"context.basic.fetched"          # 基础上下文(含预览)
"context.memories.fetched"       # 历史记忆详情
"context.requests.resolved"      # 上下文请求完成
```

### 2. Prompt优化 (v4.1)
- **v4_default**: 完整分析版 (3轮思考)
- **v4_optimized**: 快速响应版 (1轮思考) ⭐推荐

优化要点:
- thinking_depth限制为0-1
- 减少context_requests
- 默认compact回复模式
- 直接执行原则

### 3. 性能指标
| 操作类型 | 目标耗时 | 当前耗时 |
|---------|---------|---------|
| 简单记录 | <5秒 | 5-8秒 |
| 普通查询 | <10秒 | 10-12秒 |
| 复杂分析 | <15秒 | 15-18秒 |

### 4. 代码结构 (~2000行)
```python
# 数据模型 (行71-130)
UnderstandingModel    # AI理解结果
AnalysisModel        # 完整分析结果

# 辅助类 (行131-560)
ContextManager       # 上下文管理
ToolExecutor        # 工具执行

# 主引擎 (行561-1990)
AIEngineV2          # 核心引擎类
├── process_message  # 6步骤主流程
├── _analyze_message # 思考循环
└── _execute_and_respond # 执行响应
```

## 文档使用指南

### 对于开发者
1. 查看 **ARCHITECTURE.md** 了解整体架构
2. 参考 **.cursor/rules/01-ai-engine.mdc** 了解工作流
3. 阅读 **docs/AI_ENGINE_TECHNICAL.md** 了解代码细节

### 对于AI助手
1. 优先参考 **.cursor/rules/** 下的规则文档
2. 使用日志点进行调试追踪
3. 遵循三个核心原则: AI驱动、工程简化、稳定实现

### 调试技巧
```bash
# 追踪完整流程
grep "trace_id=xxx" logs.txt

# 查看性能瓶颈
grep "duration_ms" logs.txt | grep "step"

# 查看思考循环
grep "thinking_loop" logs.txt
```

## 后续维护建议

### 1. 文档同步
- 代码修改后及时更新相应文档
- 保持 `.cursor/rules/` 与实际代码一致
- 定期审查性能指标

### 2. 版本管理
- 记录每次重大更新
- 保持文档版本号更新
- 添加更新日期

### 3. 最佳实践
- 新功能先更新Prompt，无需改代码
- 工具保持通用性，不含业务逻辑
- 通过日志驱动调试和优化

## 相关链接
- [AI引擎源码](../src/ai_engine.py)
- [Prompt配置](../prompts/family_assistant_prompts.yaml)
- [MCP工具服务](../mcp-server/generic_mcp_server.py)
- [架构文档](../ARCHITECTURE.md)

---
*更新者: AI Assistant*
*日期: 2025.09.29*
*版本: 2.0*
