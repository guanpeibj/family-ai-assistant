# FAA 环境配置指南

本文档说明 FAA 项目的生产环境和开发环境配置及启动方式。

## 📊 环境对比总览

| 特性 | 开发环境 | 生产环境 |
|------|---------|---------|
| **Dockerfile** | `Dockerfile.dev` | `Dockerfile` |
| **代码挂载** | 热重载（Bind Mount） | 构建到镜像 |
| **调试工具** | ✅ ipython, vim, curl | ❌ 无 |
| **日志级别** | DEBUG | INFO |
| **日志输出** | 彩色控制台 | JSON 格式 |
| **uvicorn** | `--reload` | 无 reload |
| **FastEmbed** | 可能需要手动下载 | 镜像预下载 |
| **配置验证** | 宽松 | 严格 |
| **启动方式** | 本地 docker-compose | 服务器自动部署 |

---

## 🔧 一、开发环境

### 1.1 特点

```
目标：快速开发、调试方便
特点：
  ✅ 代码热重载（保存即生效）
  ✅ 丰富的调试工具
  ✅ 详细的日志输出
  ✅ 快速启动（不重新构建）
```

### 1.2 Dockerfile 对比

**`docker/Dockerfile.dev`** 特点：

```dockerfile
# 额外的开发工具
RUN apt-get install -y \
    vim \
    curl \
    # ... 其他调试工具

# 安装开发依赖
RUN uv pip install httpx pytest pytest-asyncio ipython

# 可编辑安装（-e）
RUN uv pip install -e .
```

### 1.3 docker-compose.yml 配置

```yaml
services:
  faa-api:
    build:
      dockerfile: docker/Dockerfile.dev  # 使用开发 Dockerfile
    
    volumes:
      # 代码挂载 - 实现热重载
      - ./src:/app/src
      - ./config:/app/config
      - ./prompts:/app/prompts
      - ./scripts:/app/scripts
      - ./tests:/app/tests
    
    command: >
      sh -c "alembic upgrade head && 
             uvicorn src.api.main:app 
             --host 0.0.0.0 
             --port 8000 
             --reload"  # 热重载
    
    environment:
      - DEBUG=true
      - LOG_LEVEL=DEBUG
      - APP_ENV=development
```

### 1.4 .env 配置（开发）

```env
# 应用模式
APP_ENV=development
DEBUG=true
LOG_LEVEL=DEBUG

# 日志（开发环境可选文件输出）
LOG_DIR=logs

# 数据库（本地）
DATABASE_URL=postgresql://faa:faa_secret@postgres:5432/family_assistant
```

### 1.5 启动开发环境

```bash
# 方式 1: 使用 override 机制（推荐）⭐
# 一次性配置
./scripts/dev-setup.sh
# 或手动复制
cp docker-compose.override.yml.example docker-compose.override.yml

# 启动（自动使用开发配置）
docker-compose up -d

# 方式 2: 使用 Makefile
make dev-setup  # 配置
make dev-up     # 启动

# 方式 3: 显式指定开发配置文件
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# 方式 4: 本地直接运行（不使用 Docker）
cd /Users/biomind/code/family-ai-assistant

# 创建虚拟环境
python3.12 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -e .

# 配置环境变量
cp env.example .env
nano .env  # 修改配置

# 启动数据库（Docker）
docker-compose up -d postgres

# 运行迁移
alembic upgrade head

# 启动 API（本地）
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# 启动 MCP 服务（另一个终端）
python mcp-server/mcp_http_wrapper.py
```

### 1.6 开发工作流

```bash
# 1. 修改代码
vim src/ai_engine.py

# 2. 保存后自动重载（无需重启）
# uvicorn --reload 自动检测文件变化

# 3. 测试
curl http://localhost:8001/health

# 4. 查看日志
docker-compose logs -f faa-api

# 5. 进入容器调试
docker-compose exec faa-api bash
python -m IPython  # 使用 IPython 调试
```

---

## 🚀 二、生产环境

### 2.1 特点

```
目标：稳定、高性能、安全
特点：
  ✅ 代码构建到镜像（不可变）
  ✅ 最小化依赖（减小镜像）
  ✅ 结构化日志（JSON）
  ✅ 自动部署和监控
  ✅ 性能优化
```

