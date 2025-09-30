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
import os
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ai_engine import ai_engine
import structlog

logger = structlog.get_logger(__name__)


async def load_budget_config():
    """从配置文件加载预算配置"""
    config_file = project_root / "family_private_data.json"
    
    if not config_file.exists():
        logger.error("config_file_not_found", path=str(config_file))
        return None
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        budget_config = config.get('budget', {})
        
        # 查找财务负责人（dad）的user_id
        # 预算应该属于家庭财务负责人，而不是抽象的"family_default"
        user_id = 'dad'  # 默认使用dad
        for member in config.get('family_members', []):
            if member.get('member_key') == 'dad' or member.get('role') == 'father':
                user_id = member.get('user_id', 'dad')
                break
        
        logger.info(
            "config_loaded",
            user_id=user_id,
            monthly_total=budget_config.get('monthly_total'),
            categories=list(budget_config.get('monthly_categories', {}).keys())
        )
        
        return {
            'user_id': user_id,  # 使用dad的user_id而不是username
            'budget': budget_config
        }
    except Exception as e:
        logger.error("config_load_failed", error=str(e))
        return None


async def create_budget_for_month(user_id: str, budget_config: dict, year: int, month: int):
    """为指定月份创建预算记录"""
    
    period = f"{year}-{month:02d}"
    budget_date = datetime(year, month, 1, 0, 0, 0)
    
    # 构建预算内容和数据
    content = f"设置{year}年{month}月预算：总预算{budget_config['monthly_total']}元"
    
    ai_data = {
        "type": "budget",
        "period": period,
        "total_budget": budget_config['monthly_total'],
        "category_budgets": budget_config['monthly_categories'],
        "occurred_at": budget_date.isoformat(),
        "source": "init_script",
        "version": "1.0"
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
                total=budget_config['monthly_total']
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
    """主函数：初始化预算数据"""
    
    logger.info("budget_init_start")
    
    # 1. 加载配置
    config = await load_budget_config()
    if not config:
        logger.error("budget_init_failed", reason="config_load_failed")
        return False
    
    user_id = config['user_id']
    budget_config = config['budget']
    
    # 2. 确保 AI 引擎已初始化
    try:
        await ai_engine.initialize_mcp()
        logger.info("ai_engine_initialized")
    except Exception as e:
        logger.warning("ai_engine_init_warning", error=str(e))
    
    # 3. 创建预算记录
    now = datetime.now()
    
    # 当前月
    result_current = await create_budget_for_month(
        user_id,
        budget_config,
        now.year,
        now.month
    )
    
    # 下个月
    next_month = now + timedelta(days=32)
    next_month = next_month.replace(day=1)
    result_next = await create_budget_for_month(
        user_id,
        budget_config,
        next_month.year,
        next_month.month
    )
    
    # 4. 汇总结果
    success = bool(result_current or result_next)
    
    if success:
        logger.info(
            "budget_init_complete",
            current_month=result_current is not None,
            next_month=result_next is not None
        )
    else:
        logger.error("budget_init_failed", reason="no_budgets_created")
    
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
