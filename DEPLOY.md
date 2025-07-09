# 部署指南

## 本地开发

### 使用 DevContainer（推荐）

1. 安装 Docker Desktop
2. 用 Cursor 打开项目
3. 选择"在容器中重新打开"
4. 开发环境自动配置完成

### 开发命令

```bash
# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 运行测试
python examples/test_api.py

# 初始化家庭数据
python scripts/init_family_data.py

# 访问数据库
psql -U faa -d family_assistant -h postgres
```

## 生产部署

### 方式一：快速部署

#### 1. 服务器准备

```bash
# 安装 Docker 和 Docker Compose
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 克隆项目
git clone https://github.com/guanpeibj/family-ai-assistant.git
cd family-ai-assistant
```

#### 2. 配置环境

```bash
# 复制并编辑配置
cp env.example .env
vim .env
```

**必需配置**：
```bash
# OpenAI（必需）
OPENAI_API_KEY=sk-xxx

# 数据库（生产环境请使用强密码）
DB_PASSWORD=your_very_strong_password

# 安全（生产环境必需）
SECRET_KEY=generate_a_long_random_string

# Threema（如需接收消息）
THREEMA_GATEWAY_ID=*XXXXXXX
THREEMA_SECRET=your_secret
THREEMA_WEBHOOK_URL=https://your-domain.com/webhook/threema
```

#### 3. 启动服务

```bash
# 构建并启动
docker-compose build
docker-compose up -d

# 检查服务状态
docker-compose ps

# 查看启动日志
docker-compose logs -f
```

#### 4. 初始化数据（可选）

```bash
# 初始化家庭基本信息
cd scripts
python init_family_data.py

# 记录生成的用户ID
```

### 方式二：GitHub Actions 自动部署

#### 1. 配置 GitHub Secrets

在仓库设置中添加：

- `DEPLOY_HOST`: 服务器IP或域名
- `DEPLOY_USER`: SSH用户名
- `DEPLOY_SSH_KEY`: SSH私钥
- `DB_PASSWORD`: 数据库密码
- `OPENAI_API_KEY`: OpenAI密钥
- `THREEMA_GATEWAY_ID`: Threema ID
- `THREEMA_SECRET`: Threema密钥
- `SECRET_KEY`: 应用密钥

#### 2. 自动部署

推送到 `main` 分支自动触发部署

## Threema 配置（可选）

### 1. 配置反向代理

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location /webhook/threema {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    location /api/ {
        proxy_pass http://localhost:8000/;
    }
}
```

### 2. 设置 Webhook

1. 登录 Threema Gateway
2. 设置 Webhook URL：`https://your-domain.com/webhook/threema`
3. 保存设置

详细步骤见 [DEPLOY_THREEMA.md](DEPLOY_THREEMA.md)

## 服务架构

```yaml
services:
  postgres       # 数据库 + pgvector
  faa-api        # 主服务（FastAPI + AI Engine）
  faa-mcp        # MCP HTTP 服务器
```

### 端口说明
- `8000`: API 服务
- `5432`: PostgreSQL（仅内部）
- `9000`: MCP HTTP 服务（仅内部）

## 日常维护

### 查看日志
```bash
# 所有服务
docker-compose logs -f

# 特定服务
docker-compose logs -f faa-api
docker-compose logs -f faa-mcp
```

### 备份数据
```bash
# 备份数据库
docker-compose exec postgres pg_dump -U faa family_assistant > backup_$(date +%Y%m%d).sql

# 备份配置
cp .env .env.backup
```

### 更新服务
```bash
git pull
docker-compose build
docker-compose up -d
```

### 监控健康状态
```bash
# API健康检查
curl http://localhost:8000/health

# MCP健康检查
curl http://localhost:9000/health
```

## 性能优化

### 1. 数据库优化
- pgvector 索引已自动创建
- 定期执行 `VACUUM ANALYZE`

### 2. 容器资源限制
```yaml
# docker-compose.yml
services:
  faa-api:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
```

### 3. 日志管理
```yaml
# 限制日志大小
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"
```

## 故障排查

### 服务无法启动
```bash
# 检查端口占用
sudo netstat -tulpn | grep -E '8000|5432|9000'

# 查看详细错误
docker-compose logs --tail=50
```

### AI响应缓慢
- 检查 OpenAI API 状态
- 确认网络连接正常
- 查看 API 日志中的响应时间

### MCP连接问题
- 确认 MCP 服务运行：`docker-compose ps faa-mcp`
- 检查内部网络：`docker network ls`
- 查看 MCP 日志：`docker-compose logs faa-mcp`

## 安全建议

1. **生产环境必需**
   - 使用强密码
   - 配置 HTTPS
   - 限制端口访问
   - 定期更新系统

2. **数据安全**
   - 定期备份
   - 加密存储敏感信息
   - 监控异常访问

3. **API安全**
   - 限制请求频率
   - 验证用户身份
   - 记录访问日志

## 成本控制

- **OpenAI API**：使用 GPT-4-turbo 约 $0.01/1K tokens
- **服务器**：最低 2GB 内存即可运行
- **存储**：数据库增长缓慢，100GB 足够长期使用 