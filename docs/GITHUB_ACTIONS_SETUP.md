# GitHub Actions CI/CD 配置指南

本文档详细说明如何配置 GitHub Actions 实现 FAA 的自动部署。

## 前提条件

1. ✅ 服务器已部署 FAA（参考 [QUICK_START_DEPLOY.md](./QUICK_START_DEPLOY.md)）
2. ✅ 代码已推送到 GitHub
3. ✅ 拥有服务器 SSH 访问权限

---

## 步骤 1: 生成 SSH 密钥对

### 在本地电脑执行：

```bash
# 生成专用于部署的 SSH 密钥
ssh-keygen -t ed25519 -f ~/.ssh/faa_deploy -C "github-actions-faa"

# 会生成两个文件：
# - ~/.ssh/faa_deploy        (私钥，用于 GitHub Secret)
# - ~/.ssh/faa_deploy.pub    (公钥，添加到服务器)
```

**不要设置密码**（否则自动部署无法工作）

---

## 步骤 2: 配置服务器

### 2.1 添加公钥到服务器

```bash
# 方法 1: 使用 ssh-copy-id（推荐）
ssh-copy-id -i ~/.ssh/faa_deploy.pub user@your-server-ip

# 方法 2: 手动添加
cat ~/.ssh/faa_deploy.pub
# 复制输出，然后在服务器上：
# echo "公钥内容" >> ~/.ssh/authorized_keys
```

### 2.2 测试 SSH 连接

```bash
# 使用新密钥测试连接
ssh -i ~/.ssh/faa_deploy user@your-server-ip "echo 'SSH 连接成功'"

# 应该看到输出：SSH 连接成功
```

### 2.3 确保部署脚本就位

在服务器上执行：

```bash
# 检查脚本是否存在
ls -lh /opt/faa/scripts/

# 应该看到：
# deploy.sh
# health_check.sh
# rollback.sh
# log_monitor.sh

# 确保有执行权限
sudo chmod +x /opt/faa/scripts/*.sh

# 测试部署脚本
/opt/faa/scripts/deploy.sh
```

---

## 步骤 3: 配置 GitHub Secrets

### 3.1 访问 GitHub Secrets 设置

1. 打开 GitHub 仓库
2. 点击 **Settings** (设置)
3. 左侧菜单找到 **Secrets and variables** → **Actions**
4. 点击 **New repository secret**

### 3.2 添加必需的 Secrets

| Secret 名称 | 如何获取 | 示例 |
|-------------|---------|------|
| `SSH_HOST` | 服务器 IP 地址 | `123.45.67.89` |
| `SSH_USER` | SSH 用户名 | `ubuntu` 或 `root` |
| `SSH_KEY` | 私钥内容（见下方） | `-----BEGIN OPENSSH PRIVATE KEY-----` |
| `SSH_PORT` | SSH 端口（可选） | `22`（默认） |
| `POSTGRES_PASSWORD` | 数据库密码 | 与服务器 `.env` 一致 |

#### 获取私钥内容：

```bash
# 在本地执行
cat ~/.ssh/faa_deploy

# 复制**全部**输出，包括：
# -----BEGIN OPENSSH PRIVATE KEY-----
# ... 中间的所有内容 ...
# -----END OPENSSH PRIVATE KEY-----
```

**重要**：必须包含开头和结尾的标记行，且不能有多余的空行。

### 3.3 添加可选的 Secrets（用于通知）

如果想要部署成功/失败时收到 Threema 通知：

| Secret 名称 | 说明 | 示例 |
|-------------|------|------|
| `THREEMA_BOT_ID` | Bot ID | `*ABCDEFG` |
| `THREEMA_ADMIN_ID` | 接收通知的 ID | `YOUR_ID` |
| `THREEMA_SECRET` | Threema Gateway Secret | `your_secret` |

---

## 步骤 4: 验证 GitHub Actions Workflow

### 4.1 检查 Workflow 文件

确保文件存在：`.github/workflows/deploy.yml`

```bash
# 在本地检查
cat .github/workflows/deploy.yml

# 应该看到 workflow 配置
```

### 4.2 推送代码触发测试

```bash
# 在本地做一个小改动
echo "# CI/CD 测试" >> README.md
git add .
git commit -m "测试 CI/CD 部署"
git push origin main  # 或 master

# 推送后立即查看 GitHub Actions
# https://github.com/YOUR_USERNAME/family-ai-assistant/actions
```

### 4.3 查看部署日志

1. 访问 **Actions** 标签页
2. 点击最新的 workflow 运行
3. 查看 **deploy** job 的日志
4. 应该看到：
   ```
   🚀 开始部署 FAA...
   📦 备份当前版本...
   📥 拉取最新代码...
   🔨 构建 Docker 镜像...
   🚀 启动新服务...
   ✅ 部署成功完成！
   ```

---

## 步骤 5: 手动触发部署

### 5.1 使用 GitHub 界面

