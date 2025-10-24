#!/bin/bash
# FAA 回滚脚本
# 用于快速回滚到上一个版本

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 配置
FAA_DIR="/opt/faa/family-ai-assistant"
BACKUP_DIR="/opt/faa/backups"
HEALTH_URL="http://localhost:8001/health"

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}   FAA 回滚操作${NC}"
echo -e "${YELLOW}========================================${NC}"
echo ""

# 检查备份目录
if [ ! -d "$BACKUP_DIR" ]; then
    echo -e "${RED}错误: 备份目录不存在: $BACKUP_DIR${NC}"
    exit 1
fi

# 列出可用的备份
echo -e "${GREEN}可用的备份版本:${NC}"
echo ""
BACKUPS=($(ls -t "$BACKUP_DIR"))
for i in "${!BACKUPS[@]}"; do
    BACKUP_PATH="$BACKUP_DIR/${BACKUPS[$i]}"
    if [ -f "$BACKUP_PATH/commit.txt" ]; then
        COMMIT=$(cat "$BACKUP_PATH/commit.txt")
        echo "$((i+1)). ${BACKUPS[$i]} - 提交: ${COMMIT:0:7}"
    else
        echo "$((i+1)). ${BACKUPS[$i]}"
    fi
done

echo ""
echo -e "${YELLOW}选择要回滚的版本（输入序号，默认 1 = 最近的备份）:${NC}"
read -r CHOICE

# 默认选择最近的备份
if [ -z "$CHOICE" ]; then
    CHOICE=1
fi

# 验证输入
if ! [[ "$CHOICE" =~ ^[0-9]+$ ]] || [ "$CHOICE" -lt 1 ] || [ "$CHOICE" -gt "${#BACKUPS[@]}" ]; then
    echo -e "${RED}无效的选择${NC}"
    exit 1
fi

# 获取选择的备份
SELECTED_BACKUP="${BACKUPS[$((CHOICE-1))]}"
BACKUP_PATH="$BACKUP_DIR/$SELECTED_BACKUP"

echo ""
echo -e "${YELLOW}即将回滚到: $SELECTED_BACKUP${NC}"

if [ -f "$BACKUP_PATH/commit.txt" ]; then
    TARGET_COMMIT=$(cat "$BACKUP_PATH/commit.txt")
    echo -e "${YELLOW}目标提交: $TARGET_COMMIT${NC}"
fi

echo ""
echo -e "${RED}警告: 这将停止当前服务并回滚代码${NC}"
echo -e "${YELLOW}是否继续? (y/N):${NC}"
read -r CONFIRM

if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo -e "${YELLOW}取消回滚${NC}"
    exit 0
fi

# 执行回滚
cd "$FAA_DIR"

echo ""
echo -e "${YELLOW}1. 停止当前服务...${NC}"
docker-compose down

echo -e "${YELLOW}2. 回滚代码...${NC}"
if [ -f "$BACKUP_PATH/commit.txt" ]; then
    git reset --hard "$TARGET_COMMIT"
    echo -e "${GREEN}✓ 代码已回滚到: $TARGET_COMMIT${NC}"
else
    echo -e "${RED}警告: 未找到提交信息，跳过代码回滚${NC}"
fi

# 可选：恢复数据库
if [ -f "$BACKUP_PATH/database.sql" ]; then
    echo ""
    echo -e "${YELLOW}发现数据库备份，是否恢复数据库? (y/N):${NC}"
    read -r RESTORE_DB
    
    if [ "$RESTORE_DB" = "y" ] || [ "$RESTORE_DB" = "Y" ]; then
        echo -e "${YELLOW}3. 恢复数据库...${NC}"
        docker-compose up -d postgres
        sleep 10
        docker-compose exec -T postgres psql -U faa family_assistant < "$BACKUP_PATH/database.sql"
        echo -e "${GREEN}✓ 数据库已恢复${NC}"
    fi
fi

echo ""
echo -e "${YELLOW}4. 启动服务...${NC}"
docker-compose up -d

# 等待服务启动
echo -e "${YELLOW}5. 等待服务启动...${NC}"
sleep 15

# 健康检查
echo -e "${YELLOW}6. 健康检查...${NC}"
if curl -f -s "$HEALTH_URL" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 健康检查通过${NC}"
else
    echo -e "${RED}❌ 健康检查失败${NC}"
    echo -e "${YELLOW}请手动检查服务状态:${NC}"
    echo "  docker-compose logs --tail=50 faa-api"
    exit 1
fi

# 显示服务状态
echo ""
echo -e "${GREEN}📊 当前服务状态:${NC}"
docker-compose ps

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   ✅ 回滚完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

exit 0

