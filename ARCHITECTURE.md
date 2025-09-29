# FAA (Family AI Assistant) 系统架构文档

## 版本信息
- **文档版本**: 2.0
- **更新日期**: 2025.09.29
- **AI引擎版本**: V2 Enhanced
- **Prompt版本**: v4.1

## 一、系统概览

### 1.1 核心理念
FAA 遵循三个核心设计原则：
1. **AI驱动 (AI-Driven)**: 让AI决定业务逻辑，工程只提供执行框架
2. **工程简化 (Engineering Simplicity)**: 统一流程，最小化代码，通过配置演进
3. **稳定实现 (Stable Implementation)**: 完善的错误处理、日志追踪和降级策略

### 1.2 架构图
```
┌─────────────────────────────────────────────────────────────┐
│                        用户交互层                            │
│     Threema │ Web API │ Email │ Future Channels            │
└─────────────────┬────────────────────────────────────────────┘
                  │
┌─────────────────▼────────────────────────────────────────────┐
│                     FastAPI 应用层                           │
│  • /message 端点：直接消息处理                               │
│  • /threema/webhook：Threema集成                           │
│  • /media/get：媒体文件访问                                │
│  • /health：健康检查                                       │
└─────────────────┬────────────────────────────────────────────┘
                  │
┌─────────────────▼────────────────────────────────────────────┐
│              AI引擎 V2 (src/ai_engine.py)                    │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │                    主处理流程 (6步骤)                     │ │
│ │ 1. 预处理 (_preprocess_message)                         │ │
│ │ 2. 实验版本 (_get_experiment_version)                   │ │
│ │ 3. AI分析 (_analyze_message) 🧠 支持3轮思考循环         │ │
│ │ 4. 澄清处理 (_handle_clarification) 可选                │ │
│ │ 5. 执行响应 (_execute_and_respond)                      │ │
│ │ 6. 实验记录 (_record_experiment_result)                 │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                               │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │                    核心组件                              │ │
│ │ • ContextManager: 智能上下文管理                        │ │
│ │ • ToolExecutor: 工具编排执行                           │ │
│ │ • MessageProcessor: 消息预处理                         │ │
│ │ • 嵌入缓存: 两级缓存优化                               │ │
│ └──────────────────────────────────────────────────────────┘ │
└─────────────────┬────────────────────────────────────────────┘
                  │ HTTP
┌─────────────────▼────────────────────────────────────────────┐
│          MCP工具服务器 (mcp-server/generic_mcp_server.py)    │
│  通用工具集（无业务逻辑）:                                   │
│  • store: 存储任意信息                                      │
│  • search: 语义/精确搜索                                    │
│  • aggregate: 数据聚合统计                                  │
│  • schedule_reminder: 提醒管理                              │
│  • update_memory_fields: 更新记忆                           │
│  • render_chart: 图表生成                                   │
└─────────────────┬────────────────────────────────────────────┘
                  │
┌─────────────────▼────────────────────────────────────────────┐
│              PostgreSQL + pgvector                           │
│  • memories: 核心记忆表 (JSONB + Vector)                    │
│  • users: 用户管理                                          │
│  • reminders: 提醒任务                                      │
│  • interactions: 交互记录                                   │
│  • households: 家庭结构                                     │
└──────────────────────────────────────────────────────────────┘
```

## 二、核心工作流

### 2.1 消息处理流程 (process_message)

```python
async def process_message(content: str, user_id: str, context: Dict) -> str:
    """
    主入口 - AI驱动的统一流程
    耗时目标: 简单操作 <5秒, 普通查询 <10秒, 复杂分析 <15秒
    """
    # 步骤1: 预处理
    # - 合并附件文本(OCR/STT/Vision)
    # - 日志: step1.preprocess.completed
    
    # 步骤2: 获取实验版本
    # - 支持A/B测试不同Prompt
    # - 当前: v4_optimized (快速版)
    
    # 步骤3: AI分析 (核心)
    # - 支持多轮思考(最多3轮)
    # - 智能获取所需上下文
    # - 输出理解+工具计划
    
    # 步骤4: 澄清处理 (可选)
    # - 仅在need_clarification时
    
    # 步骤5: 执行和响应
    # - 执行工具计划
    # - 生成最终响应
    
    # 步骤6: 实验记录
    # - 记录A/B测试数据
```

### 2.2 AI分析详解 (_analyze_message)

