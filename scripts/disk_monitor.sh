#!/bin/bash
# FAA 磁盘空间监控脚本
# 监控 Docker volumes 和宿主机磁盘使用情况

# 配置
THRESHOLD=80  # 告警阈值（百分比）
LOG_FILE="/opt/faa/logs/disk_monitor.log"

# 确保日志目录存在
mkdir -p "$(dirname "$LOG_FILE")"

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# 发送告警
send_alert() {
    local message="$1"
    log "发送告警: $message"
    
    # 如果配置了 Threema
    if [ -n "$THREEMA_BOT_ID" ] && [ -n "$THREEMA_ADMIN_ID" ] && [ -n "$THREEMA_SECRET" ]; then
        curl -X POST "https://msgapi.threema.ch/send_simple" \
            -d "from=$THREEMA_BOT_ID" \
            -d "to=$THREEMA_ADMIN_ID" \
            -d "secret=$THREEMA_SECRET" \
            -d "text=$message" > /dev/null 2>&1 || true
    fi
}

log "=== 开始磁盘监控 ==="

# 1. 检查 Docker system
log "检查 Docker 系统空间..."
DOCKER_DF=$(docker system df 2>/dev/null || echo "")
if [ -n "$DOCKER_DF" ]; then
    echo "$DOCKER_DF" >> "$LOG_FILE"
fi

# 2. 检查 Volumes
log "检查 Docker Volumes..."
for volume in family-ai-assistant_postgres_data family-ai-assistant_media_data family-ai-assistant_fastembed_cache; do
    if docker volume inspect "$volume" > /dev/null 2>&1; then
        SIZE=$(docker system df -v 2>/dev/null | grep "$volume" | awk '{print $3}' || echo "Unknown")
        log "  - $volume: $SIZE"
    fi
done

# 3. 检查容器内磁盘
log "检查容器内磁盘使用..."
CONTAINER_DF=$(docker-compose exec -T faa-api df -h 2>/dev/null | grep -E "Filesystem|/data" || echo "")
if [ -n "$CONTAINER_DF" ]; then
    echo "$CONTAINER_DF" >> "$LOG_FILE"
fi

# 4. 检查宿主机磁盘
log "检查宿主机磁盘使用..."
HOST_DF=$(df -h | grep -E "Filesystem|/var/lib/docker|/$")
echo "$HOST_DF" >> "$LOG_FILE"

# 5. 告警检查
CRITICAL=0
while IFS= read -r line; do
    if echo "$line" | grep -q "/var/lib/docker\|/$"; then
        USAGE=$(echo "$line" | awk '{print $5}' | sed 's/%//')
        MOUNT=$(echo "$line" | awk '{print $6}')
        
        if [ -n "$USAGE" ] && [ "$USAGE" -ge "$THRESHOLD" ]; then
            log "⚠️  告警: $MOUNT 使用率 ${USAGE}% (阈值 ${THRESHOLD}%)"
            CRITICAL=1
        fi
    fi
done <<< "$HOST_DF"

# 发送告警
if [ $CRITICAL -eq 1 ]; then
    send_alert "⚠️ FAA 磁盘空间告警！请检查服务器磁盘使用情况"
else
    log "✓ 磁盘空间正常"
fi

log "=== 磁盘监控完成 ==="
echo "" >> "$LOG_FILE"

exit 0

