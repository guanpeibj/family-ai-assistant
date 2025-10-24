# FAA 部署和运维指南

本文档介绍 Family AI Assistant 的生产部署和日常运维操作。

## 目录

- [系统架构](#系统架构)
- [首次部署](#首次部署)
- [日志管理](#日志管理)
- [文件管理](#文件管理)
- [CI/CD 流程](#cicd-流程)
- [日常运维](#日常运维)
- [故障排查](#故障排查)
- [安全建议](#安全建议)

---

## 系统架构

```
┌─────────────────────────────────────────────────────┐
│  GitHub Repository                                   │
│  └─ Push to main/master                             │
└───────────────┬─────────────────────────────────────┘
                │
                ↓
┌─────────────────────────────────────────────────────┐
│  GitHub Actions                                      │
│  ├─ 运行测试                                         │
│  ├─ SSH 到服务器                                     │
│  └─ 执行部署脚本                                     │
└───────────────┬─────────────────────────────────────┘
                │
                ↓
┌─────────────────────────────────────────────────────┐
│  生产服务器 (/opt/faa)                              │
│  ├─ Docker Compose (3 services)                     │
│  │   ├─ postgres (数据库)                           │
│  │   ├─ faa-api (API 服务)                         │
│  │   └─ faa-mcp (MCP 工具服务)                     │
│  ├─ 日志 (Docker 原生轮转)                          │
│  └─ 自动备份和健康检查                              │
└─────────────────────────────────────────────────────┘
```

---

## 首次部署

### 1. 服务器准备

#### 1.1 系统要求
- Ubuntu 20.04+ / Debian 11+
- Docker 20.10+
- Docker Compose 2.0+
- 至少 2GB RAM
- 至少 20GB 磁盘空间

#### 1.2 安装 Docker

```bash
# 安装 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 启动 Docker 服务
sudo systemctl enable docker
sudo systemctl start docker

# 安装 Docker Compose
sudo apt-get update
sudo apt-get install docker-compose-plugin
```

### 2. 创建目录结构

```bash
# 创建 FAA 根目录
sudo mkdir -p /opt/faa
cd /opt/faa

# 创建必要的子目录
sudo mkdir -p backups logs data scripts

# 设置权限（根据实际部署用户调整）
sudo chown -R $USER:$USER /opt/faa
```

### 3. 克隆代码仓库

```bash
cd /opt/faa
git clone https://github.com/YOUR_USERNAME/family-ai-assistant.git
cd family-ai-assistant
```

### 4. 配置环境变量

创建 `.env` 文件（**不要提交到 Git**）：

```bash
cd /opt/faa/family-ai-assistant
cp .env.example .env
nano .env
```

必须配置的环境变量：

```env
# 数据库
POSTGRES_PASSWORD=your_strong_password_here

# LLM 配置
OPENAI_API_KEY=sk-your-api-key
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1

# 安全
SECRET_KEY=your_secret_key_here
ALLOWED_USERS=user1,user2

# 应用设置
APP_ENV=production
DEBUG=false
LOG_LEVEL=INFO

# Threema（可选）
THREEMA_GATEWAY_ID=*ABCDEFG
THREEMA_SECRET=your_threema_secret
```

### 5. 复制部署脚本

```bash
# 复制脚本到 /opt/faa/scripts
sudo cp /opt/faa/family-ai-assistant/scripts/*.sh /opt/faa/scripts/

# 添加执行权限
sudo chmod +x /opt/faa/scripts/*.sh
```

### 6. 配置 SSH 密钥（用于 CI/CD）

#### 6.1 生成 SSH 密钥对

```bash
# 在本地生成密钥对
ssh-keygen -t ed25519 -C "github-actions-faa" -f ~/.ssh/faa_deploy

# 将公钥添加到服务器
ssh-copy-id -i ~/.ssh/faa_deploy.pub user@your-server-ip
```

#### 6.2 配置 GitHub Secrets

在 GitHub 仓库设置中添加以下 Secrets（Settings → Secrets and variables → Actions）：

```
SSH_HOST=your.server.ip
SSH_USER=your_username
SSH_KEY=<私钥内容，cat ~/.ssh/faa_deploy>
SSH_PORT=22

POSTGRES_PASSWORD=<与服务器 .env 一致>
THREEMA_BOT_ID=*YOUR_BOT_ID
THREEMA_ADMIN_ID=YOUR_ADMIN_ID
THREEMA_SECRET=<Threema secret>
```

### 7. 首次启动服务

```bash
cd /opt/faa/family-ai-assistant

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 检查服务状态
docker-compose ps

# 测试健康检查
curl http://localhost:8001/health
```

### 8. 配置定时任务

```bash
# 编辑 crontab
crontab -e

# 添加以下任务
# 每 5 分钟执行健康检查
*/5 * * * * /opt/faa/scripts/health_check.sh

# 每小时执行日志监控（可选）
0 * * * * /opt/faa/scripts/log_monitor.sh

# 每天凌晨 2 点备份数据库（可选）
0 2 * * * docker-compose -f /opt/faa/family-ai-assistant/docker-compose.yml exec -T postgres pg_dump -U faa family_assistant > /opt/faa/backups/db_$(date +\%Y\%m\%d).sql
```

---

## 日志管理

### Docker 原生日志轮转

FAA 使用 Docker 的原生日志轮转功能，无需额外配置：

- **单文件最大**: 50MB
- **保留文件数**: 10 个
- **自动压缩**: 是
- **日志格式**: JSON（生产环境）

### 查看日志

```bash
# 查看所有服务日志
docker-compose logs

# 查看特定服务日志
docker-compose logs faa-api
docker-compose logs faa-mcp
docker-compose logs postgres

# 实时跟踪日志
docker-compose logs -f faa-api

# 查看最近 100 行
docker-compose logs --tail=100 faa-api

# 查看特定时间范围
docker-compose logs --since 2024-01-01T00:00:00 --until 2024-01-02T00:00:00
```

### 日志位置

Docker 日志文件位于：

```
/var/lib/docker/containers/<container-id>/<container-id>-json.log
```

可以使用以下命令直接访问：

```bash
# 查找容器 ID
docker ps

# 查看日志文件
sudo tail -f /var/lib/docker/containers/<container-id>/<container-id>-json.log
```

### 日志分析

```bash
# 查找错误
docker-compose logs faa-api | grep -i error

# 统计错误数量
docker-compose logs faa-api | grep -i error | wc -l

# 查找特定用户的日志
docker-compose logs faa-api | grep "user_id=ABCDEFGH"

# 导出日志
docker-compose logs --no-color faa-api > faa-api-$(date +%Y%m%d).log
```

---

## 文件管理

FAA 使用 Docker Named Volumes 存储持久化数据，这是 Docker 的最佳实践。

### 文件存储策略

```
📦 postgres_data       - 数据库文件（Named Volume）
📦 media_data         - 媒体文件（Named Volume）  
📦 fastembed_cache    - 模型缓存（Named Volume）
📄 应用日志            - Docker 日志驱动管理
```

### Docker Named Volumes 优势

- ✅ **性能好**：特别是 Mac/Windows 环境
- ✅ **跨平台**：无需修改配置
- ✅ **自动管理**：Docker 处理权限和路径
- ✅ **易迁移**：容器迁移简单

### 查看 Volume 信息

```bash
# 列出所有 volumes
docker volume ls

# 查看详细信息（包括实际路径）
docker volume inspect family-ai-assistant_media_data

# 查看使用情况
docker system df -v
```

### Volume 实际位置

```bash
# Linux 宿主机路径
/var/lib/docker/volumes/family-ai-assistant_postgres_data/_data
/var/lib/docker/volumes/family-ai-assistant_media_data/_data
/var/lib/docker/volumes/family-ai-assistant_fastembed_cache/_data
```

### 备份 Volumes

```bash
# 备份数据库（推荐方式）
docker-compose exec -T postgres pg_dump -U faa family_assistant | gzip > db_backup.sql.gz

# 备份媒体文件
docker run --rm \
  -v family-ai-assistant_media_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/media_backup.tar.gz /data

# 备份模型缓存（通常不需要）
docker run --rm \
  -v family-ai-assistant_fastembed_cache:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/cache_backup.tar.gz /data
```

### 恢复 Volumes

```bash
# 恢复数据库
gunzip < db_backup.sql.gz | docker-compose exec -T postgres psql -U faa family_assistant

# 恢复媒体文件
docker run --rm \
  -v family-ai-assistant_media_data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/media_backup.tar.gz -C /
```

### 清理和维护

```bash
# 查看文件大小
docker-compose exec faa-api du -sh /data/*

# 清理临时文件
docker-compose exec faa-api find /data/media/temp -mtime +7 -delete

# 监控磁盘空间
docker-compose exec faa-api df -h /data
```

**详细文件管理指南**：请参考 [FILE_MANAGEMENT.md](./FILE_MANAGEMENT.md)

---

## CI/CD 流程

### 自动部署（Push 触发）

1. 推送代码到 `main` 或 `master` 分支
2. GitHub Actions 自动触发工作流
3. 运行测试（可选）
4. SSH 到服务器执行部署脚本
5. 自动备份、构建、部署、健康检查
6. 发送 Threema 通知（成功/失败）

```bash
# 本地推送代码
git add .
git commit -m "部署新功能"
git push origin main

# GitHub Actions 自动部署
# 查看部署状态: https://github.com/YOUR_REPO/actions
```

### 手动部署（GitHub 界面）

1. 访问仓库的 Actions 页面
2. 选择 "Deploy FAA to Production"
3. 点击 "Run workflow"
4. 选择是否跳过测试
5. 点击 "Run workflow" 确认

### 服务器端手动部署

```bash
# 直接在服务器上执行部署脚本
cd /opt/faa
./scripts/deploy.sh
```

---

## 日常运维

### 查看服务状态

```bash
cd /opt/faa/family-ai-assistant

# 查看所有服务状态
docker-compose ps

# 查看容器资源使用
docker stats

# 查看磁盘使用
df -h
du -sh /opt/faa/*
```

### 重启服务

```bash
# 重启所有服务
docker-compose restart

# 重启特定服务
docker-compose restart faa-api

# 完全停止并重新启动
docker-compose down
docker-compose up -d
```

### 更新服务

```bash
# 拉取最新代码
cd /opt/faa/family-ai-assistant
git pull

# 重新构建并启动
docker-compose build
docker-compose up -d
```

### 数据库维护

```bash
# 进入数据库容器
docker-compose exec postgres psql -U faa family_assistant

# 备份数据库
docker-compose exec -T postgres pg_dump -U faa family_assistant > backup_$(date +%Y%m%d).sql

# 恢复数据库
docker-compose exec -T postgres psql -U faa family_assistant < backup.sql

# 查看数据库大小
docker-compose exec postgres psql -U faa family_assistant -c "SELECT pg_size_pretty(pg_database_size('family_assistant'));"
```

### 清理和优化

```bash
# 清理未使用的 Docker 资源
docker system prune -f

# 清理旧镜像
docker image prune -a -f

# 清理旧备份（保留最近 30 个）
cd /opt/faa/backups
ls -t | tail -n +31 | xargs rm -rf
```

---

## 故障排查

### 服务无法启动

```bash
# 查看详细日志
docker-compose logs --tail=200 faa-api

# 检查容器状态
docker-compose ps

# 检查端口占用
sudo netstat -tulpn | grep 8001
sudo netstat -tulpn | grep 15432

# 重新构建（清除缓存）
docker-compose build --no-cache
docker-compose up -d
```

### 健康检查失败

```bash
# 检查 API 健康状态
curl http://localhost:8001/health

# 检查数据库连接
docker-compose exec postgres pg_isready -U faa

# 进入容器调试
docker-compose exec faa-api bash
```

### 数据库问题

```bash
# 检查数据库日志
docker-compose logs postgres

# 进入数据库查看连接
docker-compose exec postgres psql -U faa family_assistant
SELECT * FROM pg_stat_activity;

# 重启数据库
docker-compose restart postgres
```

### 磁盘空间不足

```bash
# 查看磁盘使用
df -h

# 清理 Docker 资源
docker system prune -a -f --volumes

# 清理日志（谨慎操作）
docker-compose logs --no-color > temp.log && echo "" > temp.log
```

### 回滚到上一个版本

```bash
# 使用回滚脚本
cd /opt/faa
./scripts/rollback.sh

# 选择要回滚的版本
# 脚本会自动停止服务、回滚代码、重新启动
```

---

## 安全建议

### 1. 网络安全

```bash
# 配置防火墙（UFW）
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable

# 仅允许本地访问 FAA 端口（通过 Nginx 反向代理）
# 不要直接暴露 8001 端口到公网
```

### 2. SSH 安全

```bash
# 禁用密码登录（仅使用密钥）
sudo nano /etc/ssh/sshd_config
# 设置: PasswordAuthentication no
sudo systemctl restart sshd
```

### 3. 环境变量保护

```bash
# 确保 .env 文件不可被其他用户读取
chmod 600 /opt/faa/family-ai-assistant/.env

# 定期更新密钥
# 1. 更新 .env 中的 SECRET_KEY, POSTGRES_PASSWORD
# 2. 更新 GitHub Secrets
# 3. 重新部署服务
```

### 4. 定期更新

```bash
# 更新系统包
sudo apt update && sudo apt upgrade -y

# 更新 Docker
sudo apt-get install --only-upgrade docker-ce docker-compose-plugin

# 更新 FAA 依赖
cd /opt/faa/family-ai-assistant
git pull
docker-compose build --no-cache
docker-compose up -d
```

### 5. 备份策略

- **每日自动备份**: 数据库
- **每次部署前备份**: 代码和容器状态
- **保留 30 天备份**: 自动清理旧备份
- **异地备份**: 定期将重要备份上传到云存储

```bash
# 手动完整备份
cd /opt/faa
tar -czf faa_backup_$(date +%Y%m%d).tar.gz \
    family-ai-assistant/.env \
    data/ \
    logs/ \
    $(docker-compose exec -T postgres pg_dump -U faa family_assistant)
```

---

## 常用命令速查

```bash
# === 部署相关 ===
/opt/faa/scripts/deploy.sh          # 部署
/opt/faa/scripts/rollback.sh        # 回滚
/opt/faa/scripts/health_check.sh    # 健康检查

# === 备份和恢复 ===
/opt/faa/scripts/backup_volumes.sh  # 完整备份（数据库 + 媒体）
/opt/faa/scripts/restore_volumes.sh # 交互式恢复
/opt/faa/scripts/disk_monitor.sh    # 磁盘监控

# === 日志 ===
docker-compose logs -f faa-api      # 实时日志
docker-compose logs --tail=100      # 最近 100 行
docker-compose logs --since 1h      # 最近 1 小时

# === 服务管理 ===
docker-compose restart              # 重启服务
docker-compose ps                   # 查看状态
docker-compose exec faa-api bash    # 进入容器

# === Volume 管理 ===
docker volume ls                    # 列出 volumes
docker volume inspect <name>        # 查看详情
docker system df -v                 # 查看使用情况

# === 清理 ===
docker system prune -f              # 清理未使用资源
docker image prune -a -f            # 清理旧镜像
docker volume prune -f              # 清理未使用 volumes（⚠️谨慎）
```

---

## 联系和支持

如遇到问题，请：

1. 查看日志：`docker-compose logs`
2. 检查 GitHub Actions 工作流状态
3. 运行健康检查脚本
4. 查看本文档的故障排查部分

---

**最后更新**: 2025-01-24
**版本**: 1.0

