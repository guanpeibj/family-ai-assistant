#!/bin/bash
# FAA 服务器初始化脚本
# 用途：在Ubuntu服务器上创建部署用户并设置环境

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🚀 FAA 服务器初始化脚本${NC}"
echo "======================================"
echo ""

# 检查是否为root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ 请以root用户运行此脚本${NC}"
    echo "使用: sudo bash server-init.sh"
    exit 1
fi

# 获取用户输入
echo -e "${YELLOW}📝 请提供以下信息：${NC}"
read -p "新建用户名 [默认: faa]: " USERNAME
USERNAME=${USERNAME:-faa}

read -p "是否需要设置密码？(y/n) [默认: n]: " SET_PASSWORD
SET_PASSWORD=${SET_PASSWORD:-n}

echo ""
echo -e "${YELLOW}🔧 开始初始化...${NC}"

# 1. 创建用户
if id "$USERNAME" &>/dev/null; then
    echo "✓ 用户 $USERNAME 已存在"
else
    echo "创建用户 $USERNAME..."
    if [ "$SET_PASSWORD" = "y" ]; then
        adduser $USERNAME
    else
        adduser --disabled-password --gecos "" $USERNAME
    fi
    echo "✓ 用户创建成功"
fi

# 2. 添加到必要的组
echo "设置用户权限..."
usermod -aG sudo $USERNAME
usermod -aG docker $USERNAME 2>/dev/null || echo "Docker组不存在，稍后安装Docker时会自动创建"

# 3. 创建应用目录
echo "创建应用目录..."
mkdir -p /opt/family-ai-assistant
chown $USERNAME:$USERNAME /opt/family-ai-assistant
echo "✓ 目录创建成功"

# 4. 设置SSH目录
echo "设置SSH目录..."
USER_HOME=$(getent passwd $USERNAME | cut -d: -f6)
mkdir -p $USER_HOME/.ssh
touch $USER_HOME/.ssh/authorized_keys
chown -R $USERNAME:$USERNAME $USER_HOME/.ssh
chmod 700 $USER_HOME/.ssh
chmod 600 $USER_HOME/.ssh/authorized_keys
echo "✓ SSH目录设置成功"

# 5. 安装Docker（如果未安装）
if ! command -v docker &> /dev/null; then
    echo ""
    echo -e "${YELLOW}📦 安装Docker...${NC}"
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker $USERNAME
    echo "✓ Docker安装成功"
else
    echo "✓ Docker已安装"
fi

# 6. 安装Docker Compose（如果未安装）
if ! command -v docker-compose &> /dev/null; then
    echo "安装Docker Compose..."
    apt-get update
    apt-get install -y docker-compose
    echo "✓ Docker Compose安装成功"
else
    echo "✓ Docker Compose已安装"
fi

# 7. 配置防火墙（如果启用）
if systemctl is-active --quiet ufw; then
    echo "配置防火墙..."
    ufw allow 22/tcp    # SSH
    ufw allow 8000/tcp  # FAA API
    ufw allow 443/tcp   # HTTPS（未来使用）
    ufw allow 80/tcp    # HTTP（未来使用）
    echo "✓ 防火墙配置成功"
fi

echo ""
echo -e "${GREEN}✅ 服务器初始化完成！${NC}"
echo "======================================"
echo ""
echo -e "${YELLOW}📋 下一步操作：${NC}"
echo ""
echo "1. 添加SSH公钥到服务器："
echo "   echo '你的公钥内容' >> $USER_HOME/.ssh/authorized_keys"
echo ""
echo "2. 测试SSH连接："
echo "   ssh -i ~/.ssh/faa_deploy $USERNAME@$(curl -s ifconfig.me)"
echo ""
echo "3. GitHub Secrets中设置："
echo "   SERVER_USER=$USERNAME"
echo "   SERVER_HOST=$(curl -s ifconfig.me)"
echo ""
echo -e "${GREEN}🎉 准备就绪！${NC}" 