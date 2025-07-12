#!/bin/bash
# 自动部署脚本 - 由服务器定期执行
set -e

cd /opt/family-ai-assistant

# 检查是否首次运行
if [ ! -d ".git" ]; then
    echo "首次克隆代码..."
    git clone https://github.com/guanpeibj/family-ai-assistant.git .
fi

# 获取最新代码
echo "检查更新..."
git fetch origin master

# 检查是否有新的提交
LOCAL_COMMIT=$(git rev-parse HEAD)
REMOTE_COMMIT=$(git rev-parse origin/master)

if [ "$LOCAL_COMMIT" != "$REMOTE_COMMIT" ]; then
    echo "发现新版本，开始部署..."
    
    # 拉取最新代码
    git pull origin master
    
    # 检查是否有部署配置文件
    if [ -f "deploy-config.json" ]; then
        echo "使用部署配置文件..."
        
        # 创建环境变量文件
        jq -r '.env | to_entries[] | "\(.key)=\(.value)"' deploy-config.json > .env
        
        # 创建家庭数据文件
        jq -r '.family_data' deploy-config.json > family_data.json
        
        # 设置环境变量供Docker使用
        export $(cat .env | xargs)
        
        # 部署服务
        docker-compose down
        docker-compose up -d --build
        
        # 等待服务启动
        echo "等待服务启动..."
        sleep 20
        
        # 初始化家庭数据
        FAMILY_DATA_JSON=$(cat family_data.json) docker-compose exec -T -e FAMILY_DATA_JSON="$FAMILY_DATA_JSON" faa-api python scripts/init_family_data.py || true
        
        # 清理敏感文件
        rm -f deploy-config.json family_data.json
        
        # 从Git中删除敏感文件并推送
        git add .
        git commit -m "🧹 清理部署配置文件 - $(date)" || true
        git push || true
        
        echo "部署完成: $(date)"
        echo "服务状态:"
        docker-compose ps
    else
        echo "未找到部署配置文件，跳过部署"
    fi
else
    echo "代码已是最新版本"
fi
