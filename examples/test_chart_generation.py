"""
图表生成功能测试

测试场景：
1. API 渠道生成图表（返回路径和链接）
2. Threema 渠道生成图表（返回签名链接）
3. 不同图表类型（饼图、柱状图、折线图）
"""
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.engine_provider import ai_engine
from src.core.logging import get_logger

logger = get_logger(__name__)


async def setup_test_data():
    """准备测试数据：创建一些支出记录"""
    print("\n" + "="*60)
    print("准备测试数据")
    print("="*60)
    
    test_expenses = [
        "买菜85元",
        "打车35元",
        "给大女儿买书120元",
        "看电影80元",
        "买衣服280元",
        "水电费200元"
    ]
    
    for expense in test_expenses:
        await ai_engine.process_message(
            content=expense,
            user_id="test_chart_user",
            context={"channel": "api", "thread_id": "test_chart"}
        )
        await asyncio.sleep(0.5)
    
    print("✅ 测试数据准备完成\n")


async def test_chart_pie_api():
    """测试1：API 渠道 - 饼图（类目占比）"""
    print("\n" + "="*60)
    print("测试1：API 渠道 - 生成本月支出类目占比饼图")
    print("="*60)
    
    response = await ai_engine.process_message(
        content="生成本月各类支出占比的饼图",
        user_id="test_chart_user",
        context={"channel": "api", "thread_id": "test_chart"}
    )
    
    print("\nAI 回复：")
    print(response)
    print()
    
    # 验证
    success = False
    if "chart_" in response.lower() or "图表" in response:
        print("✅ 图表生成成功")
        success = True
        if "/media/get" in response or "path" in response.lower():
            print("✅ 包含访问路径信息")
        else:
            print("⚠️  未明确提供访问路径")
    else:
        print("❌ 图表未生成或未在回复中提及")
    
    return success


async def test_chart_bar_threema():
    """测试2：Threema 渠道 - 柱状图（类目对比）"""
    print("\n" + "="*60)
    print("测试2：Threema 渠道 - 生成本月各类支出对比柱状图")
    print("="*60)
    
    response = await ai_engine.process_message(
        content="给我看看本月各类支出对比图",
        user_id="test_chart_user",
        context={"channel": "threema", "thread_id": "test_chart"}
    )
    
    print("\nAI 回复：")
    print(response)
    print()
    
    # 验证
    success = False
    if "chart_" in response.lower() or "图表" in response:
        print("✅ 图表生成成功")
        success = True
        if "sig=" in response and "exp=" in response:
            print("✅ 包含签名链接（适合 Threema）")
        elif "/media/get" in response:
            print("⚠️  包含链接但可能未签名")
        else:
            print("⚠️  未提供可点击链接")
    else:
        print("❌ 图表未生成或未在回复中提及")
    
    return success


async def test_chart_line_trend():
    """测试3：折线图（时间趋势 - 如果有多月数据）"""
    print("\n" + "="*60)
    print("测试3：生成支出趋势折线图")
    print("="*60)
    
    response = await ai_engine.process_message(
        content="画一个本月支出趋势图",
        user_id="test_chart_user",
        context={"channel": "api", "thread_id": "test_chart"}
    )
    
    print("\nAI 回复：")
    print(response)
    print()
    
    # 验证
    if "chart_" in response.lower() or "图表" in response or "趋势" in response:
        print("✅ 趋势分析响应正常")
        return True
    else:
        print("⚠️  可能因数据不足未生成趋势图（正常）")
        return False


async def test_chart_fallback():
    """测试4：图表降级 - 数据不足时的文字描述"""
    print("\n" + "="*60)
    print("测试4：数据不足时的降级处理")
    print("="*60)
    
    response = await ai_engine.process_message(
        content="生成去年全年支出图表",
        user_id="test_chart_user_new",  # 新用户无历史数据
        context={"channel": "api", "thread_id": "test_fallback"}
    )
    
    print("\nAI 回复：")
    print(response)
    print()
    
    # 验证
    if "没有" in response or "无" in response or "不足" in response:
        print("✅ 正确识别数据不足并给出说明")
        return True
    else:
        print("⚠️  回复未明确说明数据情况")
        return False


async def main():
    """主测试流程"""
    print("\n" + "="*60)
    print("图表生成功能测试")
    print("="*60)
    
    # 准备测试数据
    await setup_test_data()
    
    # 运行测试
    results = []
    results.append(("API渠道饼图", await test_chart_pie_api()))
    await asyncio.sleep(1)
    
    results.append(("Threema渠道柱状图", await test_chart_bar_threema()))
    await asyncio.sleep(1)
    
    results.append(("趋势折线图", await test_chart_line_trend()))
    await asyncio.sleep(1)
    
    results.append(("降级处理", await test_chart_fallback()))
    
    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{status} - {name}")
    
    print(f"\n通过率：{passed}/{total} ({passed*100//total}%)")
    
    if passed == total:
        print("\n🎉 所有测试通过！")
    elif passed >= total * 0.75:
        print("\n⚠️  大部分测试通过，少数功能需要调整")
    else:
        print("\n❌ 测试失败较多，需要检查配置")
    
    return passed == total


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n测试出错：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

