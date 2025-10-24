#!/bin/bash
# FAA 日志监控脚本
# 监控 Docker 容器日志中的错误，并发送告警

set -e

# 配置
LOG_DIR="/opt/faa/logs"
STATE_FILE="/tmp/faa_log_monitor_state"
ERROR_THRESHOLD=5  # 错误数量阈值

# 确保日志目录存在
mkdir -p "$LOG_DIR"

# 日志函数
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_DIR/monitor.log"
}

# 获取容器日志中的错误
check_errors() {
    local service="$1"
    local since_time="${2:-5m}"
    
    # 获取错误日志
    docker-compose -f /opt/faa/family-ai-assistant/docker-compose.yml \
        logs --since="$since_time" "$service" 2>&1 | \
        grep -i "error\|exception\|fatal\|critical" || true
}

# 发送告警
send_alert() {
    local message="$1"
    
    log_message "发送告警: $message"
    
    # 如果配置了 Threema
    if [ -n "$THREEMA_BOT_ID" ] && [ -n "$THREEMA_ADMIN_ID" ] && [ -n "$THREEMA_SECRET" ]; then
        curl -X POST "https://msgapi.threema.ch/send_simple" \
            -d "from=$THREEMA_BOT_ID" \
            -d "to=$THREEMA_ADMIN_ID" \
            -d "secret=$THREEMA_SECRET" \
            -d "text=$message" > /dev/null 2>&1 || true
    fi
}

# 主逻辑
main() {
    log_message "开始日志监控"
    
    # 检查每个服务
    for service in faa-api faa-mcp postgres; do
        # 获取最近 5 分钟的错误
        errors=$(check_errors "$service" "5m")
        
        if [ -n "$errors" ]; then
            error_count=$(echo "$errors" | wc -l)
            
            if [ "$error_count" -ge "$ERROR_THRESHOLD" ]; then
                log_message "⚠️  检测到 $service 服务有 $error_count 个错误"
                
                # 提取最近的几个错误
                recent_errors=$(echo "$errors" | tail -3)
                
                # 发送告警
                send_alert "⚠️ FAA $service 服务检测到 $error_count 个错误，最近的错误：
$recent_errors"
            else
                log_message "✓ $service 服务有少量错误 ($error_count)，低于阈值"
            fi
        else
            log_message "✓ $service 服务无错误"
        fi
    done
    
    log_message "日志监控完成"
}

# 执行监控
main

exit 0