### 2.2 Dockerfile 对比

**`docker/Dockerfile`** 特点：

```dockerfile
# 只安装必要的系统依赖
RUN apt-get install -y \
    gcc \
    postgresql-client \
    git

# 只安装生产依赖
RUN uv pip install -e .

# 预下载 FastEmbed 模型
RUN python scripts/preload_fastembed.py

# 固定启动命令（无 --reload）
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 2.3 docker-compose.yml 配置

```yaml
services:
  faa-api:
    build:
      dockerfile: docker/Dockerfile  # 使用生产 Dockerfile
    
    volumes:
      # 最小化挂载（生产环境不挂载源代码）
      - media_data:/data/media
      - fastembed_cache:/data/fastembed_cache
      
      # 只读挂载必要文件
      - ./family_private_data.json:/app/family_private_data.json:ro
    
    command: >
      sh -c "alembic upgrade head && 
             uvicorn src.api.main:app 
             --host 0.0.0.0 
             --port 8000"  # 无 --reload
    
    environment:
      - DEBUG=false
      - LOG_LEVEL=INFO
      - APP_ENV=production
      - LOG_DIR=  # 空，由 Docker 管理日志
    
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "10"
        compress: "true"
```

### 2.4 .env 配置（生产）

```env
# 应用模式
APP_ENV=production
DEBUG=false
LOG_LEVEL=INFO

# 日志（生产环境由 Docker 管理）
LOG_DIR=

# 数据库（生产）
DATABASE_URL=postgresql://faa:STRONG_PASSWORD@postgres:5432/family_assistant
POSTGRES_PASSWORD=STRONG_PASSWORD

# 安全
SECRET_KEY=random_strong_secret_key_here
ALLOWED_USERS=USER1,USER2
```

### 2.5 启动生产环境

#### 方式 1: 服务器首次部署

```bash
# 1. 服务器准备
ssh user@your-server

# 2. 安装 Docker
curl -fsSL https://get.docker.com | sh

# 3. 创建目录
sudo mkdir -p /opt/faa/{backups,logs,scripts}
cd /opt/faa

# 4. 克隆代码
git clone https://github.com/YOUR_REPO/family-ai-assistant.git
cd family-ai-assistant

# 5. 配置环境
cp env.example .env
nano .env  # 修改为生产配置

# 6. 启动服务
docker-compose up -d

# 7. 检查健康
curl http://localhost:8001/health
```

#### 方式 2: CI/CD 自动部署

```bash
# 本地推送代码
git add .
git commit -m "部署新功能"
git push origin main

# GitHub Actions 自动执行：
# 1. 运行测试
# 2. SSH 到服务器
# 3. 执行 /opt/faa/scripts/deploy.sh
# 4. 健康检查
# 5. 发送通知
```

#### 方式 3: 手动部署

```bash
# 在服务器上执行
cd /opt/faa
./scripts/deploy.sh

# 脚本会自动：
# 1. 备份当前版本
# 2. 拉取最新代码
# 3. 构建镜像
# 4. 重启服务
# 5. 健康检查
```

### 2.6 生产运维

```bash
# 查看日志
docker-compose logs -f faa-api

# 查看服务状态
docker-compose ps

# 重启服务
docker-compose restart

# 回滚版本
/opt/faa/scripts/rollback.sh

# 备份数据
/opt/faa/scripts/backup_volumes.sh

# 监控磁盘
/opt/faa/scripts/disk_monitor.sh
```

---

## 🔄 三、环境切换

### 3.1 开发 → 生产（新方式）✨

使用 docker-compose override 机制，无需修改文件：

```bash
# 简单方式：删除 override 文件
rm docker-compose.override.yml
docker-compose down
docker-compose up -d

# 显式方式：指定只用基础配置
docker-compose -f docker-compose.yml up -d
```

### 3.2 生产 → 开发（新方式）✨

```bash
# 创建 override 文件
cp docker-compose.override.yml.example docker-compose.override.yml

# 或使用脚本
./scripts/dev-setup.sh

# 重启
docker-compose down
docker-compose up -d

