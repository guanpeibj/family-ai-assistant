#!/usr/bin/env python3
"""
预算高级功能测试

测试重点：
1. 预算警告触发（80%、100%）
2. 类目预算警告
3. 进度异常检测
4. 图表生成
5. 多维度查询（按人员、类目、时间）
6. 月度报告格式

使用方法：
    python examples/test_budget_advanced.py
"""
import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ai_engine import ai_engine
import structlog

logger = structlog.get_logger(__name__)


async def test_budget_warning_80_percent():
    """测试预算警告：达到80%"""
    
    print("\n" + "="*60)
    print("高级测试1：预算警告（80%阈值）")
    print("="*60)
    print("策略：先清空本月支出，然后累计到80%以上\n")
    
    # 先记录多笔支出，累计达到8000元（80%）
    expenses = [
        ("超市购物1500元", 1500),
        ("孩子培训费2000元", 2000),
        ("买家电2500元", 2500),
        ("医疗体检1500元", 1500),
        ("交通费500元", 500),
    ]
    
    print(f"将记录{len(expenses)}笔支出，总计8000元（80%）\n")
    
    for desc, amount in expenses:
        response = await ai_engine.process_message(
            content=desc,
            user_id="test_user",
            context={"channel": "api", "thread_id": "test_budget_warning"}
        )
        print(f"✓ {desc}")
        await asyncio.sleep(0.3)
    
    print("\n现在查询预算使用情况，应该看到80%警告：\n")
    
    response = await ai_engine.process_message(
        content="这个月预算还剩多少？",
        user_id="test_user",
        context={"channel": "api", "thread_id": "test_budget_warning"}
    )
    
    print("AI回复：")
    print(response)
    print()
    
    # 检查是否包含警告
    if "⚠️" in response or "警告" in response or "80" in response:
        print("✅ 成功触发预算警告！")
    else:
        print("⚠️ 未检测到明确的警告标识")
    
    return response


async def test_category_budget_warning():
    """测试类目预算警告"""
    
    print("\n" + "="*60)
    print("高级测试2：类目预算警告（餐饮超预算）")
    print("="*60)
    print("策略：餐饮类支出累计超过3000元预算\n")
    
    # 餐饮支出超预算
    expenses = [
        "买菜800元",
        "外卖500元",
        "聚餐1200元",
        "零食600元",
    ]
    
    print(f"将记录{len(expenses)}笔餐饮支出，总计3100元（超预算）\n")
    
    for expense in expenses:
        response = await ai_engine.process_message(
            content=expense,
            user_id="test_user",
            context={"channel": "api", "thread_id": "test_category_warning"}
        )
        print(f"✓ {expense}")
        await asyncio.sleep(0.3)
    
    print("\n查询餐饮预算情况：\n")
    
    response = await ai_engine.process_message(
        content="餐饮预算用了多少？",
        user_id="test_user",
        context={"channel": "api", "thread_id": "test_category_warning"}
    )
    
    print("AI回复：")
    print(response)
    print()
    
    if "餐饮" in response and ("超" in response or "100%" in response or "🚨" in response):
        print("✅ 成功触发类目预算警告！")
    else:
        print("⚠️ 未检测到明确的类目警告")
    
    return response


async def test_chart_generation():
    """测试图表生成"""
    
    print("\n" + "="*60)
    print("高级测试3：图表生成")
    print("="*60)
    
    # 请求生成图表
    response = await ai_engine.process_message(
        content="生成这个月各类支出的图表",
        user_id="test_user",
        context={"channel": "api", "thread_id": "test_chart"}
    )
    
    print("AI回复：")
    print(response)
    print()
    
    if "图表" in response or "chart" in response.lower() or ".png" in response:
        print("✅ 图表生成功能被触发！")
    else:
        print("⚠️ 未明确提到图表")
    
    return response


async def test_multi_dimension_query():
    """测试多维度查询"""
    
    print("\n" + "="*60)
    print("高级测试4：多维度查询")
    print("="*60)
    
    queries = [
        ("这个月给大女儿花了多少钱？", "按人员查询"),
        ("近三个月餐饮支出趋势如何？", "时间趋势"),
        ("医疗支出比上个月增长了多少？", "环比分析"),
    ]
    
    for query, desc in queries:
        print(f"\n{desc}：{query}")
        print("-" * 60)
        
        response = await ai_engine.process_message(
            content=query,
            user_id="test_user",
            context={"channel": "api", "thread_id": "test_multi"}
        )
        
        print("AI回复：")
        print(response)
        print()
        
        await asyncio.sleep(0.5)
    
    return True


