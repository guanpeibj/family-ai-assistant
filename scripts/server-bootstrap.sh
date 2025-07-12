#!/bin/bash
# 极简服务器启动脚本 - 适配console限制
echo "🚀 FAA初始化..."
apt update && apt install -y docker.io docker-compose git curl jq
useradd -m -s /bin/bash faa 2>/dev/null || true
usermod -aG docker faa
mkdir -p /opt/family-ai-assistant
chown faa:faa /opt/family-ai-assistant

# 下载完整脚本
cd /opt/family-ai-assistant
curl -fsSL https://raw.githubusercontent.com/guanpeibj/family-ai-assistant/master/scripts/auto-deploy.sh -o auto-deploy.sh
chmod +x auto-deploy.sh
chown faa:faa auto-deploy.sh

# 设置定时任务
echo "* * * * * faa /opt/family-ai-assistant/auto-deploy.sh >> /var/log/faa.log 2>&1" > /etc/cron.d/faa

echo "✅ 初始化完成！"
echo "查看日志: tail -f /var/log/faa.log"
