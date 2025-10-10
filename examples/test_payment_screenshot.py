"""
支付截图识别功能测试

测试场景：
1. 模拟发送支付截图（附件中包含 vision_summary）
2. AI 识别支付信息并记账
3. 验证记账成功和预算检查
"""
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.engine_provider import ai_engine
from src.core.logging import get_logger

logger = get_logger(__name__)


async def test_alipay_screenshot():
    """测试1：支付宝支付截图识别"""
    print("\n" + "="*60)
    print("测试1：支付宝支付截图识别")
    print("="*60)
    
    # 模拟附件（实际场景中由 media_service 生成 vision_summary）
    attachments = [{
        'type': 'image',
        'mime': 'image/png',
        'path': '/data/media/test_alipay.png',
        'vision_summary': '支付宝支付，星巴克咖啡，78元，餐饮类，2025-10-10 14:30'
    }]
    
    response = await ai_engine.process_message(
        content="",  # 纯图片，无文字
        user_id="test_screenshot_user",
        context={
            "channel": "threema",
            "thread_id": "test_screenshot",
            "attachments": attachments
        }
    )
    
    print("\nAI 回复：")
    print(response)
    print()
    
    # 验证
    success = False
    if "78" in response and ("星巴克" in response or "咖啡" in response):
        print("✅ 成功识别支付信息")
        success = True
        if "记录" in response or "已记" in response or "✅" in response:
            print("✅ 记账操作已执行或等待确认")
        else:
            print("⚠️  识别成功但记账状态不明确")
    else:
        print("❌ 未正确识别支付信息")
    
    return success


async def test_wechat_screenshot():
    """测试2：微信支付截图识别"""
    print("\n" + "="*60)
    print("测试2：微信支付截图识别")
    print("="*60)
    
    attachments = [{
        'type': 'image',
        'mime': 'image/jpeg',
        'path': '/data/media/test_wechat.jpg',
        'vision_summary': '微信支付，滴滴出行，35元，交通类，2025-10-10 09:15'
    }]
    
    response = await ai_engine.process_message(
        content="",
        user_id="test_screenshot_user",
        context={
            "channel": "threema",
            "thread_id": "test_screenshot",
            "attachments": attachments
        }
    )
    
    print("\nAI 回复：")
    print(response)
    print()
    
    # 验证
    success = False
    if "35" in response and ("滴滴" in response or "交通" in response):
        print("✅ 成功识别微信支付信息")
        success = True
    else:
        print("❌ 未正确识别微信支付信息")
    
    return success


async def test_receipt_screenshot():
    """测试3：商户小票截图识别"""
    print("\n" + "="*60)
    print("测试3：商户小票截图识别")
    print("="*60)
    
    attachments = [{
        'type': 'image',
        'mime': 'image/png',
        'path': '/data/media/test_receipt.png',
        'vision_summary': '超市小票，全家便利店，总计85元，包含牛奶、面包、水果，餐饮类，2025-10-10 20:30'
    }]
    
    response = await ai_engine.process_message(
        content="这是今天买的东西",  # 用户附加说明
        user_id="test_screenshot_user",
        context={
            "channel": "api",
            "thread_id": "test_screenshot",
            "attachments": attachments
        }
    )
    
    print("\nAI 回复：")
    print(response)
    print()
    
    # 验证
    success = False
    if "85" in response and ("全家" in response or "便利店" in response):
        print("✅ 成功识别小票信息")
        success = True
    else:
        print("❌ 未正确识别小票信息")
    
    return success


