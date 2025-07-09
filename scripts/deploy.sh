#!/bin/bash
# 简单的部署脚本

set -e  # 遇到错误立即退出

echo "🚀 开始部署 Family AI Assistant..."

# 配置
REMOTE_HOST=${DEPLOY_HOST:-"your-server.com"}
REMOTE_USER=${DEPLOY_USER:-"ubuntu"}
REMOTE_DIR="~/family-ai-assistant"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 帮助信息
if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
    echo "用法: ./scripts/deploy.sh [选项]"
    echo ""
    echo "选项:"
    echo "  setup    - 首次设置服务器环境"
    echo "  deploy   - 部署应用（默认）"
    echo "  logs     - 查看远程日志"
    echo "  status   - 检查服务状态"
    echo ""
    echo "环境变量:"
    echo "  DEPLOY_HOST - 部署服务器地址"
    echo "  DEPLOY_USER - SSH用户名"
    exit 0
fi

# 首次设置
if [ "$1" == "setup" ]; then
    echo -e "${YELLOW}首次设置服务器环境...${NC}"
    ssh $REMOTE_USER@$REMOTE_HOST << 'EOF'
        # 安装 Docker
        if ! command -v docker &> /dev/null; then
            echo "安装 Docker..."
            curl -fsSL https://get.docker.com | sh
            sudo usermod -aG docker $USER
        fi
        
        # 安装 Docker Compose
        if ! command -v docker-compose &> /dev/null; then
            echo "安装 Docker Compose..."
            sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
            sudo chmod +x /usr/local/bin/docker-compose
        fi
        
        # 克隆仓库
        if [ ! -d "family-ai-assistant" ]; then
            git clone https://github.com/guanpeibj/family-ai-assistant.git
        fi
        
        echo "✅ 服务器环境设置完成！"
EOF
    exit 0
fi

# 查看日志
if [ "$1" == "logs" ]; then
    echo -e "${YELLOW}查看远程日志...${NC}"
    ssh $REMOTE_USER@$REMOTE_HOST "cd $REMOTE_DIR && docker-compose logs -f --tail=100"
    exit 0
fi

# 检查状态
if [ "$1" == "status" ]; then
    echo -e "${YELLOW}检查服务状态...${NC}"
    ssh $REMOTE_USER@$REMOTE_HOST "cd $REMOTE_DIR && docker-compose ps"
    exit 0
fi

# 默认：部署应用
echo -e "${GREEN}1. 推送代码到 GitHub...${NC}"
git add .
git commit -m "Deploy: $(date '+%Y-%m-%d %H:%M:%S')" || true
git push origin main

echo -e "${GREEN}2. 在服务器上更新代码...${NC}"
ssh $REMOTE_USER@$REMOTE_HOST << EOF
    cd $REMOTE_DIR
    git pull origin main
    
    # 检查 .env 文件
    if [ ! -f .env ]; then
        echo -e "${RED}错误: .env 文件不存在！${NC}"
        echo "请先在服务器上创建 .env 文件"
        exit 1
    fi
EOF

echo -e "${GREEN}3. 构建并重启服务...${NC}"
ssh $REMOTE_USER@$REMOTE_HOST << EOF
    cd $REMOTE_DIR
    
    # 构建镜像
    docker-compose build
    
    # 停止旧服务
    docker-compose down
    
    # 启动新服务
    docker-compose up -d
    
    # 清理旧镜像
    docker image prune -f
    
    # 显示运行状态
    docker-compose ps
EOF

echo -e "${GREEN}✅ 部署完成！${NC}"
echo ""
echo "查看日志: ./scripts/deploy.sh logs"
echo "检查状态: ./scripts/deploy.sh status" 