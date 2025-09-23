### Docker / Docker Compose 运维速查

适用对象：日常本地/服务器部署与排障。以下命令默认使用 Docker Compose v2（docker compose）。如你的环境是 v1，请将命令中的 `docker compose` 替换为 `docker-compose`。

---

## 环境准备
- 在项目根目录创建 `.env`（参考 `env.example`）。
- 主要变量：`POSTGRES_PASSWORD`、`OPENAI_API_KEY`、`SECRET_KEY`。

```bash
brew install colima
brew install docker docker-compose
colima start
colima stop
colima stop --force
colima delete
colima status



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

### FastEmbed 模型下载问题排障
```bash
# 查看 FastEmbed 模型下载相关日志
docker compose logs -f faa-api | grep -i "fastembed\|embedding\|model"

# 检查 FastEmbed 缓存目录
docker compose exec faa-api ls -la /data/fastembed_cache/

# 手动测试模型下载（在容器内）
docker compose exec faa-api python -c "
from fastembed import TextEmbedding
try:
    model = TextEmbedding(model_name='BAAI/bge-small-zh-v1.5')
    print('Model loaded successfully')
    result = list(model.embed(['测试文本']))
    print(f'Embedding generated, dimension: {len(result[0])}')
except Exception as e:
    print(f'Failed: {e}')
"

# 清理 FastEmbed 缓存（重新下载）
docker compose down
docker volume rm family-ai-assistant_fastembed_cache
docker compose up -d --build

# 检查网络连接（HuggingFace）
docker compose exec faa-api ping -c 3 huggingface.co
docker compose exec faa-api curl -I https://huggingface.co/api/models/BAAI/bge-small-zh-v1.5

# 切换到 OpenAI embedding（紧急回退）
# 在 .env 中设置：EMBED_PROVIDER=openai_compatible
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


## 部署与性能调优（建议）

以下建议帮助你将 FAA 在生产环境稳定运行，并在数据量增长时保持“快且准”。

- 环境变量（按需设置）
  - `DATABASE_URL`: PostgreSQL 连接，例如 `postgresql://faa:faa@db:5432/family_assistant`
  - `MCP_SERVER_URL`: MCP HTTP 包装器地址，例如 `http://faa-mcp:8000`
  - `MCP_STRICT_MODE`: 是否启用严格模式（`true/false`）。生产环境建议 `true`，禁用“模拟返回”，失败要显式暴露
  - `MCP_TOOLS_CACHE_TTL`: MCP 工具列表缓存秒数（默认 1200）
  - `EMB_CACHE_MAX_ITEMS`: 进程级 embedding 缓存最大条数（默认 1000）
  - `EMB_CACHE_TTL_SECONDS`: 进程级 embedding 缓存 TTL（默认 3600）
  - `MEDIA_ROOT`: 图表渲染输出目录（默认 `/data/media`）
  - OpenAI/LLM 相关：模型、Key、代理等（见 `src/core/config.py` 与部署环境）

- 数据库初始化与索引
  - 启用扩展：`pgvector`、`pg_trgm`、`uuid-ossp`、`pgcrypto`
  - 执行 `scripts/init_db.sql` 或依赖服务启动时的“幂等索引创建”（两者都安全可用）
  - 关键索引（建议必须有）：
    - `memories.embedding` 的向量索引（ivfflat/hnsw，cosine/l2 视版本而定）
    - `memories.content` 的 trigram GIN 索引（支持 `%`/similarity 排序）
    - `ai_understanding` 的 JSONB GIN（jsonb_path_ops），配合 `@>` 包含查询
    - 表达式索引：`(ai_understanding->>'thread_id'/'type'/'channel')`
    - 组合索引：`((ai_understanding->>'thread_id'), occurred_at DESC)`、`(user_id, occurred_at DESC)`
    - 可选：当 `ai_understanding.external_id` 存在时，对 `(user_id, external_id)` 建“部分唯一索引”实现软去重
  - 例：见 `scripts/init_db.sql`；服务启动时 `mcp-server/generic_mcp_server.py` 也会幂等确保

- 查询与性能建议
  - 始终在 `search/aggregate` 中带上 `filters.limit` 与合理的日期范围（`date_from/date_to`），避免宽扫
  - 语义检索优先向量；失败降级为 trigram/时间排序
  - 共享线程（`shared_thread=true`）必须附带 `thread_id`，并默认强制 `limit ≤ 30`
  - 聚合（`aggregate`）优先使用 `group_by=day|week|month` 或 `group_by_ai_field`，尽量减少多次往返
  - 定期执行 `VACUUM ANALYZE`，大表增长后考虑提高向量索引的 `lists` 或使用 HNSW（若 pgvector 版本支持）

- 缓存与时间预算
  - 工具清单缓存：`/tools` 结果在引擎侧做 10-20 分钟缓存，减少 prompt 注入的开销
  - Embedding 缓存：
    - trace 级缓存：一条消息内重复文本不重复向量化
    - 进程级 LRU 缓存：默认 1000 条、1 小时 TTL，可通过环境变量调节
  - 工具调用超时：按工具类型使用时间预算（store≈2s、search/aggregate≈3s、batch≈5s、render_chart≈6s），避免单次请求卡死

- 监控与可观测性
  - 结构化日志包含：工具名、耗时、是否向量/三元组、结果数量等
  - 建议开启 `pg_stat_statements` 以便识别慢 SQL 与缺索引路径
  - 关注指标：每次消息的 MCP 调用次数、耗时分布、embedding 缓存命中率、向量/Trigram 命中比

- 幂等与软更新（重要实践）
  - 定义：同一操作重复执行，其最终效果只有一次，或多次执行与执行一次效果等价
  - 在 FAA 中的做法：
    - 存储去重：对可识别的外部数据/重复导入，使用 `ai_understanding.external_id/source/version` 标记，先 `search(filters.jsonb_equals={external_id,type})` 检查是否已存在；存在则跳过或 `update_memory_fields` 浅合并，避免重复
    - 提醒设置：如依赖上一条 `store`，以 `$LAST_STORE_ID` 传递，LLM 侧不重复发起同一提醒；必要时也可在 `ai_understanding` 建 `reminder_key` 并在客户端侧做去重
    - 发送标记：`mark_reminder_sent` 为幂等操作（多次调用效果一致）
    - 软删除：通过 `soft_delete` 将 `ai_understanding.deleted=true`，重复调用无副作用
  - 设计建议：
    - 在 LLM 工具规划中约定：如可确定唯一性，`store.ai_data` 附带 `external_id/source/version`，并优先走“先查后存/更”
    - 数据模型保持开放，允许追加新字段；不要依赖严格 schema 来实现业务判断

- 故障与降级策略
  - 生产启用 `MCP_STRICT_MODE=true`，明确失败而非“模拟成功”
  - 搜索失败时：退化为 `filters` 与 trigram/时间排序；统计失败时：返回基于样本的定性描述并附上下一步建议
  - 回复层面：先说明已执行的操作（或失败/降级情况），再给要点和下一步

- 资源与扩展
  - 连接池：`asyncpg` 池大小按并发与数据库资源调整（当前 1-10）
  - 容量规划：图表渲染目录 `MEDIA_ROOT` 注意磁盘清理；定期归档/分区 `chat_turn` 类数据
  - 可横向扩展 MCP HTTP 层，将 embedding/渲染等重任务分离到异步后台
