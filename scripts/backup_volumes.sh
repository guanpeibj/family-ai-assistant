#!/bin/bash
# FAA Docker Volumes 备份脚本
# 备份数据库、媒体文件到指定目录

set -e

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 配置
BACKUP_ROOT="/opt/faa/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$BACKUP_ROOT/volumes_$TIMESTAMP"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   FAA Volumes 备份${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 创建备份目录
mkdir -p "$BACKUP_DIR"
echo -e "${YELLOW}备份目录: $BACKUP_DIR${NC}"
echo ""

# 1. 备份数据库
echo -e "${YELLOW}1. 备份数据库...${NC}"
if docker-compose exec -T postgres pg_dump -U faa family_assistant | gzip > "$BACKUP_DIR/database.sql.gz"; then
    DB_SIZE=$(du -sh "$BACKUP_DIR/database.sql.gz" | cut -f1)
    echo -e "${GREEN}✓ 数据库备份完成: $DB_SIZE${NC}"
else
    echo -e "${RED}✗ 数据库备份失败${NC}"
fi

# 2. 备份媒体文件
echo -e "${YELLOW}2. 备份媒体文件...${NC}"
if docker run --rm \
    -v family-ai-assistant_media_data:/data \
    -v "$BACKUP_DIR":/backup \
    alpine tar czf /backup/media.tar.gz /data 2>/dev/null; then
    MEDIA_SIZE=$(du -sh "$BACKUP_DIR/media.tar.gz" | cut -f1)
    echo -e "${GREEN}✓ 媒体文件备份完成: $MEDIA_SIZE${NC}"
else
    echo -e "${YELLOW}⚠ 媒体文件备份失败（可能为空）${NC}"
fi

# 3. 记录备份信息
echo -e "${YELLOW}3. 记录备份信息...${NC}"
cat > "$BACKUP_DIR/backup_info.txt" <<EOF
备份时间: $(date)
数据库大小: $(du -sh "$BACKUP_DIR/database.sql.gz" 2>/dev/null | cut -f1 || echo "N/A")
媒体文件大小: $(du -sh "$BACKUP_DIR/media.tar.gz" 2>/dev/null | cut -f1 || echo "N/A")
Git 提交: $(cd /opt/faa/family-ai-assistant && git rev-parse HEAD)
EOF
echo -e "${GREEN}✓ 备份信息已记录${NC}"

# 4. 总结
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   备份完成${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "位置: $BACKUP_DIR"
echo -e "总大小: $(du -sh "$BACKUP_DIR" | cut -f1)"
echo ""

# 5. 清理旧备份（保留 30 个）
echo -e "${YELLOW}清理旧备份（保留最近 30 个）...${NC}"
cd "$BACKUP_ROOT"
ls -t | grep "^volumes_" | tail -n +31 | xargs -r rm -rf
echo -e "${GREEN}✓ 清理完成${NC}"

exit 0

