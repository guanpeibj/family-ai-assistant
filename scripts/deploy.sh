#!/bin/bash
# FAA 统一部署脚本

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 显示帮助信息
show_help() {
    echo "FAA 部署脚本"
    echo ""
    echo "用法: ./scripts/deploy.sh [命令] [选项]"
    echo ""
    echo "命令:"
    echo "  install     - 安装系统依赖（Docker等）"
    echo "  setup       - 初始化项目配置"
    echo "  deploy      - 部署或更新服务"
    echo "  start       - 启动服务"
    echo "  stop        - 停止服务"
    echo "  restart     - 重启服务"
    echo "  logs        - 查看日志"
    echo "  status      - 检查服务状态"
    echo "  backup      - 备份数据"
    echo "  restore     - 恢复数据"
    echo "  clean       - 清理系统"
    echo ""
    echo "选项:"
    echo "  --remote    - 在远程服务器执行"
    echo "  --host      - 指定远程主机 (默认: 从环境变量读取)"
    echo "  --user      - 指定SSH用户 (默认: 从环境变量读取)"
    echo ""
    echo "示例:"
    echo "  ./scripts/deploy.sh install        # 本地安装依赖"
    echo "  ./scripts/deploy.sh deploy         # 本地部署"
    echo "  ./scripts/deploy.sh logs --remote  # 查看远程日志"
}

# 检查命令是否存在
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# 安装系统依赖
install_dependencies() {
    print_info "开始安装系统依赖..."
    
    # 更新系统
    sudo apt update && sudo apt upgrade -y
    
    # 安装 Docker
    if ! command_exists docker; then
        print_info "安装 Docker..."
        curl -fsSL https://get.docker.com | sh
        sudo usermod -aG docker $USER
        print_success "Docker 安装完成"
    else
        print_info "Docker 已安装"
    fi
    
    # 安装 Docker Compose
    if ! command_exists docker-compose; then
        print_info "安装 Docker Compose..."
        sudo apt install docker-compose -y
        print_success "Docker Compose 安装完成"
    else
        print_info "Docker Compose 已安装"
    fi
    
    # 安装其他工具
    sudo apt install -y git curl wget nano
    
    print_success "系统依赖安装完成！"
    print_warning "请重新登录以应用 Docker 组权限"
}

# 初始化配置
setup_project() {
    print_info "开始初始化项目配置..."
    
    # 检查 .env 文件
    if [ ! -f .env ]; then
        if [ -f env.example ]; then
            cp env.example .env
            print_warning "已创建 .env 文件，请编辑配置:"
            print_warning "nano .env"
        else
            print_error "env.example 文件不存在！"
            exit 1
        fi
    else
        print_info ".env 文件已存在"
    fi
    
    # 创建必要的目录
    mkdir -p logs backups
    
    # 设置权限
    chmod 600 .env
    
    print_success "项目配置初始化完成！"
}

# 部署服务
deploy_service() {
    print_info "开始部署服务..."
    
    # 检查配置
    if [ ! -f .env ]; then
        print_error ".env 文件不存在！请先运行 setup 命令"
        exit 1
    fi
    
    # 拉取最新代码（如果是 git 仓库）
    if [ -d .git ]; then
        print_info "拉取最新代码..."
        git pull || print_warning "无法拉取最新代码，使用本地版本"
    fi
    
    # 构建镜像
    print_info "构建 Docker 镜像..."
    docker-compose build
    
    # 停止旧服务
    print_info "停止旧服务..."
    docker-compose down
    
    # 启动新服务
    print_info "启动新服务..."
    docker-compose up -d
    
    # 清理旧镜像
    docker image prune -f
    
    # 等待服务启动
    print_info "等待服务启动..."
    sleep 10
    
    # 检查服务状态
    if docker-compose ps | grep -q "Up"; then
        print_success "服务部署成功！"
        
        # 初始化数据（首次部署）
        if [ ! -f .initialized ]; then
            print_info "首次部署，初始化数据..."
            docker-compose exec -T faa-api python scripts/init_family_data.py && touch .initialized
        fi
    else
        print_error "服务启动失败！"
        docker-compose logs --tail=50
        exit 1
    fi
}

