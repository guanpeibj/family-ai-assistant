# Docker Compose 多环境配置指南

本文档说明 FAA 项目如何使用 Docker Compose 的多文件机制实现开发和生产环境的灵活切换。

## 📁 文件结构

```
family-ai-assistant/
├── docker-compose.yml                 # 基础配置（生产环境）
├── docker-compose.dev.yml             # 开发环境覆盖配置
├── docker-compose.override.yml        # 本地自动加载（git ignore）
└── docker-compose.override.yml.example # 开发配置模板
```

## 🎯 设计理念

### Docker Compose 文件合并机制

Docker Compose 会按以下顺序自动合并配置文件：

```
1. docker-compose.yml         (基础配置)
2. docker-compose.override.yml (如果存在，自动加载)
```

**优势**：
- ✅ 开发者本地有 `override.yml` → 自动开发模式
- ✅ 生产服务器无 `override.yml` → 自动生产模式
- ✅ 无需修改 `docker-compose.yml`
- ✅ 每个开发者可以有自己的本地配置

---

## 🚀 快速开始

### 方式 1: 使用脚本（推荐）

```bash
# 1. 配置开发环境
./scripts/dev-setup.sh

# 2. 启动
docker-compose up -d

# 3. 查看日志
docker-compose logs -f
```

### 方式 2: 使用 Makefile

```bash
# 配置开发环境
make dev-setup

# 启动开发环境
make dev-up

# 查看日志
make dev-logs

# 停止
make dev-down
```

### 方式 3: 手动配置

```bash
# 1. 复制开发配置
cp docker-compose.override.yml.example docker-compose.override.yml

# 2. 启动（自动加载 override）
docker-compose up -d
```

---

## 🔧 开发环境

### 配置特点

**docker-compose.yml** (基础):
```yaml
services:
  faa-api:
    build:
      dockerfile: docker/Dockerfile  # 生产 Dockerfile
    volumes:
      - media_data:/data/media       # 最小化挂载
    command: uvicorn ... # 无 --reload
```

**docker-compose.override.yml** (覆盖):
```yaml
services:
  faa-api:
    build:
      dockerfile: docker/Dockerfile.dev  # 开发 Dockerfile
    volumes:
      - ./src:/app/src                   # 挂载源代码
      - ./config:/app/config
      # ... 更多开发用挂载
    command: uvicorn ... --reload        # 热重载
    environment:
      - DEBUG=true
      - LOG_LEVEL=DEBUG
```

**合并后效果**：
- 使用开发 Dockerfile
- 源代码挂载（热重载）
- 启用 --reload
- 调试模式开启

### 启动命令

```bash
# 标准启动（自动使用 override）
docker-compose up -d

# 查看生效的完整配置
docker-compose config

# 查看服务状态
docker-compose ps
```

### 常用操作

```bash
# 重启服务
docker-compose restart

# 查看日志
docker-compose logs -f faa-api

# 进入容器
docker-compose exec faa-api bash

# 重新构建
docker-compose build
docker-compose up -d
```

---

## 🏭 生产环境

### 特点

生产服务器**不应该有** `docker-compose.override.yml` 文件。

**只使用 docker-compose.yml**：
- 生产 Dockerfile
- 最小化 volumes
- 无 --reload
- 生产级日志配置

### 部署方式

#### 方式 1: 自动部署（推荐）

```bash
# 本地推送代码
git push origin main

# GitHub Actions 自动部署到生产服务器
# 生产服务器执行 docker-compose up -d
# 不会有 override.yml，自动使用生产配置
```

#### 方式 2: 手动部署

```bash
# 在服务器上
cd /opt/faa/family-ai-assistant

# 确保没有 override 文件
ls docker-compose.override.yml  # 应该不存在

# 部署
./scripts/deploy.sh

# 或直接
docker-compose up -d  # 仅使用 docker-compose.yml
```

#### 方式 3: 显式指定（保险）

```bash
# 显式只使用 docker-compose.yml
docker-compose -f docker-compose.yml up -d
```

---

## 🔀 环境切换

### 开发 → 生产

```bash
# 方式 1: 删除 override 文件
rm docker-compose.override.yml
docker-compose down
docker-compose up -d

# 方式 2: 显式指定
docker-compose -f docker-compose.yml down
docker-compose -f docker-compose.yml up -d
```

### 生产 → 开发

```bash
# 创建 override 文件
cp docker-compose.override.yml.example docker-compose.override.yml

# 重启
docker-compose down
docker-compose up -d
```

---

## 📋 可用的 Compose 文件

### 1. docker-compose.yml
**用途**: 基础配置（生产环境）

