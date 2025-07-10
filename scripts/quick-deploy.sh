#!/bin/bash
# FAA 快速部署脚本
# 使用: curl -fsSL https://raw.githubusercontent.com/yourusername/family-ai-assistant/main/scripts/quick-deploy.sh | bash

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🚀 FAA 快速部署脚本${NC}"
echo "=========================="
echo ""

# 检查是否为 root 或有 sudo 权限
if [ "$EUID" -ne 0 ] && ! sudo -n true 2>/dev/null; then 
    echo -e "${RED}❌ 请使用 root 用户运行或确保有 sudo 权限${NC}"
    exit 1
fi

# 1. 安装依赖
echo -e "${YELLOW}📦 步骤 1/5: 安装系统依赖...${NC}"
apt update && apt upgrade -y
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose git

# 2. 克隆项目
echo -e "${YELLOW}📥 步骤 2/5: 下载项目代码...${NC}"
cd /opt
if [ -d "family-ai-assistant" ]; then
    cd family-ai-assistant
    git pull
else
    git clone https://github.com/yourusername/family-ai-assistant.git
    cd family-ai-assistant
fi

# 3. 配置环境变量
echo -e "${YELLOW}⚙️  步骤 3/5: 配置环境变量...${NC}"
if [ ! -f .env ]; then
    cp env.example .env
    
    echo ""
    echo -e "${YELLOW}请配置必要的环境变量:${NC}"
    echo "1. OpenAI API Key (必需)"
    read -p "请输入 OPENAI_API_KEY: " OPENAI_KEY
    sed -i "s/OPENAI_API_KEY=.*/OPENAI_API_KEY=$OPENAI_KEY/" .env
    
    echo ""
    echo "2. 数据库密码 (建议修改)"
    read -p "请输入数据库密码 [默认: 随机生成]: " DB_PASS
    if [ -z "$DB_PASS" ]; then
        DB_PASS=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
        echo "生成的密码: $DB_PASS"
    fi
    sed -i "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$DB_PASS/" .env
    
    echo ""
    echo "3. Threema 配置 (可选，按 Enter 跳过)"
    read -p "请输入 THREEMA_GATEWAY_ID: " THREEMA_ID
    if [ ! -z "$THREEMA_ID" ]; then
        sed -i "s/THREEMA_GATEWAY_ID=.*/THREEMA_GATEWAY_ID=$THREEMA_ID/" .env
        read -p "请输入 THREEMA_API_SECRET: " THREEMA_SECRET
        sed -i "s/THREEMA_API_SECRET=.*/THREEMA_API_SECRET=$THREEMA_SECRET/" .env
    fi
fi

# 4. 启动服务
echo -e "${YELLOW}🐳 步骤 4/5: 启动 Docker 服务...${NC}"
docker-compose up -d

# 等待服务启动
echo "等待服务启动..."
sleep 15

# 5. 初始化数据
echo -e "${YELLOW}📊 步骤 5/5: 初始化数据...${NC}"
docker-compose exec -T faa-api python scripts/init_family_data.py

# 完成
echo ""
echo -e "${GREEN}✅ 部署完成！${NC}"
echo "=================="
echo ""
echo "📍 服务地址:"
echo "   - API: http://$(curl -s ifconfig.me):8000"
echo "   - 健康检查: http://$(curl -s ifconfig.me):8000/health"
echo ""
echo "🔧 常用命令:"
echo "   - 查看日志: cd /opt/family-ai-assistant && docker-compose logs -f"
echo "   - 查看状态: cd /opt/family-ai-assistant && docker-compose ps"
echo "   - 重启服务: cd /opt/family-ai-assistant && docker-compose restart"
echo ""
echo "📚 详细文档: https://github.com/yourusername/family-ai-assistant/blob/main/DEPLOY.md"
echo ""
echo -e "${YELLOW}⚠️  下一步建议:${NC}"
echo "1. 配置域名和 HTTPS (参考 DEPLOY.md)"
echo "2. 配置防火墙规则"
echo "3. 设置定期备份"
echo "" 