# 查看日志
show_logs() {
    local service=$1
    if [ -z "$service" ]; then
        docker-compose logs -f --tail=100
    else
        docker-compose logs -f --tail=100 $service
    fi
}

# 检查状态
check_status() {
    print_info "服务状态:"
    docker-compose ps
    
    print_info "\n健康检查:"
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        print_success "API 服务正常"
    else
        print_error "API 服务异常"
    fi
    
    print_info "\n资源使用:"
    docker stats --no-stream
}

# 备份数据
backup_data() {
    print_info "开始备份数据..."
    
    local backup_dir="backups"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="${backup_dir}/backup_${timestamp}.sql"
    
    mkdir -p $backup_dir
    
    # 备份数据库
    docker-compose exec -T postgres pg_dump -U faa family_assistant > $backup_file
    
    # 备份配置文件
    cp .env "${backup_dir}/.env.${timestamp}"
    
    # 压缩备份
    tar -czf "${backup_dir}/backup_${timestamp}.tar.gz" $backup_file "${backup_dir}/.env.${timestamp}"
    rm $backup_file "${backup_dir}/.env.${timestamp}"
    
    print_success "备份完成: ${backup_dir}/backup_${timestamp}.tar.gz"
}

# 恢复数据
restore_data() {
    local backup_file=$1
    
    if [ -z "$backup_file" ]; then
        print_error "请指定备份文件！"
        echo "可用的备份:"
        ls -la backups/*.tar.gz 2>/dev/null || echo "没有找到备份文件"
        exit 1
    fi
    
    print_warning "恢复数据将覆盖现有数据！"
    read -p "确定要继续吗？(y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
    
    print_info "开始恢复数据..."
    
    # 解压备份
    tar -xzf $backup_file -C /tmp/
    
    # 恢复数据库
    local sql_file=$(tar -tzf $backup_file | grep .sql | head -1)
    docker-compose exec -T postgres psql -U faa -d family_assistant < /tmp/$sql_file
    
    print_success "数据恢复完成！"
}

# 清理系统
clean_system() {
    print_warning "清理将删除未使用的Docker资源"
    read -p "确定要继续吗？(y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
    
    print_info "清理Docker资源..."
    docker system prune -af
    docker volume prune -f
    
    print_success "清理完成！"
}

# 远程执行
remote_execute() {
    local cmd=$1
    local host=${DEPLOY_HOST:-${2:-}}
    local user=${DEPLOY_USER:-${3:-"root"}}
    
    if [ -z "$host" ]; then
        print_error "请指定远程主机地址！"
        exit 1
    fi
    
    print_info "在远程服务器 $user@$host 执行..."
    ssh $user@$host "cd ~/family-ai-assistant && ./scripts/deploy.sh $cmd"
}

# 主函数
main() {
    local command=$1
    shift
    
    # 处理远程执行
    if [[ "$@" == *"--remote"* ]]; then
        remote_execute "$command" "$@"
        exit 0
    fi
    
    case $command in
        install)
            install_dependencies
            ;;
        setup)
            setup_project
            ;;
        deploy)
            deploy_service
            ;;
        start)
            docker-compose up -d
            print_success "服务已启动"
            ;;
        stop)
            docker-compose down
            print_success "服务已停止"
            ;;
        restart)
            docker-compose restart
            print_success "服务已重启"
            ;;
        logs)
            show_logs "$@"
            ;;
        status)
            check_status
            ;;
        backup)
            backup_data
            ;;
        restore)
            restore_data "$1"
            ;;
        clean)
            clean_system
            ;;
        help|--help|-h|"")
            show_help
            ;;
        *)
            print_error "未知命令: $command"
            show_help
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@" 