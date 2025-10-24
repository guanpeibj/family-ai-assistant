#!/bin/bash
# FAA 健康检查脚本
# 用于 crontab 定期检查服务状态
# 建议配置：*/5 * * * * /opt/faa/scripts/health_check.sh

set -e

# 配置
HEALTH_URL="http://localhost:8001/health"
FAA_DIR="/opt/faa/family-ai-assistant"
LOG_FILE="/opt/faa/logs/health_check.log"
MAX_RETRIES=3
RETRY_INTERVAL=10

# 确保日志目录存在
mkdir -p "$(dirname "$LOG_FILE")"

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# 检查服务健康
check_health() {
    local retry=0
    while [ $retry -lt $MAX_RETRIES ]; do
        if curl -f -s -m 5 "$HEALTH_URL" > /dev/null 2>&1; then
            return 0
        fi
        retry=$((retry + 1))
        sleep $RETRY_INTERVAL
    done
    return 1
}

# 重启服务
restart_service() {
    log "⚠️  健康检查失败，尝试重启服务..."
    
    cd "$FAA_DIR"
    docker-compose restart faa-api
    
    # 等待服务启动
    sleep 15
    
    # 再次检查
    if check_health; then
        log "✅ 服务重启成功"
        return 0
    else
        log "❌ 服务重启后仍然失败"
        return 1
    fi
}

# 发送告警（可选，需要配置 Threema）
send_alert() {
    local message="$1"
    
    # 如果配置了 Threema，发送告警
    if [ -n "$THREEMA_BOT_ID" ] && [ -n "$THREEMA_ADMIN_ID" ] && [ -n "$THREEMA_SECRET" ]; then
        curl -X POST "https://msgapi.threema.ch/send_simple" \
            -d "from=$THREEMA_BOT_ID" \
            -d "to=$THREEMA_ADMIN_ID" \
            -d "secret=$THREEMA_SECRET" \
            -d "text=$message" > /dev/null 2>&1 || true
    fi
}

# 主逻辑
if check_health; then
    # 健康检查通过，记录成功
    log "✅ 健康检查通过"
    exit 0
else
    # 健康检查失败，尝试重启
    log "❌ 健康检查失败"
    
    if restart_service; then
        send_alert "⚠️ FAA 服务异常，已自动重启并恢复"
        exit 0
    else
        send_alert "🚨 FAA 服务异常！自动重启失败，请尽快检查服务器"
        exit 1
    fi
fi

