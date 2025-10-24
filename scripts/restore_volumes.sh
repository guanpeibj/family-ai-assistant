#!/bin/bash
# FAA Docker Volumes 恢复脚本
# 从备份恢复数据库和媒体文件

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 配置
BACKUP_ROOT="/opt/faa/backups"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   FAA Volumes 恢复${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 检查备份目录
if [ ! -d "$BACKUP_ROOT" ]; then
    echo -e "${RED}错误: 备份目录不存在: $BACKUP_ROOT${NC}"
    exit 1
fi

# 列出可用备份
echo -e "${YELLOW}可用的备份:${NC}"
echo ""
BACKUPS=($(ls -t "$BACKUP_ROOT" | grep "^volumes_"))

if [ ${#BACKUPS[@]} -eq 0 ]; then
    echo -e "${RED}未找到备份${NC}"
    exit 1
fi

for i in "${!BACKUPS[@]}"; do
    BACKUP_PATH="$BACKUP_ROOT/${BACKUPS[$i]}"
    BACKUP_SIZE=$(du -sh "$BACKUP_PATH" | cut -f1)
    echo "$((i+1)). ${BACKUPS[$i]} - 大小: $BACKUP_SIZE"
    
    if [ -f "$BACKUP_PATH/backup_info.txt" ]; then
        echo "   $(grep "备份时间" "$BACKUP_PATH/backup_info.txt")"
    fi
done

# 选择备份
echo ""
echo -e "${YELLOW}选择要恢复的备份（输入序号，默认 1）:${NC}"
read -r CHOICE

if [ -z "$CHOICE" ]; then
    CHOICE=1
fi

# 验证输入
if ! [[ "$CHOICE" =~ ^[0-9]+$ ]] || [ "$CHOICE" -lt 1 ] || [ "$CHOICE" -gt "${#BACKUPS[@]}" ]; then
    echo -e "${RED}无效的选择${NC}"
    exit 1
fi

SELECTED_BACKUP="${BACKUPS[$((CHOICE-1))]}"
BACKUP_PATH="$BACKUP_ROOT/$SELECTED_BACKUP"

echo ""
echo -e "${YELLOW}即将恢复: $SELECTED_BACKUP${NC}"
if [ -f "$BACKUP_PATH/backup_info.txt" ]; then
    cat "$BACKUP_PATH/backup_info.txt"
fi

echo ""
echo -e "${RED}警告: 这将覆盖当前数据！${NC}"
echo -e "${YELLOW}是否继续? (y/N):${NC}"
read -r CONFIRM

if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo -e "${YELLOW}取消恢复${NC}"
    exit 0
fi

# 恢复数据库
if [ -f "$BACKUP_PATH/database.sql.gz" ]; then
    echo ""
    echo -e "${YELLOW}1. 恢复数据库...${NC}"
    
    # 确保 postgres 正在运行
    docker-compose up -d postgres
    sleep 5
    
    if gunzip < "$BACKUP_PATH/database.sql.gz" | docker-compose exec -T postgres psql -U faa family_assistant 2>/dev/null; then
        echo -e "${GREEN}✓ 数据库恢复成功${NC}"
    else
        echo -e "${RED}✗ 数据库恢复失败${NC}"
    fi
else
    echo -e "${YELLOW}⚠ 未找到数据库备份${NC}"
fi

# 恢复媒体文件
if [ -f "$BACKUP_PATH/media.tar.gz" ]; then
    echo ""
    echo -e "${YELLOW}2. 恢复媒体文件...${NC}"
    
    if docker run --rm \
        -v family-ai-assistant_media_data:/data \
        -v "$BACKUP_PATH":/backup \
        alpine sh -c "rm -rf /data/* && tar xzf /backup/media.tar.gz -C /" 2>/dev/null; then
        echo -e "${GREEN}✓ 媒体文件恢复成功${NC}"
    else
        echo -e "${RED}✗ 媒体文件恢复失败${NC}"
    fi
else
    echo -e "${YELLOW}⚠ 未找到媒体文件备份${NC}"
fi

# 重启服务
echo ""
echo -e "${YELLOW}3. 重启服务...${NC}"
docker-compose restart faa-api faa-mcp

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   恢复完成${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

exit 0