# 或使用 Makefile
make dev-setup
make dev-up
```

### 3.3 旧方式（手动修改，不推荐）

<details>
<summary>点击展开旧的手动修改方式</summary>

```bash
# 开发 → 生产
# 1. 修改 docker-compose.yml 的 dockerfile
# 2. 移除开发 volumes
# 3. 移除 --reload
# 4. 修改 .env

# 生产 → 开发
# 1. 修改 docker-compose.yml 的 dockerfile
# 2. 添加开发 volumes
# 3. 添加 --reload
# 4. 修改 .env
```

</details>

---

## 📋 四、关键差异说明

### 4.1 代码挂载

**开发环境**：
```yaml
volumes:
  - ./src:/app/src  # 代码修改实时生效
```

**生产环境**：
```yaml
# 代码已构建到镜像，无需挂载
# 修改代码需要重新构建镜像
```

### 4.2 热重载

**开发环境**：
```bash
uvicorn src.api.main:app --reload
# 保存文件自动重启服务
```

**生产环境**：
```bash
uvicorn src.api.main:app
# 无 --reload，性能更好，稳定性更高
```

### 4.3 日志输出

**开发环境**：
```python
# src/core/logging.py
if settings.DEBUG:
    # 彩色控制台，易读
    renderer = structlog.dev.ConsoleRenderer()
```

**生产环境**：
```python
# src/core/logging.py
else:
    # JSON 格式，便于解析和分析
    renderer = structlog.processors.JSONRenderer()
```

### 4.4 调试工具

**开发环境**：
```bash
# 可用工具
docker-compose exec faa-api bash
python -m IPython
vim
curl
```

**生产环境**：
```bash
# 最小化镜像，只有必要工具
docker-compose exec faa-api bash
python  # 基础 Python（无 IPython）
```

---

## 🎯 五、最佳实践

### 5.1 开发环境最佳实践

```bash
# 1. 使用代码挂载实现热重载
# 2. 启用详细日志（DEBUG）
# 3. 使用本地数据库
# 4. 安装调试工具
# 5. 配置 IDE 断点调试
```

### 5.2 生产环境最佳实践

```bash
# 1. 使用镜像构建（不挂载代码）
# 2. 最小化日志输出（INFO）
# 3. 强密码保护
# 4. 启用 CI/CD 自动部署
# 5. 配置健康检查和监控
# 6. 定期备份数据
# 7. 使用 HTTPS（Nginx 反向代理）
```

### 5.3 安全注意事项

```bash
# 生产环境必须做的事：
✅ 修改默认密码（POSTGRES_PASSWORD, SECRET_KEY）
✅ 限制 ALLOWED_USERS
✅ 配置防火墙
✅ 使用 HTTPS
✅ 定期更新依赖
✅ 不要暴露调试端口

# 开发环境可以放松：
⚪ 使用简单密码（但不要提交到 Git）
⚪ 允许所有用户
⚪ HTTP 即可
```

---

## 🔍 六、故障排查

### 问题 1: 开发环境代码修改不生效

```bash
# 检查是否挂载了代码
docker-compose exec faa-api ls -la /app/src

# 检查 uvicorn 是否启用了 --reload
docker-compose logs faa-api | grep reload

# 解决方案：确保 volumes 和 --reload 都配置了
```

### 问题 2: 生产环境性能差

```bash
# 检查是否错误启用了 --reload
docker-compose logs faa-api | grep reload

# 检查是否挂载了不必要的代码
docker-compose exec faa-api mount | grep /app/src

# 解决方案：移除 --reload 和代码挂载
```

### 问题 3: 日志格式不对

```bash
# 检查环境变量
docker-compose exec faa-api env | grep -E "DEBUG|APP_ENV"

# 解决方案：确保生产环境 DEBUG=false
```

---

## 📚 参考文档

- [部署文档](./DEPLOYMENT.md)
- [快速开始](./QUICK_START_DEPLOY.md)
- [文件管理](./FILE_MANAGEMENT.md)
- [CI/CD 配置](./GITHUB_ACTIONS_SETUP.md)

---

**最后更新**: 2025-01-24  
**维护者**: FAA 团队

