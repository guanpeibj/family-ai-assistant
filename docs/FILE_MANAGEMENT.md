# FAA 文件管理指南

本文档详细说明 FAA 项目的文件存储、备份和管理策略。

## 📂 文件存储架构

### Docker Named Volumes 策略

FAA 使用 Docker Named Volumes 存储持久化数据，这是最佳实践：

```
优点：
✅ 性能优异（特别是 Mac/Windows）
✅ 跨平台兼容
✅ Docker 自动管理权限
✅ 易于容器迁移和扩展

位置：
📁 /var/lib/docker/volumes/<project>_<volume_name>/_data
```

---

## 🗄️ 文件类型和存储策略

### 1. 数据库文件 (postgres_data)

**存储方式**：Docker Named Volume  
**实际路径**：`/var/lib/docker/volumes/family-ai-assistant_postgres_data/_data`  
**预计大小**：100MB ~ 数GB（随使用增长）

```yaml
# docker-compose.yml
volumes:
  - postgres_data:/var/lib/postgresql/data
```

**管理建议**：
- ✅ 每日自动备份（pg_dump）
- ✅ 定期监控大小
- ✅ 保留 30 天备份
- ❌ 不要直接操作文件

**备份命令**：
```bash
# 备份
docker-compose exec -T postgres pg_dump -U faa family_assistant | gzip > backup_$(date +%Y%m%d).sql.gz

# 恢复
gunzip < backup.sql.gz | docker-compose exec -T postgres psql -U faa family_assistant
```

---

### 2. 媒体文件 (media_data)

**存储方式**：Docker Named Volume  
**实际路径**：`/var/lib/docker/volumes/family-ai-assistant_media_data/_data`  
**预计大小**：100MB ~ 数十GB（随使用增长）

```yaml
# docker-compose.yml
volumes:
  - media_data:/data/media
```

**目录结构**：
```
media_data/
├── images/           # 图片文件
├── audio/            # 音频文件（语音消息）
├── videos/           # 视频文件
└── temp/             # 临时文件
```

**管理建议**：
- ✅ 定期备份重要文件
- ✅ 定期清理过期文件
- ✅ 监控磁盘空间
- ⚠️ 可能需要大量空间

**访问和备份**：
```bash
# 查看文件
docker-compose exec faa-api ls -lh /data/media

# 备份到宿主机
docker run --rm -v family-ai-assistant_media_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/media_backup_$(date +%Y%m%d).tar.gz /data

# 恢复
docker run --rm -v family-ai-assistant_media_data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/media_backup.tar.gz -C /
```

---

### 3. FastEmbed 模型缓存 (fastembed_cache)

**存储方式**：Docker Named Volume  
**实际路径**：`/var/lib/docker/volumes/family-ai-assistant_fastembed_cache/_data`  
**预计大小**：300MB ~ 500MB（固定）

```yaml
# docker-compose.yml
volumes:
  - fastembed_cache:/data/fastembed_cache
```

**管理建议**：
- ✅ 首次启动自动下载
- ✅ 可安全删除（会重新下载）
- ❌ 无需备份
- ℹ️ 加速启动时间

**清理和重建**：
```bash
# 删除缓存（会重新下载）
docker volume rm family-ai-assistant_fastembed_cache

# 重新启动（自动下载）
docker-compose up -d
```

---

### 4. 应用日志

**存储方式**：Docker 日志驱动  
**实际路径**：`/var/lib/docker/containers/<container-id>/<container-id>-json.log`  
**预计大小**：~500MB/服务（50MB × 10 个文件）

```yaml
# docker-compose.yml
logging:
  driver: "json-file"
  options:
    max-size: "50m"      # 单文件 50MB
    max-file: "10"       # 保留 10 个
    compress: "true"     # 自动压缩
```

**管理建议**：
- ✅ Docker 自动轮转
- ✅ 自动压缩旧日志
- ✅ 定期自动清理
- ❌ 无需手动管理