1. 访问 **Actions** 标签页
2. 左侧选择 **Deploy FAA to Production**
3. 点击 **Run workflow** 按钮
4. 选择分支（通常是 main）
5. 选择是否跳过测试：
   - `false` - 运行测试后部署（推荐）
   - `true` - 直接部署（快速）
6. 点击绿色的 **Run workflow** 按钮

### 5.2 使用 GitHub CLI（可选）

```bash
# 安装 GitHub CLI
brew install gh  # macOS
# 或访问: https://cli.github.com/

# 登录
gh auth login

# 触发部署
gh workflow run deploy.yml

# 查看运行状态
gh run list --workflow=deploy.yml
gh run watch
```

---

## 故障排查

### 问题 1: SSH 连接失败

**错误信息**：
```
Permission denied (publickey)
```

**解决方案**：
1. 检查 `SSH_HOST`、`SSH_USER` 是否正确
2. 确认私钥完整（包括 `BEGIN` 和 `END` 行）
3. 在服务器上检查：
   ```bash
   cat ~/.ssh/authorized_keys | grep faa_deploy
   ```

### 问题 2: 部署脚本不存在

**错误信息**：
```
/opt/faa/scripts/deploy.sh: No such file or directory
```

**解决方案**：
```bash
# 在服务器上执行
cd /opt/faa/family-ai-assistant
sudo cp scripts/*.sh /opt/faa/scripts/
sudo chmod +x /opt/faa/scripts/*.sh
```

### 问题 3: 权限不足

**错误信息**：
```
docker: permission denied
```

**解决方案**：
```bash
# 在服务器上执行
sudo usermod -aG docker $USER
# 退出并重新登录
```

### 问题 4: 健康检查失败

**解决方案**：
```bash
# 在服务器上查看日志
docker-compose logs --tail=100 faa-api

# 检查服务状态
docker-compose ps

# 手动重启
docker-compose restart
```

### 问题 5: 部署通知未收到

检查：
1. `THREEMA_BOT_ID` 是否以 `*` 开头
2. `THREEMA_ADMIN_ID` 是否正确
3. `THREEMA_SECRET` 是否有效

手动测试：
```bash
curl -X POST "https://msgapi.threema.ch/send_simple" \
  -d "from=*YOUR_BOT_ID" \
  -d "to=YOUR_ID" \
  -d "secret=YOUR_SECRET" \
  -d "text=测试通知"
```

---

## 高级配置

### 环境分离（可选）

如果想要分离 staging 和 production 环境：

1. 在 GitHub 创建 Environment：
   - Settings → Environments → New environment
   - 名称：`production`
   - 添加保护规则（需要审批、延迟等）

2. 修改 `deploy.yml`：
   ```yaml
   deploy:
     environment: production  # 添加此行
   ```

### 部署通知到其他平台

修改 `.github/workflows/deploy.yml` 中的通知步骤：

#### Slack:
```yaml
- name: Slack 通知
  uses: 8398a7/action-slack@v3
  with:
    status: ${{ job.status }}
    webhook_url: ${{ secrets.SLACK_WEBHOOK }}
```

#### 企业微信:
```yaml
- name: 企业微信通知
  run: |
    curl -X POST "${{ secrets.WECOM_WEBHOOK }}" \
      -H "Content-Type: application/json" \
      -d '{"msgtype":"text","text":{"content":"FAA 部署成功"}}'
```

---

## 安全建议

1. **最小权限原则**：
   - 使用专用的部署用户，不要用 root
   - 限制 SSH 密钥只能执行部署脚本

2. **密钥管理**：
   - 定期轮换 SSH 密钥
   - 不要在 workflow 中打印敏感信息
   - 使用 GitHub Secrets，不要硬编码

3. **审批流程**：
   - 生产环境配置 Environment 保护规则
   - 要求手动审批后才能部署

4. **回滚准备**：
   - 每次部署前自动备份
   - 保留足够的历史版本
   - 熟悉回滚流程

---

## 常见命令

```bash
# 查看 workflow 历史
gh run list --workflow=deploy.yml

# 查看特定运行的日志
gh run view <run-id> --log

# 取消正在运行的 workflow
gh run cancel <run-id>

# 重新运行失败的 workflow
gh run rerun <run-id>
```

---

## 测试清单

部署前确保：

- [ ] SSH 密钥配置正确
- [ ] 所有 GitHub Secrets 已添加
- [ ] 服务器部署脚本就位并可执行
- [ ] 手动部署测试成功
- [ ] GitHub Actions workflow 文件存在
- [ ] 推送代码能触发自动部署
- [ ] 手动触发部署正常工作
- [ ] 部署通知能正常接收（如配置）
- [ ] 回滚流程测试通过

---

**完成！** 现在你的 FAA 项目拥有完整的 CI/CD 流程，推送代码即可自动部署到生产环境。

📖 更多信息请参考：
- [完整部署文档](./DEPLOYMENT.md)
- [快速开始指南](./QUICK_START_DEPLOY.md)

