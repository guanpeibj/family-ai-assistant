# FAA 部署指南

## 🚀 快速开始（5分钟部署）

### 一键部署脚本
```bash
# 在你的服务器上执行
curl -fsSL https://raw.githubusercontent.com/guanpeibj/family-ai-assistant/master/scripts/quick-deploy.sh | bash
```

### 或者手动部署
```bash
# 1. 克隆项目
git clone https://github.com/guanpeibj/family-ai-assistant.git
cd family-ai-assistant

# 2. 复制配置
cp env.example .env
nano .env  # 编辑必要配置

# 3. 启动服务
docker-compose up -d
```

## 📋 详细部署步骤

### 1. 服务器准备

#### 最低配置要求
- CPU: 1核
- 内存: 2GB
- 存储: 20GB
- 系统: Ubuntu 20.04+

#### 推荐配置（稳定运行）
- CPU: 2核
- 内存: 4GB
- 存储: 40GB
- 系统: Ubuntu 22.04 LTS

#### 安装必要软件
```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 安装 Docker Compose
sudo apt install docker-compose -y

# 重新登录以应用 docker 组权限
logout
```

### 2. 项目部署

```bash
# 克隆项目
git clone https://github.com/yourusername/family-ai-assistant.git
cd family-ai-assistant

# 配置环境变量
cp env.example .env
nano .env
```

#### 必需的环境变量
```env
# OpenAI 配置（必需）
OPENAI_API_KEY=sk-xxx

# 数据库密码（请修改）
POSTGRES_PASSWORD=your_strong_password_here

# 应用密钥（请生成随机字符串）
SECRET_KEY=your_random_secret_key_here

# Threema 配置（可选，如需接收消息）
THREEMA_GATEWAY_ID=*XXXXXXX
THREEMA_API_SECRET=your_threema_secret
```

#### 启动服务
```bash
# 构建并启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

### 3. 配置域名和HTTPS（推荐）

#### 方案一：使用 Cloudflare（免费）
1. 注册 [Cloudflare](https://cloudflare.com) 账号
2. 添加你的域名
3. 修改域名 DNS 服务器为 Cloudflare 提供的
4. 添加 A 记录指向服务器 IP
5. 开启 SSL/TLS（Flexible 模式）
6. 开启 Always Use HTTPS

#### 方案二：使用 Nginx + Let's Encrypt
```bash
# 安装 Nginx
sudo apt install nginx certbot python3-certbot-nginx -y

# 配置 Nginx
sudo nano /etc/nginx/sites-available/faa
```

配置文件内容：
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# 启用站点
sudo ln -s /etc/nginx/sites-available/faa /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# 获取 SSL 证书
sudo certbot --nginx -d your-domain.com
```

### 4. 配置 Threema（可选）

在 Threema Gateway 管理面板设置：
- Webhook URL: `https://your-domain.com/webhook/threema`
- 选择接收所有消息类型

测试 Webhook：
```bash
curl -X POST https://your-domain.com/webhook/threema \
  -H "Content-Type: application/json" \
  -d '{"from":"ECHOECHO","text":"测试消息"}'
```

### 5. 初始化数据

```bash
# 运行数据初始化脚本
docker-compose exec faa-api python scripts/init_family_data.py

# 记录输出的用户ID，用于后续使用
```

## 🔧 日常运维

### 查看日志
```bash
# 所有服务日志
docker-compose logs -f

# 特定服务日志
docker-compose logs -f faa-api
docker-compose logs -f postgres
```

### 备份数据
```bash
# 备份脚本
cat > backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
docker-compose exec -T postgres pg_dump -U faa family_assistant > backup_${DATE}.sql
echo "备份完成: backup_${DATE}.sql"
EOF

chmod +x backup.sh

# 设置定时备份
crontab -e
# 添加: 0 2 * * * /path/to/backup.sh
```

### 更新服务
```bash
# 拉取最新代码
git pull

# 重建并重启服务
docker-compose build
docker-compose up -d

# 清理旧镜像
docker image prune -f
```

### 监控服务
```bash
# 健康检查
curl http://localhost:8000/health

# 查看资源使用
docker stats

# 查看磁盘空间
df -h
```

## 🐛 故障排查

### 服务无法启动
```bash
# 检查端口占用
sudo lsof -i :8000
sudo lsof -i :5432

# 查看详细错误
docker-compose logs --tail=100

# 重置服务
docker-compose down -v  # 注意：会删除数据
docker-compose up -d
```

### 数据库连接失败
```bash
# 检查数据库服务
docker-compose ps postgres

# 测试连接
docker-compose exec postgres psql -U faa -d family_assistant

# 重置数据库密码
docker-compose exec postgres psql -U postgres -c "ALTER USER faa PASSWORD 'new_password';"
```

### AI 响应问题
- 检查 OpenAI API Key 是否正确
- 确认 API 余额充足
- 查看 API 错误日志：`docker-compose logs faa-api | grep -i error`

## 💰 成本优化

### 服务器选择
- **开发测试**：任何 2GB 内存的 VPS（$5-10/月）
- **生产使用**：4GB 内存 VPS（$20-40/月）
- **推荐提供商**：Hetzner、DigitalOcean、Vultr

### API 成本控制
- 使用 GPT-4-turbo 而非 GPT-4
- 实现对话历史限制
- 添加用户配额管理

## 🔐 安全建议

### 必做项
1. 修改所有默认密码
2. 配置防火墙只开放必要端口
3. 启用 HTTPS
4. 定期更新系统和 Docker

### 防火墙配置
```bash
# 使用 ufw
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

## 📞 快速支持

### 健康检查失败？
```bash
# 运行诊断脚本
docker-compose exec faa-api python scripts/check_deployment.py
```

### 需要重置？
```bash
# 完全重置（注意：会删除所有数据）
docker-compose down -v
rm -rf postgres_data
docker-compose up -d
```

### GitHub Actions 自动部署

1. 在 GitHub 仓库设置 Secrets：
   - `DEPLOY_HOST`: 服务器IP
   - `DEPLOY_USER`: SSH用户
   - `DEPLOY_SSH_KEY`: SSH私钥
   - `OPENAI_API_KEY`: OpenAI密钥
   - 其他必要的环境变量

2. 推送到 main 分支自动部署

---

**需要帮助？** 查看 [常见问题](https://github.com/yourusername/family-ai-assistant/wiki) 或提交 [Issue](https://github.com/yourusername/family-ai-assistant/issues) 