**查看日志**：
```bash
# 实时查看
docker-compose logs -f faa-api

# 查看最近 100 行
docker-compose logs --tail=100 faa-api

# 查看特定时间范围
docker-compose logs --since 2024-01-01T00:00:00
```

---

### 5. 开发文件（仅开发环境）

**存储方式**：Bind Mount（开发环境）  
**实际路径**：项目目录

```yaml
# docker-compose.yml (开发环境)
volumes:
  - ./src:/app/src              # 源代码
  - ./config:/app/config        # 配置文件
  - ./prompts:/app/prompts      # Prompt 模板
```

**管理建议**：
- ✅ 通过 Git 管理
- ✅ 热重载支持
- ⚠️ 生产环境移除

---

## 📊 磁盘空间监控

### 查看 Volume 使用情况

```bash
# 列出所有 volumes
docker volume ls

# 查看特定 volume 详情
docker volume inspect family-ai-assistant_postgres_data
docker volume inspect family-ai-assistant_media_data

# 查看 volume 大小
docker system df -v

# 进入容器查看
docker-compose exec faa-api df -h /data
```

### 推荐的监控脚本

```bash
#!/bin/bash
# scripts/disk_monitor.sh

# 检查 Docker volumes 大小
echo "=== Docker Volumes 使用情况 ==="
docker system df -v | grep -A 20 "Local Volumes"

# 检查容器内磁盘
echo ""
echo "=== 容器内磁盘使用 ==="
docker-compose exec -T faa-api df -h | grep -E "Filesystem|/data"

# 检查宿主机磁盘
echo ""
echo "=== 宿主机磁盘使用 ==="
df -h | grep -E "Filesystem|/var/lib/docker|/$"
```

---

## 🗑️ 清理策略

### 自动清理（Docker）

```bash
# 清理未使用的资源
docker system prune -f

# 清理未使用的 volumes（⚠️ 谨慎使用）
docker volume prune -f

# 清理未使用的镜像
docker image prune -a -f
```

### 手动清理媒体文件

```bash
# 进入容器
docker-compose exec faa-api bash

# 查找大于 30 天的文件
find /data/media -type f -mtime +30 -ls

# 删除大于 30 天的临时文件
find /data/media/temp -type f -mtime +30 -delete

# 查看空间使用
du -sh /data/media/*
```

### 清理旧日志

```bash
# Docker 日志已自动管理，无需手动清理

# 如果需要立即清理所有日志（⚠️ 谨慎）
docker-compose down
find /var/lib/docker/containers -name "*-json.log*" -delete
docker-compose up -d
```

---

## 💾 备份和恢复

### 完整备份策略

```bash
#!/bin/bash
# scripts/full_backup.sh

BACKUP_DIR="/opt/faa/backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "开始完整备份..."

# 1. 备份数据库
echo "备份数据库..."
docker-compose exec -T postgres pg_dump -U faa family_assistant | \
  gzip > "$BACKUP_DIR/database.sql.gz"

# 2. 备份媒体文件
echo "备份媒体文件..."
docker run --rm \
  -v family-ai-assistant_media_data:/data \
  -v "$BACKUP_DIR":/backup \
  alpine tar czf /backup/media.tar.gz /data

# 3. 备份配置文件
echo "备份配置..."
cp /opt/faa/family-ai-assistant/.env "$BACKUP_DIR/env.backup"
cp -r /opt/faa/family-ai-assistant/config "$BACKUP_DIR/"

# 4. 记录当前 Git 提交
cd /opt/faa/family-ai-assistant
git rev-parse HEAD > "$BACKUP_DIR/commit.txt"

echo "备份完成: $BACKUP_DIR"
du -sh "$BACKUP_DIR"
```

### 恢复流程

