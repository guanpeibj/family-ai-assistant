#!/usr/bin/env python3
"""
预算数据初始化脚本

功能：
1. 从 family_private_data.json 读取预算配置
2. 为当前月份和下个月创建预算记录
3. 存储到 memories 表，供 AI 查询和应用

使用方法：
    python scripts/init_budget_data.py
"""
import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ai_engine import ai_engine
import structlog

logger = structlog.get_logger(__name__)


async def load_budget_config():
    """从配置文件加载预算配置（新版本：支持层级类目）"""
    config_file = project_root / "family_private_data.json"
    
    if not config_file.exists():
        logger.error("config_file_not_found", path=str(config_file))
        return None
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 读取新版费用类目配置
        expense_config = config.get('expense_categories_budget', {})
        
        if not expense_config:
            logger.error("expense_categories_budget_not_found")
            return None
        
        # 查找财务负责人（family_default用于家庭共享配置）
        user_id = 'family_default'
        
        logger.info(
            "config_loaded",
            user_id=user_id,
            monthly_total=expense_config.get('monthly_budget_total'),
            categories_count=len(expense_config.get('monthly_categories_budget', []))
        )
        
        return {
            'user_id': user_id,
            'expense_config': expense_config
        }
    except Exception as e:
        logger.error("config_load_failed", error=str(e))
        return None


async def create_expense_categories_config(user_id: str, expense_config: dict):
    """创建费用类目配置记录（存储到memories）"""
    
    from src.services.expense_categories_service import expense_categories_service
    
    # 使用service格式化详细描述（供content字段使用）
    context = expense_categories_service.get_categories_context()
    
    content = f"家庭费用类目配置\n月度总预算: {expense_config.get('monthly_budget_total', 0)}元\n\n{context['formatted_description']}"
    
    ai_data = {
        "type": "expense_category_config",
        "total_budget": expense_config.get('monthly_budget_total', 0),
        "currency": expense_config.get('currency', 'CNY'),
        "categories": expense_config.get('monthly_categories_budget', []),
        "occurred_at": datetime.now().isoformat(),
        "source": "init_script",
        "version": "2.0"
    }
    
    # 检查是否已存在
    existing = await ai_engine._call_mcp_tool(
        'search',
        query="",
        user_id=user_id,
        filters={
            "jsonb_equals": {"type": "expense_category_config"},
            "limit": 1
        }
    )
    
    existing_configs = [item for item in existing if not item.get('_meta')]
    
    if existing_configs:
        # 更新现有配置
        config_id = existing_configs[0].get('id')
        logger.info("expense_config_exists", config_id=config_id)
        
        try:
            result = await ai_engine._call_mcp_tool(
                'update_memory_fields',
                memory_id=config_id,
                fields={
                    'content': content,
                    'ai_understanding': ai_data
                }
            )
            logger.info("expense_config_updated", config_id=config_id)
            return result
        except Exception as e:
            logger.error("expense_config_update_failed", error=str(e))
            return None
    
    # 创建新配置
    try:
        result = await ai_engine._call_mcp_tool(
            'store',
            content=content,
            ai_data=ai_data,
            user_id=user_id
        )
        
        if result.get('success'):
            logger.info(
                "expense_config_created",
                config_id=result.get('id'),
                categories_count=len(expense_config.get('monthly_categories_budget', []))
            )
            return result
        else:
            logger.error("expense_config_create_failed", error=result.get('error'))
            return None
    except Exception as e:
        logger.error("expense_config_create_exception", error=str(e))
        return None


async def create_budget_for_month(user_id: str, expense_config: dict, year: int, month: int):
    """为指定月份创建预算记录（新版本：使用扁平category_budgets便于统计）"""
    
    period = f"{year}-{month:02d}"
    budget_date = datetime(year, month, 1, 0, 0, 0)
    
    # 从层级类目中提取预算金额（扁平化，包括二级类目）
    categories_budget = expense_config.get('monthly_categories_budget', [])
    category_budgets = {}
    
    def extract_budgets(categories, parent_name=''):
        """递归提取所有层级的预算"""
        for cat in categories:
            cat_name = cat.get('category_name')
            budget_val = cat.get('budget', -1)
            
            # 一级类目：直接使用名称
            if budget_val != -1:
                category_budgets[cat_name] = budget_val
            
            # 处理二级类目
            sub_categories = cat.get('sub_categories', [])
            if sub_categories:
                for sub_cat in sub_categories:
                    sub_name = sub_cat.get('sub_category_name')
                    sub_budget = sub_cat.get('budget', -1)
                    if sub_budget != -1:
                        # 二级类目：使用 "一级>二级" 格式
                        full_name = f"{cat_name}>{sub_name}"
                        category_budgets[full_name] = sub_budget
    
    extract_budgets(categories_budget)
    
    total_budget = expense_config.get('monthly_budget_total', 0)
    
    # 构建预算内容和数据
    content = f"设置{year}年{month}月预算：总预算{total_budget}元，{len(category_budgets)}个类目有预算限制"
    
    ai_data = {
        "type": "budget",
        "period": period,
        "total_budget": total_budget,
        "category_budgets": category_budgets,  # 扁平结构，便于aggregate统计
        "occurred_at": budget_date.isoformat(),
        "source": "init_script",
        "version": "2.0"
    }
    
    # 检查是否已存在
    existing = await ai_engine._call_mcp_tool(
        'search',
        query="",
        user_id=user_id,
        filters={
            "jsonb_equals": {"type": "budget", "period": period},
            "limit": 1
        }
    )
    
    # 排除 _meta 项
    existing_budgets = [item for item in existing if not item.get('_meta')]
    
    if existing_budgets:
        logger.info(
            "budget_exists",
            period=period,
            budget_id=existing_budgets[0].get('id')
        )
        return existing_budgets[0]
    
    # 创建新预算
    try:
        result = await ai_engine._call_mcp_tool(
            'store',
            content=content,
            ai_data=ai_data,
            user_id=user_id
        )
        
        if result.get('success'):
            logger.info(
                "budget_created",
                period=period,
                budget_id=result.get('id'),
                total=total_budget
            )
            return result
        else:
            logger.error(
                "budget_create_failed",
                period=period,
                error=result.get('error')
            )
            return None
    except Exception as e:
        logger.error(
            "budget_create_exception",
            period=period,
            error=str(e)
        )
        return None


