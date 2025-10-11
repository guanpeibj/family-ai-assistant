#!/bin/bash
# FAA 集成测试运行脚本（已迁移到V2）
# 
# ⚠️  此脚本已更新为使用V2测试系统
# 新系统特性：三层验证（数据/智能/体验）+ 量化评分（0-100分）
#
# 使用方式：
#   ./scripts/run_integration_tests.sh quick    # 快速验证（10个用例，2分钟）
#   ./scripts/run_integration_tests.sh p0       # P0核心测试（约30个用例）
#   ./scripts/run_integration_tests.sh golden   # 黄金测试集（55个用例，15分钟）
#   ./scripts/run_integration_tests.sh          # 默认运行quick
#
# 详细说明请查看：tests/integration/README.md

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 获取测试类型参数（V2系统）
TEST_TYPE=${1:-quick}

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          FAA 集成测试系统 V2                                  ║${NC}"
echo -e "${BLUE}║  三层验证：数据(40分) + 智能(40分) + 体验(20分)              ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
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

# 步骤3：运行测试（V2系统）
echo ""
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}3️⃣  运行集成测试${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# 根据类型选择测试命令（V2系统）
case $TEST_TYPE in
  quick)
    echo -e "${GREEN}测试类型：快速验证（10个用例，约2分钟）${NC}"
    echo -e "${BLUE}成本：约$0.35${NC}"
    echo ""
    TEST_CMD="python tests/integration/run_golden_set.py --limit 10"
    ;;
    
  p0|P0)
    echo -e "${GREEN}测试类型：P0核心功能（约30个用例，约8分钟）${NC}"
    echo -e "${BLUE}成本：约$1.00${NC}"
    echo ""
    TEST_CMD="python tests/integration/test_p0_core_all.py"
    ;;
    
  golden|full|all)
    echo -e "${GREEN}测试类型：黄金测试集（55个用例，约15分钟）${NC}"
    echo -e "${BLUE}成本：约$1.80${NC}"
    echo ""
    TEST_CMD="python tests/integration/run_golden_set.py"
    ;;
    
  example)
    echo -e "${GREEN}测试类型：示例测试（8个用例，约2分钟）${NC}"
    echo -e "${BLUE}成本：约$0.30${NC}"
    echo ""
    TEST_CMD="python tests/integration/test_p0_accounting_v2.py"
    ;;
    
  *)
    echo -e "${RED}❌ 未知的测试类型：$TEST_TYPE${NC}"
    echo ""
    echo "支持的类型："
    echo "  quick   - 快速验证（10个用例，2分钟）"
    echo "  p0      - P0核心功能（约30个用例，8分钟）"
    echo "  golden  - 黄金测试集（55个用例，15分钟）"
    echo "  example - 示例测试（8个用例，2分钟）"
    echo ""
    echo "查看详细说明："
    echo "  cat tests/integration/README.md"
    exit 1
    ;;
esac

# 在容器内运行测试
if docker-compose exec -T faa-api $TEST_CMD; then
    EXIT_CODE=$?
else
    EXIT_CODE=$?
fi

# 步骤4：显示报告（V2系统）
echo ""
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}4️⃣  测试报告${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "报告位置："
echo "  • JSON报告：tests/integration/reports/*.json"
echo "  • 文本报告：tests/integration/reports/*.txt"
echo ""
echo "查看报告："
echo ""
echo "  # 列出所有报告（按时间倒序）"
echo "  docker-compose exec faa-api ls -lht tests/integration/reports/"
echo ""
echo "  # 查看最新文本报告"
echo "  docker-compose exec faa-api sh -c 'cat \$(ls -t tests/integration/reports/*.txt 2>/dev/null | head -1)'"
echo ""
echo "  # 查看最新JSON报告（格式化）"
echo "  docker-compose exec faa-api sh -c 'cat \$(ls -t tests/integration/reports/*.json 2>/dev/null | head -1)' | jq '.summary'"
echo ""

# 显示评分说明
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}✅ 测试通过！${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "V2评分体系："
    echo "  • 数据层(40分): 验证数据是否正确存储"
    echo "  • 智能层(40分): AI评估意图理解和信息提取"
    echo "  • 体验层(20分): AI评估用户体验和人设契合"
    echo "  • 总分(100分): 三层累加，60分及格"
    echo ""
    echo "通过标准："
    if [ "$TEST_TYPE" == "golden" ] || [ "$TEST_TYPE" == "full" ] || [ "$TEST_TYPE" == "all" ]; then
        echo "  • 通过率 ≥ 90%（黄金测试集高标准）"
        echo "  • 平均分 ≥ 80"
    else
        echo "  • 通过率 ≥ 80%"
        echo "  • 平均分 ≥ 70"
    fi
else
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}❌ 测试失败！${NC}"
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "排查建议："
    echo "  1. 查看上方失败用例的详细评分"
    echo "  2. 检查数据层分数（如果<24/40，说明数据未正确存储）"
    echo "  3. 检查智能层分数（如果<24/40，说明AI理解有问题）"
    echo "  4. 查看JSON报告的详细分析"
    echo ""
    echo "查看详细报告："
    echo "  docker-compose exec faa-api sh -c 'cat \$(ls -t tests/integration/reports/*.txt 2>/dev/null | head -1)'"
fi

echo ""
echo "V2系统文档："
echo "  • README: tests/integration/README.md"
echo "  • 快速上手: tests/integration/QUICK_START_V2.md"
echo "  • 完整指南: tests/integration/TEST_SYSTEM_V2_GUIDE.md"
echo ""

exit $EXIT_CODE