#### 思考循环机制
```
第1轮: 基础理解
├── 获取基础上下文 (最近4条对话 + 家庭信息)
├── 构建分析载荷
├── 调用LLM分析
└── 判断是否需要深入 (thinking_depth)

第2-3轮: 深度分析 (可选)
├── 基于初步理解请求额外上下文
├── 累积洞察 (accumulated_context)
├── 再次调用LLM深化理解
└── 输出最终分析结果
```

#### 输出契约 (AnalysisModel)
```json
{
  "understanding": {
    "intent": "用户意图",
    "entities": {
      "amount": 100,
      "type": "购物"
    },
    "need_action": true,
    "need_clarification": false,
    "thinking_depth": 1,
    "needs_deeper_analysis": false,
    "original_content": "原始消息"
  },
  "context_requests": [
    {"name": "recent_memories", "kind": "recent_memories"}
  ],
  "tool_plan": {
    "steps": [
      {"tool": "store", "args": {...}}
    ]
  },
  "response_directives": {
    "profile": "compact"
  }
}
```

### 2.3 上下文管理 (ContextManager)

#### 基础上下文
- **light_context**: 最近对话记录
- **household**: 家庭成员信息

#### 动态上下文请求
- **recent_memories**: 历史记忆
- **semantic_search**: 语义搜索
- **direct_search**: 精确过滤
- **thread_summaries**: 线程摘要

### 2.4 工具执行 (ToolExecutor)

#### 执行流程
1. 获取工具元数据
2. 检查时间预算
3. 执行工具步骤
4. 验证结果完整性
5. 必要时补充查询

#### 验证循环
- 最多3轮验证
- 检查数据完整性
- 自动补充缺失信息

## 三、关键技术特性

### 3.1 日志系统

#### 主流程日志
```
message.received           # 接收消息
step1.preprocess.completed # 预处理完成
step3.analysis.completed   # 分析完成
step5.execution.completed  # 执行完成
```

#### 分析详细日志
```
analysis.round.started        # 轮次开始
analysis.basic_context.details # 上下文详情
llm.response.summary          # LLM响应
llm.understanding.details     # 理解详情
llm.tool_plan.details        # 工具计划
```

#### 性能追踪
- 每个步骤都有 `duration_ms`
- 支持 `trace_id` 全链路追踪
- 工具调用计数和耗时

### 3.2 缓存机制

#### 向量嵌入缓存
- **Trace级缓存**: 单次请求内复用
- **全局LRU缓存**: 跨请求复用
- **TTL**: 3600秒
- **容量**: 1000项

#### 工具元数据缓存
- 缓存MCP工具列表
- 减少HTTP调用

### 3.3 Prompt管理

#### 版本体系
```yaml
current: "v4_optimized"  # 当前激活版本

prompts:
  v4_default:    # 完整分析版
    - 支持3轮思考
    - 全面上下文
    - 详细响应
    
  v4_optimized:  # 快速响应版(推荐)
    - 限制1轮思考
    - 最少上下文
    - 简洁回复
```

#### 动态注入
- `{{DYNAMIC_TOOLS}}`: 工具列表
- `{{DYNAMIC_TOOL_SPECS}}`: 工具规格

### 3.4 错误处理

#### 异常层级
```
BaseAIException
├── AnalysisError       # AI分析失败
├── ContextResolutionError # 上下文失败
├── ToolPlanningError   # 规划失败
├── MCPToolError        # 工具调用失败
├── ToolTimeoutError    # 工具超时
└── LLMError           # LLM调用失败
```

#### 降级策略
1. 工具失败 → 基础响应
2. LLM失败 → 友好提示
3. 严重错误 → 详细日志

## 四、数据模型

### 4.1 核心表结构

