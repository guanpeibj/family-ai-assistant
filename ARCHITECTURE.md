# Family AI Assistant - 简化架构

## 核心理念

**"AI驱动、尽量减少工程预设、实在有用"**

## 架构概览

```
用户 → Threema → FastAPI → AI Engine → MCP Tools → Database
                              ↓
                         OpenAI API
```

## 关键设计决策

### 1. 极简数据模型
- 只有两个表：`memories` 和 `reminders`
- AI决定如何理解和存储信息（`ai_understanding` JSONB字段）
- 支持精确查询的可选字段（`amount`, `occurred_at`）

### 2. AI驱动的处理流程
1. **理解**：AI分析用户消息，提取意图和实体
2. **执行**：根据理解调用相应的MCP工具
3. **回复**：AI生成自然语言响应

### 3. 泛化的MCP工具
- `store`: 存储任何信息
- `search`: 语义搜索 + 精确过滤
- `aggregate`: 灵活的聚合统计
- `schedule_reminder`: 设置提醒
- `get_pending_reminders`: 获取待发送提醒
- `mark_reminder_sent`: 标记已发送

### 4. 简单的提醒系统
- 后台任务每分钟检查一次
- 无需复杂的调度框架
- 提醒与记忆关联

## 技术栈

- **Python 3.12.11** + **FastAPI**: Web框架
- **PostgreSQL** + **pgvector**: 数据存储和向量搜索
- **OpenAI API 1.90.0**: AI能力
- **MCP**: 工具协议
- **Docker Compose**: 部署

## 扩展性

1. **新功能**：只需调整AI prompt，无需改代码
2. **新数据类型**：AI自动适应，存入JSONB
3. **新渠道**：添加新的消息处理端点即可

## 为什么这样设计？

- **简单**：3层架构，代码量少，易理解
- **灵活**：AI决定一切，减少硬编码
- **实用**：专注核心功能，快速交付
- **可扩展**：结构简单，便于后续迭代 