```bash
#!/bin/bash
# scripts/restore_backup.sh <backup_dir>

BACKUP_DIR="$1"

if [ ! -d "$BACKUP_DIR" ]; then
  echo "备份目录不存在: $BACKUP_DIR"
  exit 1
fi

echo "从 $BACKUP_DIR 恢复..."

# 1. 停止服务
docker-compose down

# 2. 恢复数据库
echo "恢复数据库..."
docker-compose up -d postgres
sleep 10
gunzip < "$BACKUP_DIR/database.sql.gz" | \
  docker-compose exec -T postgres psql -U faa family_assistant

# 3. 恢复媒体文件
echo "恢复媒体文件..."
docker run --rm \
  -v family-ai-assistant_media_data:/data \
  -v "$BACKUP_DIR":/backup \
  alpine tar xzf /backup/media.tar.gz -C /

# 4. 恢复配置
echo "恢复配置..."
cp "$BACKUP_DIR/env.backup" /opt/faa/family-ai-assistant/.env

# 5. 启动服务
docker-compose up -d

echo "恢复完成"
```

---

## 🔍 常用运维命令

### Volume 管理

```bash
# 查看 volume 列表
docker volume ls

# 查看 volume 详情（包括实际路径）
docker volume inspect family-ai-assistant_media_data

# 创建 volume
docker volume create my_volume

# 删除 volume（⚠️ 数据将丢失）
docker volume rm family-ai-assistant_fastembed_cache
```

### 文件访问

```bash
# 通过容器访问文件
docker-compose exec faa-api ls -lh /data/media
docker-compose exec faa-api cat /data/media/images/file.jpg

# 复制文件到宿主机
docker-compose cp faa-api:/data/media/file.jpg ./file.jpg

# 复制文件到容器
docker-compose cp ./file.jpg faa-api:/data/media/
```

### 空间统计

```bash
# Docker 系统空间使用
docker system df

# 详细信息（包括 volumes）
docker system df -v

# 特定容器的磁盘使用
docker-compose exec faa-api du -sh /data/*
```

---

## 📋 定期维护清单

### 每日

- ✅ 自动备份数据库（cron）
- ✅ 自动健康检查（cron）

### 每周

- ✅ 检查磁盘空间使用
- ✅ 查看日志是否有异常
- ✅ 检查备份是否正常

### 每月

- ✅ 清理旧备份（保留 30 天）
- ✅ 清理临时媒体文件
- ✅ Docker 系统清理
- ✅ 测试恢复流程

### 每季度

- ✅ 完整备份测试恢复
- ✅ 审查存储策略
- ✅ 评估是否需要扩容

---

## ⚠️ 注意事项

### 不要做的事情

1. ❌ 不要直接修改 `/var/lib/docker/volumes/` 下的文件
2. ❌ 不要在容器运行时删除 volumes
3. ❌ 不要手动修改 PostgreSQL 数据文件
4. ❌ 不要删除正在使用的 volumes

### 安全操作

1. ✅ 备份前先测试
2. ✅ 删除前先确认
3. ✅ 使用 Docker 命令操作 volumes
4. ✅ 重要操作前先做快照

---

## 🆘 故障排查

### Volume 权限问题

```bash
# 检查 volume 所有者
docker-compose exec faa-api ls -la /data

# 修复权限（在容器内）
docker-compose exec faa-api chown -R app:app /data
```

### Volume 空间不足

```bash
# 检查使用情况
docker system df -v

# 清理旧备份
find /opt/faa/backups -mtime +30 -delete

# 清理媒体临时文件
docker-compose exec faa-api find /data/media/temp -mtime +7 -delete

# 清理 Docker 未使用资源
docker system prune -a -f
```

### Volume 数据丢失

```bash
# 检查 volume 是否存在
docker volume ls | grep family-ai-assistant

# 从备份恢复
/opt/faa/scripts/restore_backup.sh /opt/faa/backups/20250124_120000
```

---

## 📚 参考资料

- [Docker Volumes 官方文档](https://docs.docker.com/storage/volumes/)
- [PostgreSQL 备份最佳实践](https://www.postgresql.org/docs/current/backup.html)
- [FAA 部署文档](./DEPLOYMENT.md)

---

**最后更新**: 2025-01-24  
**维护者**: FAA 团队

