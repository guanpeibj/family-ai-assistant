# FAA 架构设计

## 系统架构图

```
┌─────────────────┐     ┌─────────────────┐
│   Threema App   │     │  Email Client   │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ▼                       ▼
┌─────────────────────────────────────────┐
│            FastAPI (Port 8000)          │
│  ┌──────────────┐  ┌────────────────┐  │
│  │   Webhook    │  │  Message API    │  │
│  └──────┬───────┘  └───────┬────────┘  │
│         │                  │            │
│         ▼                  ▼            │
│     ┌────────────────────────────┐     │
│     │    AI Engine (统一驱动版)   │     │
│     │  • 统一理解（含上下文）       │     │
│     │  • AI自主对话关系处理       │     │
│     │  • 智能深度上下文搜索       │     │
│     └────────────┬───────────────┘     │
└──────────────────┼─────────────────────┘
                   │
                   ▼
        ┌─────────────────────┐
        │  MCP HTTP Wrapper   │
        │    (Port 9000)      │
        └──────────┬──────────┘
                   │
                   ▼
        ┌─────────────────────┐
        │   Generic MCP Tools │
        │ • store             │
        │ • search            │
        │ • aggregate         │
        │ • schedule_reminder │
        └──────────┬──────────┘
                   │
                   ▼
        ┌─────────────────────┐
        │    PostgreSQL       │
        │   with pgvector     │
        └─────────────────────┘
```

## 核心组件

### 1. AI Engine (统一驱动版)
- **统一理解入口**: 单一AI理解流程，自动处理所有对话复杂度
- **智能上下文感知**: 基础上下文（最近对话）+ 可选深度搜索（语义相关）
- **AI自主对话关系识别**: 自动识别跟进、新话题、修正等对话关系
- **零工程预设**: 完全由AI决定信息合并、完整性判断、澄清策略

### 2. Prompt 管理系统
```yaml
# prompts/family_assistant_prompts.yaml
version: "4.0"
current: "v4_default"
blocks:
  system_identity: |
    ...
prompts:
  v4_default:
    system_blocks: [system_identity, ...]
    understanding_blocks: [understanding_contract]
    response_blocks: [response_contract]
    response_ack_blocks: [ack_prompt]
    tool_planning_blocks: [planning_brief]
    profiles:
      threema:
        response_blocks: [response_contract, response_voice_compact]
```

### 3. MCP 工具层（完全通用）
- **零业务逻辑**: 所有业务理解由AI完成
- **通用接口**: store/search/aggregate等基础能力
- **仅消费向量**: 语义向量统一由 AI Engine 生成；MCP 通过参数 `embedding`（store）与 `query_embedding`（search）接收并在数据库执行相似度检索；未提供时退化为非向量过滤
- **本地向量**: 默认使用本地开源向量模型（fastembed，如 `BAAI/bge-small-zh-v1.5`），无需外网与云 API；也可配置回退到 OpenAI 兼容 Embedding
- **HTTP包装器**: 支持容器化部署

### 4. 数据模型
```sql
-- 通用记忆表
CREATE TABLE memories (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    content TEXT NOT NULL,
    ai_understanding JSONB,  -- AI自由决定存什么
    embedding vector(512),   -- 语义向量（BAAI/bge-small-zh-v1.5，由 AI Engine 生成并传入）
    amount DECIMAL,          -- 精确金额(可选)
    occurred_at TIMESTAMP    -- 精确时间(可选)
);
```

## AI 驱动的统一流程 (重构后)

### 核心理念: 让AI决定一切
```
用户输入 → 统一AI理解（含上下文） → 工具计划 → 执行 → 回复
```

