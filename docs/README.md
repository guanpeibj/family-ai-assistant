# FAA 文档中心

Family AI Assistant 完整文档导航。

## 📚 快速导航

### 🚀 部署和运维

- **[Docker Compose 多环境配置](./DOCKER_COMPOSE_GUIDE.md)** ⭐ 推荐
  - docker-compose.override.yml 机制
  - 一键切换开发/生产环境
  - 无需手动修改配置文件
  - Makefile 便捷命令

- **[环境配置指南](./ENVIRONMENT_SETUP.md)** 🔧 必读
  - 开发 vs 生产环境对比
  - 启动方式详解
  - 环境切换指南
  - 最佳实践

- **[快速部署指南](./QUICK_START_DEPLOY.md)** ⭐ 推荐新手
  - 5 步完成生产部署
  - 最快 15 分钟上线
  
- **[完整部署文档](./DEPLOYMENT.md)**
  - 详细的部署步骤
  - 日志管理
  - 文件管理
  - 故障排查
  - 安全建议

- **[文件管理指南](./FILE_MANAGEMENT.md)** 📦 重要
  - Docker Volumes 策略
  - 备份和恢复
  - 磁盘空间监控
  - 清理和维护

- **[GitHub Actions 配置](./GITHUB_ACTIONS_SETUP.md)**
  - CI/CD 自动部署
  - SSH 密钥配置
  - Secrets 设置
  - 故障排查

### 📋 配置示例
- **[Crontab 示例](./crontab.example)**
  - 健康检查定时任务
  - 自动备份配置
  - 日志监控

## 📖 文档概览

### 1. 快速开始

如果你是**第一次部署** FAA：

```
1. 阅读 QUICK_START_DEPLOY.md（15分钟）
2. 在服务器上完成基础部署
3. 配置 GitHub Actions（GITHUB_ACTIONS_SETUP.md）
4. 推送代码，测试自动部署
```

### 2. 生产运维

如果你已经部署完成，需要**日常维护**：

```
常用命令：
- 查看日志：docker-compose logs -f faa-api
- 重启服务：docker-compose restart
- 查看状态：docker-compose ps
- 健康检查：curl http://localhost:8001/health
- 手动部署：/opt/faa/scripts/deploy.sh
- 回滚版本：/opt/faa/scripts/rollback.sh
```

详细内容参考：[DEPLOYMENT.md](./DEPLOYMENT.md)

### 3. CI/CD 配置

如果你想要**自动化部署**：

1. 生成 SSH 密钥对
2. 配置 GitHub Secrets
3. 推送代码自动部署
4. 或手动触发部署

详细内容参考：[GITHUB_ACTIONS_SETUP.md](./GITHUB_ACTIONS_SETUP.md)

## 🛠️ 核心功能

### 日志管理
- **Docker 原生轮转**：单文件 50MB，保留 10 个
- **JSON 格式**：便于分析和搜索
- **查看命令**：`docker-compose logs -f`

### 自动部署
- **Push 触发**：推送到 main/master 自动部署
- **手动触发**：GitHub Actions 界面点击部署
- **自动回滚**：健康检查失败自动回退

### 健康监控
- **定时检查**：每 5 分钟自动检查
- **自动重启**：检测到异常自动重启服务
- **告警通知**：可选 Threema 通知

### 备份恢复
- **自动备份**：每次部署前自动备份
- **数据库备份**：每日自动备份数据库
- **快速回滚**：一键回滚到历史版本

## 📊 系统架构

```
┌─────────────┐
│   GitHub    │ Push 触发
└──────┬──────┘
       │
       ↓
┌─────────────────┐
│ GitHub Actions  │ 自动部署
└──────┬──────────┘
       │
       ↓ SSH
┌─────────────────────────────────────┐
│  生产服务器 (/opt/faa)              │
│  ┌───────────────────────────────┐  │
│  │ Docker Compose                │  │
│  │  ├─ postgres    (数据库)      │  │
│  │  ├─ faa-api     (API 服务)    │  │
│  │  └─ faa-mcp     (MCP 工具)    │  │
│  └───────────────────────────────┘  │
│  ┌───────────────────────────────┐  │
│  │ 日志 (Docker 自动轮转)        │  │
│  │  - 50MB/文件，保留 10 个      │  │
│  │  - JSON 格式                  │  │
│  └───────────────────────────────┘  │
│  ┌───────────────────────────────┐  │
│  │ 脚本 (/opt/faa/scripts)       │  │
│  │  ├─ deploy.sh    (部署)       │  │
│  │  ├─ rollback.sh  (回滚)       │  │
│  │  ├─ health_check.sh           │  │
│  │  └─ log_monitor.sh            │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

## 🔧 维护脚本

### 部署脚本 (`/opt/faa/scripts/deploy.sh`)
- 自动备份当前版本
- 拉取最新代码
- 构建 Docker 镜像
- 重启服务
- 健康检查
- 失败自动回滚

### 健康检查 (`/opt/faa/scripts/health_check.sh`)
- 定期检查服务健康
- 失败自动重启
- 可选 Threema 告警

### 回滚脚本 (`/opt/faa/scripts/rollback.sh`)
- 列出历史版本
- 交互式选择回滚点
- 自动回退代码和服务
- 可选数据库恢复

### 日志监控 (`/opt/faa/scripts/log_monitor.sh`)
- 监控错误日志
- 超过阈值发送告警
- 记录监控历史

## 📖 相关文档

### 项目文档
- [主 README](../readme.MD) - 项目概述
- [架构设计](../docs/) - 系统架构

### 配置文件
- [.env.example](../.env.example) - 环境变量示例
- [docker-compose.yml](../docker-compose.yml) - Docker 配置

### GitHub Actions
- [deploy.yml](../.github/workflows/deploy.yml) - 部署工作流

## ❓ 常见问题

### Q: 如何查看日志？
```bash
docker-compose logs -f faa-api
```

### Q: 如何重启服务？
```bash
docker-compose restart
```

### Q: 如何回滚版本？
```bash
/opt/faa/scripts/rollback.sh
```

### Q: 如何手动触发部署？
在 GitHub Actions 界面点击 "Run workflow"

### Q: 如何配置自动通知？
在 GitHub Secrets 中配置 `THREEMA_*` 相关变量

### Q: 健康检查失败怎么办？
```bash
# 1. 查看日志
docker-compose logs --tail=100 faa-api

# 2. 检查服务状态
docker-compose ps

# 3. 重启服务
docker-compose restart

# 4. 如果问题持续，回滚
/opt/faa/scripts/rollback.sh
```

## 🔒 安全提示

1. ✅ 不要将 `.env` 文件提交到 Git
2. ✅ 定期更新 SSH 密钥
3. ✅ 使用强密码保护数据库
4. ✅ 配置防火墙限制访问
5. ✅ 定期备份重要数据
6. ✅ 监控服务器资源使用

## 🆘 获取帮助

遇到问题？

1. 查看 [故障排查](./DEPLOYMENT.md#故障排查) 章节
2. 检查 [GitHub Actions 日志](https://github.com/YOUR_REPO/actions)
3. 查看服务器日志：`docker-compose logs`
4. 提交 GitHub Issue

## 📝 贡献文档

欢迎改进文档！

1. Fork 项目
2. 修改文档
3. 提交 Pull Request

---

**最后更新**: 2025-01-24  
**维护者**: FAA 团队