async def initialize_budgets():
    """主函数：初始化预算数据和类目配置"""
    
    logger.info("budget_init_start")
    
    # 1. 加载配置
    config = await load_budget_config()
    if not config:
        logger.error("budget_init_failed", reason="config_load_failed")
        return False
    
    user_id = config['user_id']
    expense_config = config['expense_config']
    
    # 2. 确保 AI 引擎已初始化
    try:
        await ai_engine.initialize_mcp()
        logger.info("ai_engine_initialized")
    except Exception as e:
        logger.warning("ai_engine_init_warning", error=str(e))
    
    # 3. 创建费用类目配置记录（第一步：让AI知道类目体系）
    logger.info("creating_expense_categories_config")
    config_result = await create_expense_categories_config(user_id, expense_config)
    
    if not config_result:
        logger.warning("expense_config_creation_warning")
    else:
        logger.info("expense_config_created_successfully")
    
    # 4. 创建预算记录
    now = datetime.now()
    
    # 当前月
    result_current = await create_budget_for_month(
        user_id,
        expense_config,
        now.year,
        now.month
    )
    
    # 下个月
    next_month = now + timedelta(days=32)
    next_month = next_month.replace(day=1)
    result_next = await create_budget_for_month(
        user_id,
        expense_config,
        next_month.year,
        next_month.month
    )
    
    # 5. 汇总结果
    success = bool(config_result and (result_current or result_next))
    
    if success:
        logger.info(
            "budget_init_complete",
            config_created=config_result is not None,
            current_month=result_current is not None,
            next_month=result_next is not None
        )
    else:
        logger.error("budget_init_failed", reason="incomplete_initialization")
    
    return success


async def verify_budgets(user_id: str):
    """验证预算是否正确创建"""
    
    logger.info("budget_verify_start")
    
    try:
        # 查询所有预算记录
        budgets = await ai_engine._call_mcp_tool(
            'search',
            query="",
            user_id=user_id,
            filters={
                "jsonb_equals": {"type": "budget"},
                "limit": 10
            }
        )
        
        # 排除 _meta 项
        budget_list = [item for item in budgets if not item.get('_meta')]
        
        logger.info(
            "budget_verify_result",
            count=len(budget_list),
            periods=[b.get('ai_understanding', {}).get('period') for b in budget_list]
        )
        
        # 显示详细信息
        for budget in budget_list:
            aiu = budget.get('ai_understanding', {})
            logger.info(
                "budget_detail",
                period=aiu.get('period'),
                total=aiu.get('total_budget'),
                categories=list(aiu.get('category_budgets', {}).keys())
            )
        
        return True
    except Exception as e:
        logger.error("budget_verify_failed", error=str(e))
        return False


async def main():
    """主入口"""
    
    print("=" * 60)
    print("预算数据初始化脚本")
    print("=" * 60)
    print()
    
    try:
        # 初始化预算
        success = await initialize_budgets()
        
        if success:
            print()
            print("✅ 预算初始化成功！")
            print()
            
            # 验证预算
            config = await load_budget_config()
            if config:
                await verify_budgets(config['user_id'])
            
            print()
            print("📋 下一步：")
            print("1. 运行测试脚本：python examples/test_budget.py")
            print("2. 或直接使用：curl -X POST http://localhost:8000/message \\")
            print("   -H 'Content-Type: application/json' \\")
            print("   -d '{\"content\": \"这个月预算还剩多少\", \"user_id\": \"test_user\"}'")
            print()
        else:
            print()
            print("❌ 预算初始化失败，请检查日志")
            print()
            return 1
        
        return 0
        
    except Exception as e:
        logger.error("main_exception", error=str(e))
        print()
        print(f"❌ 发生错误：{e}")
        print()
        return 1
    finally:
        # 清理资源
        await ai_engine.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
