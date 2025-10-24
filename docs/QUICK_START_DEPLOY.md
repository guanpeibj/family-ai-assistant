# FAA 快速部署指南

5 步完成 FAA 生产部署和 CI/CD 配置。

## 前置要求

- 一台 Ubuntu/Debian 服务器（2GB+ RAM）
- Docker 和 Docker Compose
- GitHub 仓库访问权限

---

## 步骤 1: 服务器准备（5分钟）

```bash
# SSH 登录服务器
ssh user@your-server-ip

# 安装 Docker
curl -fsSL https://get.docker.com | sh
sudo systemctl enable docker
sudo apt-get install docker-compose-plugin -y

# 创建目录
sudo mkdir -p /opt/faa/{backups,logs,data,scripts}
sudo chown -R $USER:$USER /opt/faa

# 克隆代码
cd /opt/faa
git clone https://github.com/YOUR_USERNAME/family-ai-assistant.git
```

---

## 步骤 2: 配置环境变量（3分钟）

```bash
cd /opt/faa/family-ai-assistant
cp .env.example .env
nano .env
```

**最小配置**（必须修改）:

```env
# 数据库密码（改成强密码）
POSTGRES_PASSWORD=your_strong_password

# LLM 配置
OPENAI_API_KEY=sk-your-api-key
OPENAI_MODEL=gpt-4o-mini

# 安全密钥（随机字符串）
SECRET_KEY=your_random_secret_key

# 用户 ID（你的 Threema ID）
ALLOWED_USERS=ABCDEFGH
```

保存并退出。

---

## 步骤 3: 首次启动测试（2分钟）

```bash
cd /opt/faa/family-ai-assistant

# 启动服务
docker-compose up -d

# 等待 20 秒
sleep 20

# 测试健康检查
curl http://localhost:8001/health

# 查看日志
docker-compose logs --tail=50
```

看到 `{"status": "healthy"}` 就成功了！

---

## 步骤 4: 配置 GitHub CI/CD（10分钟）

### 4.1 生成 SSH 密钥

在**本地电脑**上：

```bash
# 生成密钥对
ssh-keygen -t ed25519 -f ~/.ssh/faa_deploy -C "faa-deploy"

# 复制公钥到服务器
ssh-copy-id -i ~/.ssh/faa_deploy.pub user@your-server-ip

# 测试免密登录
ssh -i ~/.ssh/faa_deploy user@your-server-ip "echo 连接成功"
```

### 4.2 配置 GitHub Secrets

访问 GitHub 仓库: **Settings → Secrets and variables → Actions → New repository secret**

添加以下 Secrets:

| 名称 | 值 | 说明 |
|------|-----|------|
| `SSH_HOST` | `your.server.ip` | 服务器 IP |
| `SSH_USER` | `your_username` | SSH 用户名 |
| `SSH_KEY` | 私钥内容 | `cat ~/.ssh/faa_deploy` 的完整输出 |
| `POSTGRES_PASSWORD` | 数据库密码 | 与 .env 一致 |
| `THREEMA_BOT_ID` | `*ABCDEFG` | （可选）通知用 |
| `THREEMA_ADMIN_ID` | `YOUR_ID` | （可选）接收通知 |
| `THREEMA_SECRET` | secret | （可选）Threema 密钥 |

### 4.3 复制部署脚本

在**服务器**上：

```bash
# 复制脚本
sudo cp /opt/faa/family-ai-assistant/scripts/*.sh /opt/faa/scripts/
sudo chmod +x /opt/faa/scripts/*.sh

# 测试部署脚本
/opt/faa/scripts/deploy.sh
```

---

## 步骤 5: 配置自动监控（5分钟）

```bash
# 在服务器上配置 crontab
crontab -e

# 添加以下行（复制粘贴）
*/5 * * * * /opt/faa/scripts/health_check.sh
0 2 * * * docker-compose -f /opt/faa/family-ai-assistant/docker-compose.yml exec -T postgres pg_dump -U faa family_assistant > /opt/faa/backups/db_$(date +\%Y\%m\%d).sql
```

保存退出。

---

## 完成！测试自动部署

### 本地推送代码触发部署：

```bash
# 在本地修改代码
echo "# Test deploy" >> README.md
git add .
git commit -m "测试自动部署"
git push origin main

# 访问 GitHub Actions 查看部署状态
# https://github.com/YOUR_USERNAME/family-ai-assistant/actions
```

### 或手动触发部署：

1. 访问 GitHub: **Actions → Deploy FAA to Production**
2. 点击 **Run workflow**
3. 点击绿色按钮确认

---

## 日常使用

### 查看日志

```bash
# 服务器上
docker-compose logs -f faa-api
```

### 重启服务

```bash
docker-compose restart
```

### 回滚版本

```bash
/opt/faa/scripts/rollback.sh
```

### 查看服务状态

```bash
docker-compose ps
curl http://localhost:8001/health
```

---

## 故障排查

### 部署失败？

```bash
# 1. 查看日志
docker-compose logs --tail=100 faa-api

# 2. 检查环境变量
cat /opt/faa/family-ai-assistant/.env | grep -v "PASSWORD\|SECRET\|KEY"

# 3. 重新构建
docker-compose build --no-cache
docker-compose up -d
```

### GitHub Actions 连接不上服务器？

- 检查 SSH_HOST、SSH_USER 是否正确
- 检查 SSH_KEY 是否完整（包括 `-----BEGIN` 和 `-----END`）
- 在服务器上确认公钥已添加：`cat ~/.ssh/authorized_keys`

### 健康检查失败？

```bash
# 检查数据库
docker-compose exec postgres pg_isready -U faa

# 检查 API 服务
docker-compose logs faa-api | tail -50

# 手动重启
docker-compose restart faa-api
```

---

## 下一步

- ✅ 配置 Nginx 反向代理（HTTPS）
- ✅ 配置防火墙
- ✅ 设置 Threema webhook
- 📖 阅读完整文档：[DEPLOYMENT.md](./DEPLOYMENT.md)

---

**有问题？** 查看 [完整部署文档](./DEPLOYMENT.md) 或检查 GitHub Issues。

