# FAA Threema 集成部署指南

## 前置准备

### 1. Threema Gateway 账号
- 在 [Threema Gateway](https://gateway.threema.ch) 注册账号
- 购买 Gateway ID（Basic 或 E2E 模式）
- **推荐使用 E2E 模式**（支持接收消息）

### 2. 服务器要求
- Linux 服务器（推荐部署在欧洲，如德国法兰克福）
- Docker 和 Docker Compose
- 公网 IP 和域名（用于 Webhook）
- SSL 证书（Threema 要求 HTTPS）

## 部署步骤

### 1. 克隆项目
```bash
git clone https://github.com/guanpeibj/family-ai-assistant.git
cd family-ai-assistant
```

### 2. 配置环境变量
```bash
cp env.example .env
vim .env
```

重要配置项：
```bash
# 数据库密码
DB_PASSWORD=your_strong_password

# OpenAI
OPENAI_API_KEY=sk-xxx

# Threema Gateway
THREEMA_GATEWAY_ID=*XXXXXXX  # 你的 Gateway ID
THREEMA_SECRET=your_secret    # Gateway Secret
THREEMA_PRIVATE_KEY=          # 留空自动生成，或填入已有私钥
THREEMA_WEBHOOK_URL=https://your-domain.com/webhook/threema

# 安全
SECRET_KEY=generate_a_long_random_string
```

### 3. 配置 Nginx（SSL 终端）
```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location /webhook/threema {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    # 可选：API 端点
    location /api/ {
        proxy_pass http://localhost:8000/;
        proxy_set_header Host $host;
    }
}
```

### 4. 启动服务
```bash
# 创建并运行数据库迁移
docker-compose up -d postgres
sleep 10  # 等待数据库启动

# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f
```

### 5. 配置 Threema Gateway Webhook

登录 Threema Gateway 管理面板：
1. 进入你的 Gateway ID 设置
2. 设置 Webhook URL：`https://your-domain.com/webhook/threema`
3. 保存设置

### 6. 测试

#### 6.1 测试 API 健康状态
```bash
curl https://your-domain.com/api/health
```

#### 6.2 发送测试消息
在 Threema 中添加你的 Gateway ID 为联系人，发送消息测试。

#### 6.3 运行测试脚本
```bash
cd examples
python test_threema.py
```

## 日常维护

### 查看日志
```bash
# 所有服务
docker-compose logs -f

# 仅 API 服务
docker-compose logs -f faa-api

# 仅 MCP 服务
docker-compose logs -f faa-mcp
```

### 备份数据库
```bash
# 备份
docker-compose exec postgres pg_dump -U faa family_assistant > backup_$(date +%Y%m%d).sql

# 恢复
docker-compose exec -T postgres psql -U faa family_assistant < backup_20240115.sql
```

### 更新服务
```bash
git pull
docker-compose build
docker-compose up -d
```

## 故障排查

### 1. Threema 消息收不到
- 检查 Webhook URL 是否正确配置
- 检查 SSL 证书是否有效
- 查看 API 日志是否有错误

### 2. 消息解密失败
- 检查 THREEMA_SECRET 是否正确
- 确认使用的是 E2E 模式
- 查看私钥是否正确生成/配置

### 3. MCP 连接失败
- 确保 MCP 服务正在运行
- 检查网络连接
- 查看 MCP 服务日志

## 安全建议

1. **使用强密码**：数据库和 SECRET_KEY
2. **限制访问**：使用防火墙限制数据库端口
3. **定期备份**：设置自动备份脚本
4. **监控日志**：定期检查异常活动
5. **及时更新**：关注项目更新和安全补丁

## 扩展功能

### 添加邮件支持
1. 配置邮件相关环境变量
2. 实现邮件适配器（参考 Threema 适配器）
3. 添加邮件 webhook 端点

### 添加微信支持
1. 申请微信公众号/企业微信
2. 配置微信相关环境变量
3. 实现微信适配器
4. 添加微信 webhook 端点

## 获取帮助

- 项目 Issue：https://github.com/guanpeibj/family-ai-assistant/issues
- Threema Gateway 文档：https://gateway.threema.ch/en/developer
- OpenAI API 文档：https://platform.openai.com/docs 