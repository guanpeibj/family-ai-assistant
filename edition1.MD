# FAA（Family AI Assistant）第一版开发计划

## 一、项目范围定义

### 核心功能
1. **Threema文字对话接入**
2. **智能信息记录**（财务收支、健康数据、家庭杂事）
3. **智能查询和简单统计**
4. **简单提醒功能**（记录提醒事项，定时发送Threema消息）

### 技术栈
- Python 3.12 + FastAPI
- PostgreSQL + pgvector
- MCP (Model Context Protocol)
- OpenAI API
- Docker + Docker Compose
- APScheduler（轻量级任务调度）

## 二、系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    用户层                                │
│  ┌─────────────┐                                       │
│  │  Threema    │                                       │
│  │   Robot     │                                       │
│  └──────┬──────┘                                       │
└─────────┼───────────────────────────────────────────────┘
          │
┌─────────┼───────────────────────────────────────────────┐
│         ▼          接口层 (FastAPI)                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │  Message    │  │  Scheduler  │  │   Health    │   │
│  │  Handler    │  │   Service   │  │   Check     │   │
│  └──────┬──────┘  └──────┬──────┘  └─────────────┘   │
└─────────┼────────────────┼──────────────────────────────┘
          │                │
┌─────────┼────────────────┼──────────────────────────────┐
│         ▼                ▼     AI处理层                  │
│  ┌─────────────────────────────┐                       │
│  │      AI Orchestrator        │                       │
│  │  ┌─────────┐ ┌───────────┐ │                       │
│  │  │Intent   │ │ Response  │ │                       │
│  │  │Parser   │ │ Generator │ │                       │
│  │  └─────────┘ └───────────┘ │                       │
│  └──────────┬──────────────────┘                       │
└─────────────┼────────────────────────────────────────────┘
              │
┌─────────────┼────────────────────────────────────────────┐
│             ▼        MCP服务层                           │
│  ┌──────────────────────────────────────┐              │
│  │     Family Memory MCP Server         │              │
│  │  ┌────────┐ ┌────────┐ ┌──────────┐│              │
│  │  │ Store  │ │ Query  │ │ Analyze  ││              │
│  │  │ Tools  │ │ Tools  │ │  Tools   ││              │
│  │  └────────┘ └────────┘ └──────────┘│              │
│  └──────────┬───────────────────────────┘              │
└─────────────┼────────────────────────────────────────────┘
              │
┌─────────────┼────────────────────────────────────────────┐
│             ▼         数据层                             │
│  ┌─────────────────┐  ┌─────────────────┐             │
│  │   PostgreSQL    │  │     Redis       │             │
│  │   + pgvector    │  │ (Scheduler)     │             │
│  └─────────────────┘  └─────────────────┘             │
└──────────────────────────────────────────────────────────┘
```

## 三、MCP Server 设计（优化版）

```yaml
family-memory-mcp-server:
  tools:
    # 存储工具组
    - store_memory:       # 通用记忆存储
        params: [content, category, metadata]
        categories: [finance, health, task, info]
    
    # 查询工具组  
    - query_memories:     # 通用查询
        params: [query, category, time_range]
    - get_person_info:    # 查询家庭成员信息
        params: [person_name, info_type]
    
    # 分析工具组
    - analyze_finance:    # 财务简单统计
        params: [time_range, category]
    - analyze_health:     # 健康趋势
        params: [person, metric_type]
    
    # 提醒工具组
    - set_reminder:       # 设置提醒
        params: [content, remind_time, repeat_pattern]
    - list_reminders:     # 查看提醒
        params: [time_range, status]
```

## 四、数据模型设计

```sql
-- 主记忆表
CREATE TABLE memories (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    user_id VARCHAR(50),
    category VARCHAR(50),
    data JSONB,
    embeddings vector(1536),  -- 语义向量
    metadata JSONB
);

-- 提醒表
CREATE TABLE reminders (
    id SERIAL PRIMARY KEY,
    content TEXT,
    remind_at TIMESTAMP,
    repeat_pattern VARCHAR(50),  -- once/daily/weekly/monthly
    is_sent BOOLEAN DEFAULT FALSE,
    created_by VARCHAR(50),
    metadata JSONB
);

-- 索引优化
CREATE INDEX idx_memories_category ON memories(category);
CREATE INDEX idx_memories_data ON memories USING GIN(data);
CREATE INDEX idx_reminders_time ON reminders(remind_at) WHERE NOT is_sent;
```

## 五、开发任务清单

### Phase 1: 基础设施（1-2天）
- [ ] 项目初始化，Docker环境搭建
- [ ] PostgreSQL + pgvector 配置
- [ ] FastAPI 基础框架
- [ ] 环境变量和配置管理
- [ ] 基础日志系统

### Phase 2: Threema接入（1天）
- [ ] Threema Bot API集成
- [ ] 消息接收和发送模块
- [ ] 用户身份验证
- [ ] 消息队列处理

### Phase 3: MCP Server实现（2天）
- [ ] MCP Server框架搭建
- [ ] 实现store_memory工具
- [ ] 实现query_memories工具
- [ ] 实现analyze_finance基础版
- [ ] 实现reminder相关工具

### Phase 4: AI集成（1-2天）
- [ ] OpenAI API接入
- [ ] Intent Parser（意图识别）
- [ ] Entity Extraction（实体提取）
- [ ] Response Generator（回复生成）
- [ ] AI与MCP工具的编排逻辑

### Phase 5: 提醒功能（1天）
- [ ] APScheduler集成
- [ ] 提醒任务扫描和执行
- [ ] 提醒消息发送
- [ ] 重复模式处理

### Phase 6: 测试和部署（1天）
- [ ] 单元测试核心功能
- [ ] Docker镜像构建
- [ ] 部署脚本和CI/CD
- [ ] 生产环境配置
- [ ] 基础监控和告警

## 六、简化的交互流程示例

### 记账场景
```
用户: "今天买菜花了58元"
↓
AI理解: {intent: "record_expense", amount: 58, category: "买菜"}
↓
MCP调用: store_memory(content="买菜支出58元", category="finance", metadata={...})
↓
AI回复: "记住了，今天买菜58元。本月买菜已支出523元。"
```

### 提醒场景
```
用户: "提醒我明天下午3点给大女儿打疫苗"
↓
AI理解: {intent: "set_reminder", time: "明天15:00", content: "给大女儿打疫苗"}
↓
MCP调用: set_reminder(content="给大女儿打疫苗", remind_time="2024-01-20 15:00")
↓
AI回复: "好的，明天下午3点我会提醒你给大女儿打疫苗。"
```

## 七、部署方案

```yaml
# docker-compose.yml
version: '3.8'
services:
  faa-api:
    build: .
    environment:
      - DATABASE_URL=postgresql://...
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - THREEMA_ID=${THREEMA_ID}
      - THREEMA_SECRET=${THREEMA_SECRET}
    depends_on:
      - postgres
      - redis
  
  faa-mcp:
    build: ./mcp-server
    depends_on:
      - postgres
  
  postgres:
    image: pgvector/pgvector:pg16
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  redis:
    image: redis:alpine
```

## 八、风险和应对

1. **AI理解偏差**：保留原始消息，支持手动纠正
2. **提醒遗漏**：增加提醒状态检查，未发送的提醒会重试
3. **数据增长**：定期归档旧数据，保持查询性能

这个计划平衡了功能完整性和开发时间，确保能在几天内交付一个实用的生日礼物！