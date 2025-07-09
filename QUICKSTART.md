# 快速开始指南

## 本地开发（推荐使用 DevContainer）

### 1. 使用 Cursor 开发

```bash
# 1. 克隆项目
git clone https://github.com/guanpeibj/family-ai-assistant.git
cd family-ai-assistant

# 2. 创建环境配置（两种方式）

# 方式一：复制示例文件
cp env.example .env
# 然后编辑 .env 文件，填入你的实际配置

# 方式二：直接创建
cat > .env << EOF
DATABASE_URL=postgresql+asyncpg://faa_user:faa_password@postgres:5432/faa_db
OPENAI_API_KEY=你的OpenAI密钥
THREEMA_ID=你的Threema_ID
THREEMA_SECRET=你的Threema密钥
ALLOWED_USERS=test_user
SECRET_KEY=dev-secret-key
APP_ENV=development
LOG_LEVEL=INFO
EOF

# 3. 用 Cursor 打开项目
# 会提示"在容器中重新打开"，点击确认
```

### 2. 在 DevContainer 中开发

容器启动后，在终端运行：

```bash
# 启动 API 服务
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# 在另一个终端测试
python examples/test_api.py
```

### 3. 手动运行（不使用 DevContainer）

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 测试 API
curl http://localhost:8000/health
```

## 快速测试

### 使用 curl 测试

```bash
# 健康检查
curl http://localhost:8000/health

# 发送消息
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{
    "content": "今天买菜花了58元",
    "user_id": "test_user"
  }'
```

### 使用 Python 测试

```python
import httpx
import asyncio

async def test():
    async with httpx.AsyncClient() as client:
        # 发送消息
        response = await client.post(
            "http://localhost:8000/message",
            json={
                "content": "今天买菜花了58元",
                "user_id": "test_user"
            }
        )
        print(response.json())

asyncio.run(test())
```

## 常见问题

### 1. OpenAI API 错误
- 检查 API 密钥是否正确
- 确认账户有余额

### 2. 数据库连接错误
- 确认 PostgreSQL 容器正在运行
- 检查 DATABASE_URL 配置

### 3. MCP Server 连接问题
- 暂时 MCP 调用是模拟的
- Phase 2 会实现真实连接

## 下一步

1. 配置 Threema Bot（Phase 2）
2. 实现 MCP 客户端连接
3. 部署到生产环境 