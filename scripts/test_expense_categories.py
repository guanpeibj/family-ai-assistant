#!/usr/bin/env python3
"""
费用类目系统测试脚本

功能：验证新的费用类目配置是否正确工作

使用方法：
    python scripts/test_expense_categories.py
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ai_engine import ai_engine
from src.services.expense_categories_service import expense_categories_service
import structlog

logger = structlog.get_logger(__name__)


async def test_service_loading():
    """测试1：ExpenseCategoriesService配置加载"""
    print("=" * 60)
    print("测试1：配置服务加载")
    print("=" * 60)
    
    context = expense_categories_service.get_categories_context()
    
    print(f"✅ 总预算: {context['total_budget']} 元")
    print(f"✅ 类目数量: {len(context['categories'])}")
    print(f"✅ 类目列表: {[cat.get('category_name') for cat in context['categories'][:5]]}...")
    print()


async def test_config_in_memories():
    """测试2：配置是否存储在memories中"""
    print("=" * 60)
    print("测试2：配置存储验证")
    print("=" * 60)
    
    # AIEngineV2 在 __init__ 时已完成初始化
    
    result = await ai_engine._call_mcp_tool(
        'search',
        query="",
        user_id="family_default",
        filters={
            "jsonb_equals": {"type": "expense_category_config"},
            "limit": 1
        }
    )
    
    configs = [item for item in result if not item.get('_meta')]
    
    if configs:
        config = configs[0]
        ai_data = config.get('ai_understanding', {})
        print(f"✅ 配置已存储")
        print(f"   ID: {config.get('id')}")
        print(f"   总预算: {ai_data.get('total_budget')} 元")
        print(f"   类目数: {len(ai_data.get('categories', []))}")
        print(f"   版本: {ai_data.get('version')}")
    else:
        print("❌ 配置未找到，请先运行: python scripts/init_budget_data.py")
        return False
    
    print()
    return True


async def test_budget_records():
    """测试3：预算记录是否正确"""
    print("=" * 60)
    print("测试3：预算记录验证")
    print("=" * 60)
    
    result = await ai_engine._call_mcp_tool(
        'search',
        query="",
        user_id="family_default",
        filters={
            "jsonb_equals": {"type": "budget"},
            "limit": 5
        }
    )
    
    budgets = [item for item in result if not item.get('_meta')]
    
    if budgets:
        print(f"✅ 找到 {len(budgets)} 条预算记录")
        for budget in budgets:
            ai_data = budget.get('ai_understanding', {})
            print(f"   - {ai_data.get('period')}: {ai_data.get('total_budget')} 元")
            print(f"     类目预算数: {len(ai_data.get('category_budgets', {}))}")
    else:
        print("⚠️  未找到预算记录")
    
    print()


async def test_ai_classification():
    """测试4：AI分类能力（模拟）"""
    print("=" * 60)
    print("测试4：AI分类测试（模拟）")
    print("=" * 60)
    
    print("提示：这是一个完整的AI流程测试")
    print("你可以使用以下命令测试AI分类：")
    print()
    print("  curl -X POST http://localhost:8000/message \\")
    print("    -H 'Content-Type: application/json' \\")
    print("    -d '{")
    print('      "content": "买菜花了80元",')
    print('      "user_id": "dad"')
    print("    }'")
    print()
    print("预期：AI应该将其分类为 category=\"食材\"")
    print()


async def test_database_indexes():
    """测试5：数据库索引验证"""
    print("=" * 60)
    print("测试5：数据库索引检查")
    print("=" * 60)
    
    print("提示：检查以下索引是否存在")
    print("  - idx_memories_aiu_category")
    print("  - idx_memories_aiu_sub_category")
    print("  - idx_memories_cat_subcat")
    print()
    print("运行SQL检查:")
    print("  SELECT indexname FROM pg_indexes")
    print("  WHERE tablename = 'memories' AND indexname LIKE '%category%';")
    print()


async def main():
    """主测试流程"""
    print()
    print("🧪 费用类目系统测试")
    print()
    
    try:
        # 测试1：服务加载
        await test_service_loading()
        
        # 测试2：配置存储
        config_ok = await test_config_in_memories()
        
        if config_ok:
            # 测试3：预算记录
            await test_budget_records()
        
        # 测试4：AI分类说明
        await test_ai_classification()
        
        # 测试5：数据库索引
        await test_database_indexes()
        
        print("=" * 60)
        print("✅ 测试完成")
        print("=" * 60)
        print()
        print("下一步:")
        print("1. 如果配置未找到，运行: python scripts/init_budget_data.py")
        print("2. 启动服务测试AI分类: docker-compose up -d")
        print("3. 发送测试消息验证分类功能")
        print()
        
        return 0
        
    except Exception as e:
        logger.error("test_failed", error=str(e))
        print()
        print(f"❌ 测试失败: {e}")
        print()
        return 1
    finally:
        # AIEngineV2 不需要显式关闭
        pass


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