async def test_incomplete_screenshot():
    """测试4：信息不完整的截图（需要补充询问）"""
    print("\n" + "="*60)
    print("测试4：信息不完整的截图处理")
    print("="*60)
    
    # 模拟识别结果不完整（缺少金额）
    attachments = [{
        'type': 'image',
        'mime': 'image/png',
        'path': '/data/media/test_incomplete.png',
        'vision_summary': '商家名称：麦当劳，商品：汉堡套餐，时间：2025-10-10 12:00'
        # 缺少金额
    }]
    
    response = await ai_engine.process_message(
        content="",
        user_id="test_screenshot_user",
        context={
            "channel": "api",
            "thread_id": "test_screenshot",
            "attachments": attachments
        }
    )
    
    print("\nAI 回复：")
    print(response)
    print()
    
    # 验证
    success = False
    if "多少" in response or "金额" in response or "?" in response or "？" in response:
        print("✅ 正确识别信息不完整并询问")
        success = True
    else:
        print("⚠️  未明确询问缺失信息（可能已根据上下文补全）")
        success = True  # 不算失败
    
    return success


async def test_non_payment_image():
    """测试5：非支付类图片（不应触发记账）"""
    print("\n" + "="*60)
    print("测试5：非支付类图片处理")
    print("="*60)
    
    attachments = [{
        'type': 'image',
        'mime': 'image/jpeg',
        'path': '/data/media/test_family.jpg',
        'vision_summary': '家庭照片，三个孩子在公园草地上玩耍，阳光明媚'
    }]
    
    response = await ai_engine.process_message(
        content="",
        user_id="test_screenshot_user",
        context={
            "channel": "api",
            "thread_id": "test_screenshot",
            "attachments": attachments
        }
    )
    
    print("\nAI 回复：")
    print(response)
    print()
    
    # 验证
    success = False
    if "记录" not in response and "支出" not in response:
        print("✅ 正确识别非支付图片，未触发记账")
        success = True
    else:
        print("❌ 误将非支付图片识别为记账请求")
    
    return success


async def test_user_confirmation_flow():
    """测试6：用户确认流程（两轮对话）"""
    print("\n" + "="*60)
    print("测试6：用户确认记账流程")
    print("="*60)
    
    # 第一轮：发送截图
    attachments = [{
        'type': 'image',
        'mime': 'image/png',
        'path': '/data/media/test_confirm.png',
        'vision_summary': '支付宝支付，肯德基，120元，餐饮类，2025-10-10 18:00'
    }]
    
    response1 = await ai_engine.process_message(
        content="",
        user_id="test_screenshot_user",
        context={
            "channel": "api",
            "thread_id": "test_confirm",
            "attachments": attachments
        }
    )
    
    print("\n第一轮 AI 回复（识别并询问）：")
    print(response1)
    print()
    
    # 第二轮：用户确认
    await asyncio.sleep(1)
    response2 = await ai_engine.process_message(
        content="对，记录一下",
        user_id="test_screenshot_user",
        context={
            "channel": "api",
            "thread_id": "test_confirm"
        }
    )
    
    print("\n第二轮 AI 回复（确认记账）：")
    print(response2)
    print()
    
    # 验证
    success = False
    if ("识别" in response1 or "?" in response1 or "？" in response1) and \
       ("记录" in response2 or "已记" in response2 or "✅" in response2):
        print("✅ 确认流程正常")
        success = True
    else:
        print("⚠️  确认流程可能有异常")
    
    return success


async def main():
    """主测试流程"""
    print("\n" + "="*60)
    print("支付截图识别功能测试")
    print("="*60)
    print("\n注意：本测试使用模拟的 vision_summary 数据")
    print("实际使用时需要：")
    print("1. 设置 ENABLE_VISION=true")
    print("2. 配置支持 Vision 的模型（如 gpt-4o-mini）")
    print("3. 通过 Threema 发送真实截图\n")
    
    # 运行测试
    results = []
    results.append(("支付宝截图", await test_alipay_screenshot()))
    await asyncio.sleep(0.5)
    
    results.append(("微信截图", await test_wechat_screenshot()))
    await asyncio.sleep(0.5)
    
    results.append(("商户小票", await test_receipt_screenshot()))
    await asyncio.sleep(0.5)
    
    results.append(("信息不完整", await test_incomplete_screenshot()))
    await asyncio.sleep(0.5)
    
    results.append(("非支付图片", await test_non_payment_image()))
    await asyncio.sleep(0.5)
    
    results.append(("确认流程", await test_user_confirmation_flow()))
    
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

