#!/bin/bash
# FAA 集成测试运行脚本
# 
# 在Docker容器内运行集成测试，自动处理服务启动和等待
#
# 使用方式：
#   ./scripts/run_integration_tests.sh P0       # 运行P0测试
#   ./scripts/run_integration_tests.sh P1       # 运行P1测试
#   ./scripts/run_integration_tests.sh P2       # 运行P2测试
#   ./scripts/run_integration_tests.sh all      # 运行所有测试
#   ./scripts/run_integration_tests.sh          # 默认运行P0

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 获取优先级参数
PRIORITY=${1:-P0}

echo -e "${GREEN}🚀 FAA 集成测试运行脚本${NC}"
echo "=========================================="
echo ""

# 步骤1：检查服务状态
echo -e "${YELLOW}1️⃣ 检查Docker服务状态...${NC}"
if ! docker-compose ps | grep -q "Up"; then
    echo -e "${YELLOW}⚠️  服务未运行，正在启动...${NC}"
    docker-compose up -d
    
    echo -e "${YELLOW}⏳ 等待服务就绪（15秒）...${NC}"
    sleep 15
else
    echo -e "${GREEN}✅ 服务已运行${NC}"
fi

# 步骤2：检查服务健康
echo ""
echo -e "${YELLOW}2️⃣ 检查服务健康状态...${NC}"

# 检查PostgreSQL
if docker-compose exec -T postgres pg_isready -U faa -d family_assistant > /dev/null 2>&1; then
    echo -e "${GREEN}✅ PostgreSQL 健康${NC}"
else
    echo -e "${RED}❌ PostgreSQL 不可用${NC}"
    exit 1
fi

# 检查MCP服务
if curl -s -f http://localhost:9000/tools > /dev/null 2>&1; then
    echo -e "${GREEN}✅ MCP服务 健康${NC}"
else
    echo -e "${RED}❌ MCP服务不可用${NC}"
    exit 1
fi

# 步骤3：运行测试
echo ""
echo -e "${YELLOW}3️⃣ 运行集成测试（优先级：${PRIORITY}）...${NC}"
echo "=========================================="
echo ""

# 构建测试命令
if [ "$PRIORITY" == "all" ]; then
    TEST_CMD="python tests/integration/run_tests.py --all"
else
    TEST_CMD="python tests/integration/run_tests.py --priority ${PRIORITY}"
fi

# 在容器内运行测试
if docker-compose exec -T faa-api $TEST_CMD; then
    echo ""
    echo -e "${GREEN}✅ 测试通过！${NC}"
    EXIT_CODE=0
else
    echo ""
    echo -e "${RED}❌ 测试失败！${NC}"
    EXIT_CODE=1
fi

# 步骤4：显示报告位置
echo ""
echo -e "${YELLOW}4️⃣ 测试报告${NC}"
echo "----------------------------------------"
echo "报告保存在容器内：/app/tests/integration/reports/"
echo "可以通过以下方式查看："
echo ""
echo "  # 列出报告"
echo "  docker-compose exec faa-api ls -lh tests/integration/reports/"
echo ""
echo "  # 查看最新报告"
echo "  docker-compose exec faa-api cat tests/integration/reports/test_report_${PRIORITY}_*.json | head -100"
echo ""

exit $EXIT_CODE