#### memories (核心记忆表)
```sql
CREATE TABLE memories (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    content TEXT NOT NULL,
    ai_understanding JSONB,    -- AI自由存储
    embedding vector(1536),     -- 语义向量
    amount DECIMAL(10,2),       -- 金额(可选)
    occurred_at TIMESTAMP,      -- 发生时间
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### 索引策略
- 向量索引: `ivfflat`
- JSONB索引: `jsonb_path_ops`
- 表达式索引: `thread_id`, `type`, `channel`
- 组合索引: 时间+用户

### 4.2 JSONB灵活性

AI可以在 `ai_understanding` 中存储任意结构:
```json
{
  "type": "expense",
  "amount": 100,
  "category": "购物",
  "thread_id": "20250929",
  "entities": {
    "shop": "超市",
    "items": ["牛奶", "面包"]
  },
  // AI可以自由扩展...
  "confidence": 0.95,
  "related_memories": ["uuid1", "uuid2"]
}
```

## 五、性能优化

### 5.1 目标指标
| 操作类型 | 目标耗时 | 当前耗时 |
|---------|---------|---------|
| 简单记录 | <5秒 | 5-8秒 |
| 普通查询 | <10秒 | 10-12秒 |
| 复杂分析 | <15秒 | 15-18秒 |
| 思考轮数 | ≤2轮 | 1-2轮 |

### 5.2 优化策略

#### 已实施
- ✅ Prompt优化 (v4_optimized)
- ✅ 向量嵌入缓存
- ✅ 减少思考轮数
- ✅ 简化上下文请求

#### 计划中
- [ ] 查询结果缓存
- [ ] 工具并行执行
- [ ] 流式响应
- [ ] 预编译Prompt

### 5.3 监控要点
```python
# 关键监控指标
{
  "thinking_rounds": 1-2,      # 思考轮数
  "tool_calls": 1-3,           # 工具调用数
  "total_duration_ms": <15000, # 总耗时
  "cache_hit_rate": >0.5       # 缓存命中率
}
```

## 六、部署架构

### 6.1 容器化部署
```yaml
services:
  faa-api:       # FastAPI应用
    - AI引擎
    - API端点
    - 后台任务
    
  faa-mcp:       # MCP工具服务
    - HTTP包装器
    - 通用工具集
    
  faa-postgres:  # 数据库
    - PostgreSQL 15
    - pgvector扩展
```

### 6.2 环境配置

#### 核心配置
```bash
# AI配置
OPENAI_API_KEY=xxx
OPENAI_MODEL=gpt-4
AI_PROVIDER=openai

# 系统配置
DEBUG=false
LOW_BUDGET_MODE=false
MCP_SERVER_URL=http://faa-mcp:8000

# 数据库
DATABASE_URL=postgresql://...
```

## 七、开发指南

### 7.1 添加新功能（无需改代码）

#### 方法1: 修改Prompt
```yaml
# prompts/family_assistant_prompts.yaml
blocks:
  my_new_feature: |
    新功能的行为描述...

prompts:
  v4_optimized:
    understanding_blocks:
      - my_new_feature  # 添加到块列表
```

#### 方法2: 调整工具使用
通过Prompt引导AI使用现有工具的新组合

### 7.2 添加新工具

1. 在MCP服务器添加工具:
```python
# mcp-server/generic_mcp_server.py
async def _new_tool(self, ...):
    """保持通用性，无业务逻辑"""
    pass
```

2. 更新工具白名单（如需要）

### 7.3 调试技巧

#### 日志调试
```bash
# 开启调试模式
DEBUG=true

# 关键日志点
grep "step3.analysis" logs.txt    # 分析过程
grep "trace_id=xxx" logs.txt      # 追踪请求
grep "duration_ms" logs.txt       # 性能分析
```

#### 性能分析
```python
# 查看各步骤耗时
"step1.preprocess.completed" duration_ms=10
"step3.analysis.completed" duration_ms=8000
"step5.execution.completed" duration_ms=3000
```

## 八、最佳实践

### 8.1 Prompt优化
- 使用 v4_optimized 版本
- 限制思考深度为0-1
- 减少不必要的上下文请求
- 使用聚合工具替代多次查询

### 8.2 工具使用
- 直接执行，避免预检查
- 使用精确过滤条件
- 批量操作优于逐个处理

### 8.3 错误处理
- 提供友好的用户提示
- 记录详细的调试信息
- 实施合理的降级策略

## 九、路线图

### 2025 Q1 (已完成)
- ✅ AI引擎V2重构
- ✅ 思考循环优化
- ✅ 详细日志系统
- ✅ Prompt v4优化

### 2025 Q2 (进行中)
- [ ] 查询结果缓存
- [ ] 工具并行化
- [ ] 流式响应
- [ ] 性能监控面板

### 2025 Q3-Q4
- [ ] 多模态增强
- [ ] 自适应Prompt
- [ ] 分布式执行
- [ ] 智能预加载

## 十、参考文档

- [AI引擎工作流](.cursor/rules/01-ai-engine.mdc)
- [Prompt管理](.cursor/rules/02-prompts.mdc)
- [MCP工具开发](.cursor/rules/03-mcp-tools.mdc)
- [数据库设计](.cursor/rules/05-database-and-index.mdc)
- [部署指南](DEPLOY.md)

---
*Architecture Version: 2.0*
*Last Updated: 2025.09.29*
*Maintained by: AI-Driven Development Team*