### 1. 统一AI理解流程
```python
async def process_message(content, user_id, context):
    light_context = await get_recent_memories(user_id, thread=context.thread_id)

    analysis = await analyze_message(
        message=content,
        user_id=user_id,
        context=context,
        light_context=light_context,
    )

    if analysis.understanding.need_clarification:
        return await generate_clarification(analysis.understanding)

    context_payload = await resolve_context_requests(analysis.context_requests)
    plan = await build_tool_plan(
        understanding=analysis.understanding,
        context_payload=context_payload,
        analysis_plan=analysis.tool_plan,
    )
    execution_result = await execute_tool_steps(plan.steps, context_payload)
    return await generate_response(
        understanding=analysis.understanding,
        execution_result=execution_result,
        context_payload=context_payload,
        response_directives=analysis.response_directives,
    )
```

分析返回的结构是固定契约：
- `understanding`：AI对本轮消息的结构化理解（意图、实体、澄清状态等）
- `context_requests`：LLM声明需要的额外上下文（recent_memories / semantic_search / direct_search ...）
- `tool_plan`：草稿步骤与所需上下文引用
- `response_directives`：回复所需的 profile、语气与关注点

### 2. 智能上下文管理
- `context_requests` 描述需要的资源类型（例如近期对话、语义检索结果、线程摘要、指定过滤搜索等）
- 引擎统一通过 `_resolve_context_requests` 调用 MCP `search / batch_search` 等工具拉取数据，结果写入 `context_payload`
- 工具计划可通过 `{"use_context": "recent_history"}` 等引用上下文数据，执行阶段会自动解析

## 自我进化机制 - 核心设计理念

> **"工程固定，能力自动增长"** - 即使工程代码保持不变，系统的智能和能力也随着AI模型进步和数据积累而自动提升

### 1. AI模型升级 → 能力自动提升
```bash
# 仅需更新配置，无需修改代码
OPENAI_MODEL=gpt-4o  # 未来可能是 gpt-5, claude-4 等
```
**自动获得的新能力**：
- 更准确的对话关系识别
- 更智能的上下文理解
- 更自然的多轮对话处理
- 更复杂的推理能力

### 2. Prompt优化 → 行为自动改进
```yaml
# 只需调整YAML，行为立即优化
contextual_understanding_rules: |
  AI自主上下文理解：
  - 自动识别跟进回答："给二女儿的"→补充前一个记账请求
  - 自动合并信息：跟进+原始请求→完整理解
```

### 3. 数据积累 → 个性化自动增强
- 历史对话提供更好的上下文
- AI自学习家庭成员偏好
- JSONB开放结构支持AI发现新信息类型

### 4. 零工程干预的能力扩展
- **新对话模式**：AI自动适应，无需编程
- **复杂场景处理**：更强模型自动胜任
- **个性化改进**：随使用自动优化

## 部署架构

### Docker Compose 服务
```yaml
services:
  faa-api:      # FastAPI主服务
  faa-mcp:      # MCP HTTP包装器
  postgres:     # 数据库
```

### 环境隔离
- 开发环境：DevContainer
- 测试环境：docker-compose
- 生产环境：云服务器 + Docker

## 安全设计

### 1. 数据隔离
- 用户数据通过user_id严格隔离
- MCP工具自动过滤用户数据

### 2. 加密通信
- Threema端到端加密
- API使用HTTPS（生产环境）

### 3. 敏感信息
- OpenAI API Key环境变量
- 数据库密码环境变量

## 扩展性设计

### 1. 新渠道接入
- 实现新的webhook endpoint
- 复用现有AI Engine

### 2. 新功能添加
- 更新prompt即可支持新场景
- 无需修改核心代码

### 3. 多语言支持
- 通过prompt版本实现
- AI自动适应语言

## 性能优化

### 1. 向量搜索
- pgvector索引加速语义搜索
- 相似度计算在数据库层完成

### 2. 连接池
- asyncpg连接池管理
- 避免频繁建立连接

### 3. 异步处理
- 全异步架构
- 支持并发请求

## 监控与日志

### 1. 结构化日志
- structlog JSON格式
- 便于日志分析

### 2. 健康检查
- /health endpoint
- Docker健康检查

### 3. 错误追踪
- 详细的错误上下文
- AI决策过程可追溯 
