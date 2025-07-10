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
│     │      AI Engine (增强版)     │     │
│     │  • Prompt Manager          │     │
│     │  • Context Awareness       │     │
│     │  • Emotion Support         │     │
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

### 1. AI Engine (增强版)
- **Prompt Manager**: 动态加载和管理不同版本的提示词
- **历史上下文感知**: 获取最近5条交互记录辅助理解
- **情感支持系统**: 识别用户情绪并给予温暖回应
- **智能分类器**: 自动识别育儿、教育、医疗等特殊类别

### 2. Prompt 管理系统
```yaml
# prompts/family_assistant_prompts.yaml
version: "2.0"
current: "v2_enhanced"
prompts:
  v2_enhanced:
    system: 详细的家庭场景指导
    understanding: 消息理解增强规则
    response_generation: 回复生成优化策略
```

### 3. MCP 工具层（完全通用）
- **零业务逻辑**: 所有业务理解由AI完成
- **通用接口**: store/search/aggregate等基础能力
- **HTTP包装器**: 支持容器化部署

### 4. 数据模型
```sql
-- 通用记忆表
CREATE TABLE memories (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    content TEXT NOT NULL,
    ai_understanding JSONB,  -- AI自由决定存什么
    embedding vector(1536),  -- 语义向量
    amount DECIMAL,          -- 精确金额(可选)
    occurred_at TIMESTAMP    -- 精确时间(可选)
);
```

## AI 驱动的核心流程

### 1. 消息理解流程
```python
async def understand_message(content, user_id):
    # 1. 获取历史上下文
    recent_memories = get_recent_memories(user_id, limit=5)
    
    # 2. 加载当前prompt版本
    system_prompt = prompt_manager.get_system_prompt()
    understanding_guide = prompt_manager.get_understanding_prompt()
    
    # 3. AI理解（包含上下文）
    understanding = await ai.analyze(
        content, 
        context=recent_memories,
        guide=understanding_guide
    )
    
    return understanding
```

### 2. 智能回复生成
```python
async def generate_response(understanding, results):
    # 使用增强的回复指导
    response_guide = prompt_manager.get_response_prompt()
    
    # 生成温暖、有用的回复
    response = await ai.generate(
        understanding=understanding,
        results=results,
        guide=response_guide,
        style="warm_and_helpful"
    )
    
    return response
```

## 自我进化机制

### 1. Prompt 版本迭代
- 通过YAML配置文件管理prompt版本
- 支持A/B测试不同的prompt策略
- 无需修改代码即可优化AI行为

### 2. 数据积累增强
- 每次交互都在丰富AI的理解
- 历史数据帮助更准确的个性化
- JSONB字段支持存储任意新信息

### 3. 模型升级透明
- 更换OpenAI模型只需修改配置
- 自动获得新模型的能力提升
- 工程代码保持稳定

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