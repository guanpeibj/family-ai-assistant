# Family AI Assistant - 架构设计

## 核心理念

**"AI驱动、尽量减少工程预设、实在有用"**

## 架构概览

```
用户 → Threema/Email/WeChat → FastAPI → AI Engine → MCP(HTTP) → Database
                                          ↓
                                    OpenAI API
```

## 关键设计决策

### 1. 极简数据模型
- **用户管理**：`users` 和 `user_channels` 表支持多渠道
- **核心存储**：`memories` 表存储所有信息
- **提醒系统**：`reminders` 表关联记忆
- **AI理解**：`ai_understanding` JSONB字段让AI自由存储

### 2. AI驱动的处理流程
1. **接收**：通过Webhook接收消息（Threema已实现）
2. **理解**：AI深度分析消息，智能提取信息
3. **执行**：根据理解调用MCP工具，自动进行相关统计
4. **回复**：AI生成个性化、有价值的响应

### 3. 增强的AI能力
- **定制化System Prompt**：专为3孩家庭优化
- **智能时间理解**：自动转换自然语言时间表达
- **自动分类**：支出类别自动识别
- **统计分析**：记录后立即提供相关统计
- **异常检测**：发现异常模式时主动提醒

### 4. 泛化的MCP工具（HTTP接口）
```
POST /tool/store              # 存储任何信息
POST /tool/search             # 语义搜索 + 精确过滤
POST /tool/aggregate          # 灵活的聚合统计
POST /tool/schedule_reminder  # 设置提醒
POST /tool/get_pending_reminders  # 获取待发送提醒
POST /tool/mark_reminder_sent # 标记已发送
```

### 5. 多渠道支持架构
- **Threema**：E2E加密，已完整实现
- **Email**：预留接口，易于添加
- **WeChat**：预留接口，相同模式

## 技术栈

- **Python 3.12 + FastAPI**: Web框架
- **PostgreSQL + pgvector**: 数据存储和向量搜索
- **OpenAI API**: AI能力（GPT-4-turbo）
- **MCP HTTP包装器**: 工具服务化
- **PyNaCl**: Threema加密
- **Docker Compose**: 容器编排

## 设计亮点

### 1. AI自我进化能力
- 工程代码保持稳定
- 能力随AI模型升级自动提升
- 通过数据积累越用越智能
- 只需调整Prompt即可获得新功能

### 2. 零业务逻辑硬编码
- 没有预设的分类系统
- 没有固定的数据格式
- 没有限制的使用场景
- AI决定一切

### 3. 容器化友好
- MCP通过HTTP提供服务
- 各服务独立运行
- 易于水平扩展
- 简化部署流程

## 安全设计

- **端到端加密**：Threema消息全程加密
- **用户隔离**：每个用户的数据完全独立
- **最小权限**：工具只能访问用户自己的数据
- **环境变量管理**：敏感信息分离

## 扩展性

1. **新渠道**：实现适配器接口即可
2. **新功能**：调整AI prompt，无需改代码
3. **新工具**：添加MCP工具定义
4. **性能扩展**：服务可独立扩展

## 为什么这样设计？

- **简单**：3层架构，易理解易维护
- **灵活**：AI决定一切，适应性强
- **实用**：专注核心功能，快速交付
- **进化**：随AI技术进步自动获得新能力 