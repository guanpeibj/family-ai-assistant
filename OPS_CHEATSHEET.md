### Docker / Docker Compose 运维速查

适用对象：日常本地/服务器部署与排障。以下命令默认使用 Docker Compose v2（docker compose）。如你的环境是 v1，请将命令中的 `docker compose` 替换为 `docker-compose`。

---

## 环境准备
- 在项目根目录创建 `.env`（参考 `env.example`）。
- 主要变量：`POSTGRES_PASSWORD`、`OPENAI_API_KEY`、`SECRET_KEY`。

```bash
# 检查当前 compose 版本
docker compose version

# 载入/查看 .env 变量
cat .env
```

---

## 快速启动/停止
```bash
# 构建并后台启动（首次或依赖变更后）
docker compose up -d --build

# 启动（已构建过）
docker compose up -d

# 停止服务（保留数据卷）
docker compose down

# 停止并移除网络（保留卷）
docker compose down --remove-orphans
```

---

## 查看状态与日志
```bash
# 查看服务状态
docker compose ps

# 查看某服务日志（持续追踪）
docker compose logs -f faa-api

# 查看所有服务最近 100 行日志
docker compose logs --tail=100
```

---

## 重建/滚动更新
```bash
# 仅重建 API 服务并重启
docker compose build faa-api && docker compose up -d faa-api

# 不使用缓存构建
docker compose build --no-cache faa-api

# 重新创建容器但不重建镜像
docker compose up -d --force-recreate faa-api
```

---

## 进入容器 / 执行命令
```bash
# 列出容器（含名称）
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'

# 进入 API 容器 shell
docker exec -it family-ai-assistant-faa-api-1 /bin/bash

# 在 API 容器中执行一次性命令（示例：pip list）
docker exec -it family-ai-assistant-faa-api-1 pip list

# 进入 MCP 容器
docker exec -it family-ai-assistant-faa-mcp-1 /bin/bash

# 进入 Postgres（psql）
docker exec -it family-ai-assistant-postgres-1 psql -U faa -d family_assistant
```

提示：容器名称可能因目录名或 Compose 版本不同而变化，可先 `docker compose ps` 确认。

---

## 健康检查与连通性
```bash
# API 健康检查
curl -f http://localhost:8000/health

# 测试 API 端口映射
curl -v http://localhost:8000/

# 测试 MCP 健康（若暴露）
curl -v http://localhost:9000/health || true
```

---

## 卷/网络管理（数据持久化）
```bash
# 列出卷
docker volume ls

# 查看卷占用
docker system df -v

# 删除未使用卷（谨慎）
docker volume prune -f

# 查看网络
docker network ls

# 检查网络详情
docker network inspect family-ai-assistant_default | jq '.' | less
```

注意：本项目的 Postgres 数据使用命名卷 `postgres_data`（见 docker-compose.yml），`down` 不会删除卷；如需清空数据库，请谨慎执行：
```bash
docker compose down
docker volume rm family-ai-assistant_postgres_data
docker compose up -d --build
```

---

## 清理与空间回收
```bash
# 删除无用数据（镜像、悬挂卷、构建缓存等）
docker system prune -f

# 更激进（包含未使用卷）
docker system prune -a --volumes -f

# 删除悬挂镜像
docker image prune -f
```

---

## 常见排障
```bash
# 查看容器资源
docker stats

# 查看容器低级事件
docker events

# 查看单容器详细信息（环境变量、挂载等）
docker inspect family-ai-assistant-faa-api-1 | jq '.' | less

# 检查端口占用
sudo lsof -iTCP -sTCP:LISTEN -n -P | grep ':8000\|:5432\|:9000'

# 直接测试容器内网络（在容器内执行）
curl -v http://faa-mcp:8000/health
nc -zv postgres 5432
```

---

## Compose 变量与覆盖
```bash
# 临时覆盖环境变量（一次性）
POSTGRES_PASSWORD=strong docker compose up -d

# 指定额外的 compose 覆盖文件
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## 项目相关快捷命令
```bash
# 一键部署（可参考 scripts/quick-deploy.sh / scripts/deploy.sh）
git pull && docker compose down && docker compose up -d --build

# 查看 API/MCP 日志
docker compose logs -f faa-api
docker compose logs -f faa-mcp

# 仅重启某服务
docker compose restart faa-api
```

---

## 参考
- docker docs: https://docs.docker.com/
- compose file v3: https://docs.docker.com/compose/compose-file/compose-file-v3/

---

## Alembic 数据库迁移（PostgreSQL）

环境变量与进入容器
```bash
# 设置连接串（本机直连，或在容器内读取）
export DATABASE_URL=postgresql://faa:faa@localhost:5432/family_assistant

# 进入 API 容器并加载环境后再执行 Alembic
docker compose exec -it faa-api /bin/bash
```

常用命令
```bash
# 升级到最新版本
alembic upgrade head

# 回退一版（可多次执行）
alembic downgrade -1

# 查看当前版本
alembic current

# 查看历史记录
alembic history

# 查看所有 head（分支场景）
alembic heads

# 生成迁移（手写变更）
alembic revision -m "describe changes"

# 自动检测模型差异生成迁移（需谨慎检查）
alembic revision --autogenerate -m "autogen changes"
```

在容器内一条命令执行（示例）
```bash
# 升级（容器名以实际为准）
docker compose exec faa-api bash -lc 'alembic upgrade head'

# 回退一版
docker compose exec faa-api bash -lc 'alembic downgrade -1'
```