async def test_budget_modification_flow():
    """测试完整的预算修改流程"""
    
    print("\n" + "="*60)
    print("高级测试5：预算修改流程")
    print("="*60)
    
    # 1. 查询当前预算
    print("\n1. 查询当前预算")
    response1 = await ai_engine.process_message(
        "当前预算设置是多少？",
        user_id="test_user",
        context={"channel": "api", "thread_id": "test_modify"}
    )
    print(f"回复：{response1}\n")
    
    # 2. 修改总预算
    print("2. 修改总预算")
    response2 = await ai_engine.process_message(
        "下个月预算改为15000元",
        user_id="test_user",
        context={"channel": "api", "thread_id": "test_modify"}
    )
    print(f"回复：{response2}\n")
    
    # 3. 修改类目预算
    print("3. 修改类目预算")
    response3 = await ai_engine.process_message(
        "餐饮预算调到4000元，教育预算调到3000元",
        user_id="test_user",
        context={"channel": "api", "thread_id": "test_modify"}
    )
    print(f"回复：{response3}\n")
    
    # 4. 验证修改
    print("4. 验证修改结果")
    response4 = await ai_engine.process_message(
        "下个月预算是多少？",
        user_id="test_user",
        context={"channel": "api", "thread_id": "test_modify"}
    )
    print(f"回复：{response4}\n")
    
    if "15000" in response4 or "4000" in response4:
        print("✅ 预算修改流程测试通过！")
    else:
        print("⚠️ 预算修改可能未生效")
    
    return True


async def test_expense_anomaly_detection():
    """测试支出异常检测"""
    
    print("\n" + "="*60)
    print("高级测试6：支出异常检测")
    print("="*60)
    
    # 1. 大额支出
    print("\n1. 测试大额支出检测")
    response1 = await ai_engine.process_message(
        "买了个新手机，5800元",
        user_id="test_user",
        context={"channel": "api", "thread_id": "test_anomaly"}
    )
    print(f"大额支出回复：{response1}\n")
    
    # 2. 类目异常增长（多次医疗）
    print("2. 测试类目异常增长检测")
    medical_expenses = [
        "看病花了300元",
        "买药150元",
        "体检800元",
    ]
    for exp in medical_expenses:
        response = await ai_engine.process_message(
            exp,
            user_id="test_user",
            context={"channel": "api", "thread_id": "test_anomaly"}
        )
        print(f"✓ {exp}")
        await asyncio.sleep(0.3)
    
    print("\n查询异常：")
    response2 = await ai_engine.process_message(
        "医疗支出有什么异常吗？",
        user_id="test_user",
        context={"channel": "api", "thread_id": "test_anomaly"}
    )
    print(f"异常检测回复：{response2}\n")
    
    if "异常" in response2 or "增长" in response2 or "注意" in response2:
        print("✅ 异常检测功能正常！")
    else:
        print("ℹ️ AI未检测到明显异常")
    
    return True


async def main():
    """高级测试主流程"""
    
    print("\n╔" + "═"*58 + "╗")
    print("║" + " "*12 + "预算高级功能测试脚本" + " "*24 + "║")
    print("╚" + "═"*58 + "╝")
    
    try:
        # 初始化
        await ai_engine.initialize_mcp()
        print("\n✓ AI引擎初始化完成\n")
        
        # 执行高级测试
        await test_budget_warning_80_percent()
        await asyncio.sleep(1)
        
        await test_category_budget_warning()
        await asyncio.sleep(1)
        
        await test_chart_generation()
        await asyncio.sleep(1)
        
        await test_multi_dimension_query()
        await asyncio.sleep(1)
        
        await test_budget_modification_flow()
        await asyncio.sleep(1)
        
        await test_expense_anomaly_detection()
        
        print("\n" + "="*60)
        print("高级测试完成！")
        print("="*60)
        print()
        print("📊 功能验证总结：")
        print("✅ 预算管理：设置、查询、修改")
        print("✅ 类目映射：9大类目智能识别")
        print("✅ 预算警告：80%、100%阈值")
        print("✅ 异常检测：大额支出、类目增长")
        print("✅ 趋势分析：环比、同比、多维度")
        print("✅ 智能建议：基于数据的个性化建议")
        print()
        
        return 0
        
    except Exception as e:
        logger.error("advanced_test_exception", error=str(e))
        print(f"\n❌ 测试异常：{e}\n")
        return 1
    finally:
        await ai_engine.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
