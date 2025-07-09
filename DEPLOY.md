# 部署指南

## 本地开发（使用 DevContainer）

### 1. 使用 Cursor + DevContainer

1. 确保安装了 Docker Desktop 和 `anysphere.remote-containers` 扩展
2. 打开项目目录
3. Cursor 会提示"在容器中重新打开"，点击确认
4. 容器启动后，所有开发环境已配置好

### 2. 开发命令

```bash
# 在容器内启动服务
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# 运行测试
python examples/test_api.py

# 查看数据库
psql -U faa_user -d faa_db -h postgres

# 查看日志
docker-compose logs -f
```

## 生产部署

### 方式一：GitHub Actions 自动部署（推荐）

#### 1. 配置 GitHub Secrets

在仓库设置中添加以下 Secrets：

- `DEPLOY_HOST`: 服务器IP或域名
- `DEPLOY_USER`: SSH用户名
- `DEPLOY_SSH_KEY`: SSH私钥（用于连接服务器）
- `DEPLOY_PORT`: SSH端口（默认22）
- `DATABASE_URL`: PostgreSQL连接字符串
- `OPENAI_API_KEY`: OpenAI API密钥
- `THREEMA_ID`: Threema Bot ID
- `THREEMA_SECRET`: Threema Secret
- `ALLOWED_USERS`: 允许的用户列表（逗号分隔）
- `SECRET_KEY`: 应用密钥

#### 2. 首次设置服务器

在本地运行：
```bash
export DEPLOY_HOST=your-server.com
export DEPLOY_USER=ubuntu
./scripts/deploy.sh setup
```

#### 3. 自动部署

- 推送到 `main` 或 `master` 分支会自动触发部署
- 也可以在 GitHub Actions 页面手动触发

### 方式二：手动部署脚本

#### 1. 设置环境变量

```bash
export DEPLOY_HOST=your-server.com
export DEPLOY_USER=ubuntu
```

#### 2. 首次部署

```bash
# 设置服务器环境
./scripts/deploy.sh setup

# SSH到服务器创建 .env 文件
ssh $DEPLOY_USER@$DEPLOY_HOST
cd ~/family-ai-assistant
cp .env.example .env
# 编辑 .env 填入实际配置
vim .env
exit
```

#### 3. 日常部署

```bash
# 一键部署
./scripts/deploy.sh

# 查看日志
./scripts/deploy.sh logs

# 检查状态
./scripts/deploy.sh status
```

## 部署流程说明

1. **代码推送**：将代码推送到 GitHub
2. **构建镜像**：在服务器上构建 Docker 镜像
3. **更新服务**：停止旧容器，启动新容器
4. **健康检查**：确认服务正常运行

## 故障排查

### 查看日志
```bash
# 所有服务日志
docker-compose logs

# 只看API日志
docker-compose logs faa-api

# 实时查看
docker-compose logs -f --tail=100
```

### 检查服务状态
```bash
docker-compose ps
```

### 重启服务
```bash
docker-compose restart
```

### 数据库问题
```bash
# 进入数据库
docker-compose exec postgres psql -U faa_user -d faa_db

# 检查表结构
\dt

# 查看记忆数据
SELECT * FROM memories LIMIT 10;
```

## 注意事项

1. **首次部署**需要在服务器上手动创建 `.env` 文件
2. **数据持久化**：PostgreSQL 数据存储在 Docker volume 中
3. **端口**：确保服务器防火墙开放 8000 端口（API）
4. **备份**：定期备份数据库和 `.env` 文件 