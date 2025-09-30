#!/bin/bash
# 预算功能一键测试脚本

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                 FAA 预算功能测试套件                         ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查Docker容器状态
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "步骤1：检查容器状态"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker-compose ps | grep -E "faa-api|faa-mcp|postgres"
echo ""

# 选择测试类型
echo "请选择测试类型："
echo "  1) 快速验证（约10秒）"
echo "  2) 基础功能测试（约3分钟）"
echo "  3) 高级功能测试（约5分钟）"
echo "  4) 完整测试（约8分钟）"
echo "  5) 验证预算数据"
echo ""
read -p "请输入选择 [1-5]: " choice

case $choice in
  1)
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "快速验证测试"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "测试1：记账功能"
    curl -s -X POST http://localhost:8001/message \
      -H 'Content-Type: application/json' \
      -d '{"content": "测试：买菜30元", "user_id": "test_verify"}' | \
      python3 -c "import sys,json; r=json.load(sys.stdin); print('✓ 回复:', r['response'][:80])"
    echo ""
    
    echo "测试2：预算查询"
    curl -s -X POST http://localhost:8001/message \
      -H 'Content-Type: application/json' \
      -d '{"content": "这个月预算还剩多少？", "user_id": "test_verify"}' | \
      python3 -c "import sys,json; r=json.load(sys.stdin); print('✓ 回复:', r['response'][:80])"
    echo ""
    echo "${GREEN}✅ 快速验证完成！功能正常。${NC}"
    ;;
    
  2)
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "基础功能测试（约3分钟）"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    docker-compose exec -T faa-api python examples/test_budget.py
    ;;
    
  3)
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "高级功能测试（约5分钟）"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    docker-compose exec -T faa-api python examples/test_budget_advanced.py
    ;;
    
  4)
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "完整测试套件（约8分钟）"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "${YELLOW}运行基础功能测试...${NC}"
    docker-compose exec -T faa-api python examples/test_budget.py
    echo ""
    echo "${YELLOW}运行高级功能测试...${NC}"
    docker-compose exec -T faa-api python examples/test_budget_advanced.py
    echo ""
    echo "${GREEN}✅ 完整测试套件执行完成！${NC}"
    ;;
    
  5)
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "验证预算数据"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    docker-compose exec -T faa-api python -c "
import asyncio
from src.ai_engine import ai_engine
async def check():
    await ai_engine.initialize_mcp()
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
    
    await ai_engine.close()
asyncio.run(check())
    "
    ;;
    
  *)
    echo "${YELLOW}无效选择，退出${NC}"
    exit 1
    ;;
esac

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "测试完成！"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📚 相关文档："
echo "  • 快速参考：BUDGET_QUICK_REFERENCE.md"
echo "  • 功能指南：docs/BUDGET_FEATURE_GUIDE.md"
echo "  • 使用示例：examples/budget_usage_examples.md"
echo ""
