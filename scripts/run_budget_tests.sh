#!/bin/bash
# FAA 预算功能测试脚本 (V2版本)
#
# ⚠️  已更新为使用V2测试系统
# 新系统特性：三层验证 + 量化评分（0-100分）

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           FAA 预算功能测试套件 (V2系统)                      ║"
echo "║  三层验证：数据(40分) + 智能(40分) + 体验(20分)              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 检查Docker容器状态
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "步骤1：检查容器状态"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker-compose ps | grep -E "faa-api|faa-mcp|postgres"
echo ""

# 选择测试类型
echo "请选择测试类型："
echo -e "  ${BLUE}1)${NC} 快速验证 V2（3个预算测试用例，约30秒）"
echo -e "  ${BLUE}2)${NC} 预算功能完整测试 V2（5个用例，约2分钟）"
echo -e "  ${BLUE}3)${NC} 包含预算的黄金测试集（55个用例，约15分钟）"
echo -e "  ${BLUE}4)${NC} 验证预算数据（数据库查询）"
echo -e "  ${BLUE}5)${NC} 旧版本测试（examples/）- 不推荐"
echo ""
read -p "请输入选择 [1-5]: " choice

case $choice in
  1)
    echo ""
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}快速验证 - 预算功能核心测试（V2系统）${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "${BLUE}测试用例：TC031-TC033（3个预算核心用例）${NC}"
    echo -e "${BLUE}预计耗时：约30秒${NC}"
    echo -e "${BLUE}成本：约$0.10${NC}"
    echo ""
    
    # 创建临时测试脚本
    docker-compose exec -T faa-api python -c "
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, '/app')

from tests.integration.base_new import IntegrationTestBase

async def quick_budget_test():
    tester = IntegrationTestBase('budget_quick')
    await tester.setup()
    
    # TC031: 设置预算
    await tester.run_test(
        test_id='TC031',
        test_name='设置月度预算',
        message='设置本月预算10000元',
        expected_behavior={'intent': '设置预算', 'key_actions': ['保存预算设置'], 'response_should': '确认预算已设置'},
        data_verification={'should_store': True, 'expected_data': {'type': 'budget_setting', 'amount': 10000}}
    )
    
    # TC014: 查询预算
    await tester.run_test(
        test_id='TC014',
        test_name='预算查询',
        message='这个月预算还剩多少？',
        expected_behavior={'intent': '查询预算剩余', 'key_actions': ['查询预算设置', '计算已用金额'], 'response_should': '告知预算剩余'},
        data_verification={'should_store': False}
    )
    
    # TC033: 预算状态
    await tester.run_test(
        test_id='TC033',
        test_name='预算使用情况',
        message='本月预算使用情况',
        expected_behavior={'intent': '查询预算状态', 'key_actions': ['计算已用百分比'], 'response_should': '告知预算使用情况'},
        data_verification={'should_store': False}
    )
    
    summary = tester.print_summary()
    await tester.teardown()
    
    return summary.get('pass_rate', 0) >= 0.8 and summary.get('avg_total_score', 0) >= 70

result = asyncio.run(quick_budget_test())
sys.exit(0 if result else 1)
"
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        echo ""
        echo -e "${GREEN}✅ 预算功能快速验证通过！${NC}"
    else
        echo ""
        echo -e "${RED}❌ 预算功能验证失败！${NC}"
    fi
    ;;
    
  2)
    echo ""
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}预算功能完整测试（V2系统）${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "${BLUE}测试用例：TC031-TC035（5个预算用例）${NC}"
    echo -e "${BLUE}预计耗时：约2分钟${NC}"
    echo -e "${BLUE}成本：约$0.16${NC}"
    echo ""
    
    # 使用run_golden_set.py运行预算相关用例
    docker-compose exec -T faa-api python -c "
import asyncio
import sys
from pathlib import Path
import yaml
sys.path.insert(0, '/app')

from tests.integration.base_new import IntegrationTestBase
from validators.scoring import ScoringSystem

async def budget_full_test():
    # 加载yaml
    with open('/app/tests/integration/test_cases/golden_set.yaml', 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    
    # 获取预算类用例
    budget_cases = data.get('budget', [])
    
    tester = IntegrationTestBase('budget_full')
    await tester.setup()
    
    print(f'\\n加载了 {len(budget_cases)} 个预算测试用例\\n')
    
    for case in budget_cases:
        await tester.run_test(
            test_id=case['test_id'],
            test_name=case['test_name'],
            message=case['user_input'],
            expected_behavior=case['expected_behavior'],
            data_verification=case.get('data_verification')
        )
        await asyncio.sleep(0.3)
    
    summary = tester.print_summary()
    await tester.teardown()
    
    return summary.get('pass_rate', 0) >= 0.8 and summary.get('avg_total_score', 0) >= 70

result = asyncio.run(budget_full_test())
sys.exit(0 if result else 1)
"
    EXIT_CODE=$?
    ;;
    
  3)
    echo ""
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}黄金测试集（包含预算功能）${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "${BLUE}测试用例：55个黄金测试集（包含5个预算用例）${NC}"
    echo -e "${BLUE}预计耗时：约15分钟${NC}"
    echo -e "${BLUE}成本：约$1.80${NC}"
    echo ""
    
    docker-compose exec -T faa-api python tests/integration/run_golden_set.py
    EXIT_CODE=$?
    ;;
    
  4)
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "验证预算数据"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    docker-compose exec -T faa-api python -c "
import asyncio
from src.ai_engine import ai_engine
async def check():
    # AIEngineV2 在 __init__ 时已完成初始化
    result = await ai_engine._call_mcp_tool('search',
        query='', user_id='family_default',
        filters={'jsonb_equals': {'type': 'budget'}, 'limit': 10})
    
    budgets = [x for x in result if not x.get('_meta')]
    print(f'找到 {len(budgets)} 个预算记录：')
    print('')
    for b in budgets:
        aiu = b.get('ai_understanding', {})
        period = aiu.get('period')
        total = aiu.get('total_budget')
        cats = aiu.get('category_budgets', {})
        print(f'  • {period}: 总预算 ¥{total}')
        print(f'    类目数：{len(cats)}')
    
    # AIEngineV2 不需要显式关闭
asyncio.run(check())
    "
    ;;
    
  5)
    echo ""
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}旧版本测试（examples/）- 不推荐${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "${RED}⚠️  旧版本测试不包含三层验证和量化评分${NC}"
    echo -e "${RED}⚠️  建议使用选项1或2的V2测试${NC}"
    echo ""
    read -p "确定要运行旧版本测试？[y/N]: " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        echo "已取消"
        exit 0
    fi
    
    echo ""
    docker-compose exec -T faa-api python examples/test_budget.py
    EXIT_CODE=$?
    ;;
    
  *)
    echo -e "${RED}❌ 无效选择${NC}"
    exit 1
    ;;
esac

# 显示结果
echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}✅ 测试完成并通过！${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
else
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}❌ 测试失败！${NC}"
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
fi

echo ""
echo "📚 V2测试系统文档："
echo "  • README: tests/integration/README.md"
echo "  • 快速上手: tests/integration/QUICK_START_V2.md"
echo "  • 完整指南: tests/integration/TEST_SYSTEM_V2_GUIDE.md"
echo ""

exit $EXIT_CODE
