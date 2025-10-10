#!/usr/bin/env python3
"""
P1 集成测试 - 图片识别处理

测试用例：TC281 - TC285
优先级：P1（重要功能）

功能覆盖：
- 支付宝截图识别
- 微信支付截图识别
- 小票识别
- 体检报告识别
- 识别失败降级

注意：实际测试需要准备图片文件或模拟OCR/Vision结果
"""

import asyncio
from base import IntegrationTestBase


class TestP1MultimodalImage(IntegrationTestBase):
    """P1 图片识别处理测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p1_image")
    
    async def test_tc281_alipay_screenshot(self):
        """
        TC281: 支付宝截图识别
        
        验证点：
        1. 识别支付宝支付截图
        2. 提取商家名称（星巴克）
        3. 提取金额（78元）
        4. 自动映射类目（星巴克 → 餐饮）
        5. 询问确认后记账
        
        模拟方式：
        - 模拟vision_summary或ocr_text结果
        """
        # 模拟图片识别后的文本
        vision_summary = "支付宝支付截图，显示向星巴克支付了78.00元"
        
        print("\n--- 步骤1：AI识别截图内容 ---")
        await self.run_test(
            test_id="TC281-1",
            test_name="识别支付截图",
            message="[发送支付宝截图]",
            expected_keywords=["星巴克", "78", "是否记录", "确认"],
            context={
                "attachments": [{
                    "type": "image",
                    "vision_summary": vision_summary,
                    "mime": "image/jpeg"
                }]
            }
        )
        
        await asyncio.sleep(0.5)
        
        print("\n--- 步骤2：用户确认记账 ---")
        await self.run_test(
            test_id="TC281",
            test_name="确认记账",
            message="对，记录一下",
            expected_keywords=["记录", "78"]
        )
    
    async def test_tc282_wechat_payment_screenshot(self):
        """
        TC282: 微信支付截图识别
        
        验证点：
        1. 识别微信支付截图
        2. 提取关键信息
        3. 自动记账或询问确认
        """
        vision_summary = "微信支付记录，支付给美团外卖45元"
        
        await self.run_test(
            test_id="TC282",
            test_name="微信支付截图识别",
            message="[发送微信支付截图]",
            expected_keywords=["45", "外卖"],
            context={
                "attachments": [{
                    "type": "image",
                    "vision_summary": vision_summary
                }]
            }
        )
    
    async def test_tc283_receipt_recognition(self):
        """
        TC283: 小票识别
        
        验证点：
        1. 识别超市小票
        2. 提取总金额
        3. 可能提取商品清单
        4. 自动映射类目
        5. 记账成功
        """
        ocr_text = """
        家乐福超市
        购物小票
        ---------------
        牛奶        28.00
        面包        12.00
        水果        35.00
        ---------------
        合计：      75.00元
        """
        
        await self.run_test(
            test_id="TC283",
            test_name="超市小票识别",
            message="[发送超市小票照片]",
            expected_keywords=["75", "超市"],
            context={
                "attachments": [{
                    "type": "image",
                    "ocr_text": ocr_text
                }]
            }
        )
    
    async def test_tc284_health_report_recognition(self):
        """
        TC284: 体检报告识别
        
        验证点：
        1. 识别体检报告图片
        2. 提取健康指标（身高、体重等）
        3. 识别人员信息
        4. 记录健康数据
        """
        vision_summary = "儿童体检报告：姓名-张XX，身高85cm，体重16kg，视力正常"
        
        print("\n--- 识别体检报告 ---")
        await self.run_test(
            test_id="TC284-1",
            test_name="识别体检报告",
            message="[发送孩子体检报告]",
            expected_keywords=["85", "16", "体检"],
            context={
                "attachments": [{
                    "type": "image",
                    "vision_summary": vision_summary
                }]
            }
        )
        
        await asyncio.sleep(0.5)
        
        # 如果AI需要确认人员
        print("\n--- 确认是哪个孩子 ---")
        await self.run_test(
            test_id="TC284",
            test_name="确认人员",
            message="是二女儿的",
            expected_keywords=["记录", "二女儿"]
        )
    
    async def test_tc285_recognition_failure_fallback(self):
        """
        TC285: 识别失败降级
        
        验证点：
        1. 图片模糊或无法识别
        2. AI友好提示识别失败
        3. 请求用户手动输入
        4. 不强制要求图片内容
        """
        await self.run_test(
            test_id="TC285",
            test_name="识别失败降级",
            message="[发送模糊图片]",
            expected_keywords=["无法", "不清楚", "手动", "输入"],
            context={
                "attachments": [{
                    "type": "image",
                    "vision_summary": "图片内容模糊，无法清晰识别"
                }]
            }
        )


async def main():
    """运行P1图片识别处理测试"""
    print("=" * 80)
    print("P1 集成测试 - 图片识别处理")
    print("=" * 80)
    print()
    
    tester = TestP1MultimodalImage()
    
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        await tester.test_tc281_alipay_screenshot()
        await asyncio.sleep(0.5)
        
        await tester.test_tc282_wechat_payment_screenshot()
        await asyncio.sleep(0.5)
        
        await tester.test_tc283_receipt_recognition()
        await asyncio.sleep(0.5)
        
        await tester.test_tc284_health_report_recognition()
        await asyncio.sleep(0.5)
        
        await tester.test_tc285_recognition_failure_fallback()
        
        tester.print_summary()
        return 0
        
    except Exception as e:
        print(f"❌ 测试异常：{e}")
        return 1
        
    finally:
        await tester.teardown()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    import sys
    sys.exit(exit_code)

