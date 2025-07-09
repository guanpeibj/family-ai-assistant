# 快速开始指南

## 5分钟上手FAA 🚀

### 1. 克隆并配置

```bash
# 克隆项目
git clone https://github.com/guanpeibj/family-ai-assistant.git
cd family-ai-assistant

# 配置环境（只需配置必要项）
cp env.example .env
vim .env
```

**必需配置**：
```bash
# OpenAI（必需）
OPENAI_API_KEY=sk-xxx

# 数据库密码（建议修改默认值）
DB_PASSWORD=your_strong_password

# Threema（可选，用于接收消息）
THREEMA_GATEWAY_ID=*XXXXXXX
THREEMA_SECRET=your_secret
```

### 2. 一键启动

```bash
# 启动所有服务
docker-compose up -d

# 确认服务运行正常
docker-compose ps
```

### 3. 初始化家庭信息（推荐）

```bash
# 预设家庭基本信息
python scripts/init_family_data.py

# 记下输出的用户ID，后续使用
```

## 开始使用

### 方式一：API测试（立即可用）

```bash
# 运行完整测试套件
python examples/test_api.py

# 或使用curl快速测试
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{
    "content": "今天买菜花了58元",
    "user_id": "test_user"
  }'
```

### 方式二：Threema对话（需配置）

1. 配置Threema Gateway（见[DEPLOY_THREEMA.md](DEPLOY_THREEMA.md)）
2. 添加FAA为联系人
3. 开始自然对话

## 功能示例

### 💰 智能记账
```
你："今天买菜花了58元"
FAA："已记录！本月买菜支出523元，比上月同期增加20%。💡建议多买些应季蔬菜。"
```

### 👶 健康追踪
```
你："儿子身高92cm"
FAA："记录成功！比上个月长高2cm，成长曲线很棒！📈"
```

### ⏰ 智能提醒
```
你："明天上午9点提醒我带女儿打疫苗"
FAA："好的，明天上午9点会准时提醒您。"
```

### 🔍 信息查询
```
你："这个月花了多少钱？"
FAA："本月总支出1,580元，其中买菜523元，交通180元..."
```

## 开发模式

### 使用DevContainer（推荐）

1. 用Cursor打开项目
2. 提示"在容器中重新打开"时确认
3. 容器内所有环境已配置好

### 查看日志

```bash
# 实时查看所有服务日志
docker-compose logs -f

# 只看AI处理日志
docker-compose logs -f faa-api

# 查看MCP服务日志
docker-compose logs -f faa-mcp
```

## 常见问题

### Q: AI回复不够智能？
A: 检查OpenAI API key是否有效，确认使用的是GPT-4模型

### Q: MCP服务连接失败？
A: MCP通过HTTP包装器运行在9000端口，检查`docker-compose ps`确认服务状态

### Q: 提醒没有发送？
A: 提醒通过Threema发送，需要配置Threema Gateway

## 下一步

1. **体验核心功能**：运行test_api.py了解所有功能
2. **配置Threema**：实现完整的对话体验
3. **查看使用示例**：[USAGE_EXAMPLES.md](USAGE_EXAMPLES.md)
4. **部署到云服务器**：[DEPLOY.md](DEPLOY.md)

---

💡 **提示**：FAA会随着使用越来越了解你的家庭，提供更精准的建议！ 