```bash
# 单独使用（生产）
docker-compose -f docker-compose.yml up -d
```

### 2. docker-compose.dev.yml
**用途**: 开发环境覆盖配置（提交到 Git）

```bash
# 显式使用开发配置
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

### 3. docker-compose.override.yml
**用途**: 本地自动加载（不提交到 Git）

```bash
# 从模板创建
cp docker-compose.override.yml.example docker-compose.override.yml

# 自动加载
docker-compose up -d
```

### 4. docker-compose.override.yml.example
**用途**: 开发配置模板（提交到 Git）

新开发者快速开始的模板。

---

## 🎨 自定义配置

### 个人开发配置

每个开发者可以根据需要自定义 `docker-compose.override.yml`：

```yaml
version: '3.8'

services:
  faa-api:
    # 自定义端口
    ports:
      - "8080:8000"  # 改为 8080
    
    # 额外的环境变量
    environment:
      - MY_CUSTOM_VAR=value
    
    # 额外的 volumes
    volumes:
      - ./my-local-data:/data/extra
```

因为此文件在 `.gitignore` 中，不会影响其他开发者。

---

## 🔍 调试和验证

### 查看生效的配置

```bash
# 查看合并后的完整配置
docker-compose config

# 查看特定服务的配置
docker-compose config faa-api

# 查看使用的文件
docker-compose config --services
```

### 验证环境

```bash
# 检查是否使用开发配置
docker-compose exec faa-api env | grep -E "DEBUG|APP_ENV|LOG_LEVEL"

# 应该看到（开发环境）：
# DEBUG=true
# APP_ENV=development
# LOG_LEVEL=DEBUG

# 检查是否挂载了源代码
docker-compose exec faa-api ls -la /app/src

# 检查是否启用了 --reload
docker-compose logs faa-api | grep reload
```

### 常见问题

#### 问题 1: 不确定使用的是哪个配置

```bash
# 方法 1: 检查环境变量
docker-compose exec faa-api env | grep APP_ENV

# 方法 2: 查看完整配置
docker-compose config | grep -A 5 "dockerfile"

# 方法 3: 检查是否有 override 文件
ls -la docker-compose.override.yml
```

#### 问题 2: 修改代码不生效

```bash
# 1. 检查是否挂载了源代码
docker-compose exec faa-api ls -la /app/src

# 2. 检查是否启用了 --reload
docker-compose logs faa-api | grep "Uvicorn running"

# 3. 确保使用了 override
docker-compose config | grep "Dockerfile.dev"
```

#### 问题 3: 生产环境意外使用了开发配置

```bash
# 检查是否有 override 文件
ls /opt/faa/family-ai-assistant/docker-compose.override.yml

# 如果存在，删除它
rm /opt/faa/family-ai-assistant/docker-compose.override.yml

# 重启服务
docker-compose down
docker-compose up -d
```

---

## 📚 Makefile 命令参考

项目提供了 Makefile 简化操作：

```bash
# 查看所有命令
make help

# 开发环境
make dev-setup     # 配置开发环境
make dev-up        # 启动
make dev-down      # 停止
make dev-logs      # 查看日志
make dev-restart   # 重启
make dev-shell     # 进入容器

# 生产环境
make prod-up       # 启动（会检查 override）
make prod-down     # 停止
make prod-logs     # 查看日志
make prod-build    # 重新构建

# 其他
make ps            # 查看状态
make clean         # 清理
make backup        # 备份
```

---

## 🔐 最佳实践

### 开发环境

```bash
✅ DO:
  - 使用 docker-compose.override.yml
  - 挂载源代码实现热重载
  - 启用 DEBUG 和详细日志
  - 使用 Dockerfile.dev

❌ DON'T:
  - 提交 docker-compose.override.yml 到 Git
  - 在生产环境使用开发配置
  - 硬编码个人配置到 docker-compose.yml
```

### 生产环境

```bash
✅ DO:
  - 只使用 docker-compose.yml
  - 删除任何 override 文件
  - 使用 CI/CD 自动部署
  - 定期备份数据

❌ DON'T:
  - 在生产环境使用 --reload
  - 挂载源代码到生产容器
  - 在生产环境使用 DEBUG=true
```

---

## 📖 相关文档

- [环境配置指南](./ENVIRONMENT_SETUP.md) - 详细的环境对比
- [部署文档](./DEPLOYMENT.md) - 生产部署指南
- [快速开始](./QUICK_START_DEPLOY.md) - 快速上手

---

**最后更新**: 2025-01-24  
**维护者**: FAA 团队

