#!/bin/bash
# FAA 生产部署脚本
# 功能：自动拉取代码、备份、构建、部署、健康检查

set -e  # 遇到错误立即退出

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 配置
FAA_DIR="/opt/faa/family-ai-assistant"
BACKUP_DIR="/opt/faa/backups"
HEALTH_URL="http://localhost:8001/health"
MAX_WAIT_TIME=60

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   FAA 生产部署开始${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 1. 检查当前目录
if [ ! -d "$FAA_DIR" ]; then
    echo -e "${RED}错误: FAA 目录不存在: $FAA_DIR${NC}"
    exit 1
fi

cd "$FAA_DIR"

# 2. 备份当前版本
echo -e "${YELLOW}📦 备份当前版本...${NC}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="$BACKUP_DIR/$TIMESTAMP"
mkdir -p "$BACKUP_PATH"

# 记录当前提交
CURRENT_COMMIT=$(git rev-parse HEAD)
echo "$CURRENT_COMMIT" > "$BACKUP_PATH/commit.txt"
echo "当前提交: $CURRENT_COMMIT" >> "$BACKUP_PATH/deploy.log"
echo "备份时间: $(date)" >> "$BACKUP_PATH/deploy.log"

# 备份容器状态
docker-compose ps > "$BACKUP_PATH/services.txt" 2>&1 || true

# 备份数据库（可选，根据需要启用）
# echo -e "${YELLOW}💾 备份数据库...${NC}"
# docker-compose exec -T postgres pg_dump -U faa family_assistant > "$BACKUP_PATH/database.sql" || true

echo -e "${GREEN}✓ 备份完成: $BACKUP_PATH${NC}"

# 3. 拉取最新代码
echo -e "${YELLOW}📥 拉取最新代码...${NC}"
git fetch origin
NEW_COMMIT=$(git rev-parse origin/master 2>/dev/null || git rev-parse origin/main)

if [ "$CURRENT_COMMIT" = "$NEW_COMMIT" ]; then
    echo -e "${GREEN}✓ 代码已是最新，无需更新${NC}"
else
    echo "更新: $CURRENT_COMMIT -> $NEW_COMMIT"
    git pull
fi

# 4. 构建镜像
echo -e "${YELLOW}🔨 构建 Docker 镜像...${NC}"
docker-compose build --no-cache

# 5. 停止旧服务
echo -e "${YELLOW}⏸️  停止旧服务...${NC}"
docker-compose down

# 6. 启动新服务
echo -e "${YELLOW}🚀 启动新服务...${NC}"
docker-compose up -d

# 7. 等待服务启动
echo -e "${YELLOW}⏳ 等待服务启动...${NC}"
WAIT_TIME=0
while [ $WAIT_TIME -lt $MAX_WAIT_TIME ]; do
    sleep 3
    WAIT_TIME=$((WAIT_TIME + 3))
    
    if curl -f -s "$HEALTH_URL" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ 服务已启动 (${WAIT_TIME}秒)${NC}"
        break
    fi
    
    echo "等待中... (${WAIT_TIME}/${MAX_WAIT_TIME}秒)"
done

# 8. 健康检查
echo -e "${YELLOW}🏥 执行健康检查...${NC}"
HEALTH_RESPONSE=$(curl -f -s "$HEALTH_URL" || echo "")

if [ -z "$HEALTH_RESPONSE" ]; then
    echo -e "${RED}❌ 健康检查失败！${NC}"
    echo -e "${YELLOW}🔄 尝试回滚...${NC}"
    
    # 回滚到上一个版本
    git reset --hard "$CURRENT_COMMIT"
    docker-compose down
    docker-compose up -d
    
    echo -e "${RED}已回滚到之前的版本${NC}"
    exit 1
fi

echo -e "${GREEN}✓ 健康检查通过${NC}"
echo "响应: $HEALTH_RESPONSE"

# 9. 清理旧镜像
echo -e "${YELLOW}🧹 清理旧镜像...${NC}"
docker image prune -f

# 10. 显示服务状态
echo ""
echo -e "${GREEN}📊 当前服务状态:${NC}"
docker-compose ps

# 11. 清理旧备份（保留最近 30 个）
echo -e "${YELLOW}🧹 清理旧备份...${NC}"
cd "$BACKUP_DIR"
ls -t | tail -n +31 | xargs -r rm -rf
echo -e "${GREEN}✓ 保留最近 30 个备份${NC}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   ✅ 部署成功完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "提交: $NEW_COMMIT"
echo -e "备份: $BACKUP_PATH"
echo -e "时间: $(date)"
echo ""

exit 0
