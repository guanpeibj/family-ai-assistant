# FAA 部署检查清单

## 🚀 快速部署步骤

### 1. 服务器准备 ✓
- [ ] Ubuntu 20.04+ (最低 2GB 内存)
- [ ] Docker 和 Docker Compose 已安装
- [ ] Git 已安装

### 2. 项目部署 ✓
- [ ] 克隆项目到 `/opt/family-ai-assistant`
- [ ] 复制 `env.example` 为 `.env`
- [ ] 配置必需的环境变量：
  - [ ] `OPENAI_API_KEY`
  - [ ] `POSTGRES_PASSWORD`
  - [ ] `SECRET_KEY`

### 3. 启动服务 ✓
- [ ] 运行 `docker-compose up -d`
- [ ] 所有容器状态为 "Up"
- [ ] 健康检查通过: `curl http://localhost:8000/health`

### 4. 域名配置（可选）✓
- [ ] 域名 A 记录指向服务器 IP
- [ ] HTTPS 证书配置（Cloudflare 或 Let's Encrypt）
- [ ] Nginx 反向代理配置

### 5. Threema 配置（可选）✓
- [ ] 配置 Webhook URL
- [ ] 测试消息接收

## 🔍 验证部署

```bash
# 检查服务状态
./scripts/deploy.sh status

# 查看日志
./scripts/deploy.sh logs

# 健康检查
curl http://localhost:8000/health
```

## 🚨 常见问题

### 端口被占用
```bash
# 查找占用端口的进程
sudo lsof -i :8000
# 修改 docker-compose.yml 中的端口映射
```

### 数据库连接失败
```bash
# 检查数据库容器
docker-compose ps postgres
# 查看数据库日志
docker-compose logs postgres
```

### OpenAI API 错误
- 检查 API Key 是否正确
- 确认账户余额充足
- 查看 API 日志: `docker-compose logs faa-api | grep -i openai`

## 📞 需要帮助？

- 查看详细部署文档: [DEPLOY.md](DEPLOY.md)
- 提交 Issue: https://github.com/yourusername/family-ai-assistant/issues 