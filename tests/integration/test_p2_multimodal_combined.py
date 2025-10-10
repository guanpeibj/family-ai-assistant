#!/usr/bin/env python3
"""
P2 集成测试 - 组合输入处理

测试用例：TC068 - TC069
优先级：P2（增强功能）

功能覆盖：
- 图文混合记账
- 语音+图片记账
"""

import asyncio
from base import IntegrationTestBase


class TestP2MultimodalCombined(IntegrationTestBase):
    """P2 组合输入处理测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p2_combined")
    
    async def test_tc068_text_image_accounting(self):
        """
        TC068: 图文混合记账
        
        验证点：
        1. 结合文字描述和图片内容
        2. 文字："给大女儿买了校服"
        3. 图片：支付截图显示160元
        4. AI综合理解并完成记账
        5. 人员、金额、类目都正确
        """
        vision_summary = "支付宝支付截图，金额160.00元"
        
        await self.run_test(
            test_id="TC068",
            test_name="图文混合记账",
            message="给大女儿买了校服",
            expected_keywords=["记录", "160", "大女儿"],
            context={
                "attachments": [{
                    "type": "image",
                    "vision_summary": vision_summary
                }]
            }
        )
    
    async def test_tc069_voice_image_accounting(self):
        """
        TC069: 语音+图片记账
        
        验证点：
        1. 语音说明情况
        2. 图片显示小票
        3. AI综合两种输入
        4. 完成准确记账
        """
        # 模拟语音转写
        transcription = "刚才买的东西"
        
        # 模拟图片OCR
        ocr_text = "超市小票，合计85.00元"
        
        await self.run_test(
            test_id="TC069",
            test_name="语音+图片记账",
            message=transcription,
            expected_keywords=["记录", "85"],
            context={
                "source": "voice",
                "attachments": [{
                    "type": "image",
                    "ocr_text": ocr_text
                }]
            }
        )


async def main():
    """运行P2组合输入处理测试"""
    print("=" * 80)
    print("P2 集成测试 - 组合输入处理")
    print("=" * 80)
    print()
    
    tester = TestP2MultimodalCombined()
    
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        await tester.test_tc068_text_image_accounting()
        await asyncio.sleep(0.5)
        
        await tester.test_tc069_voice_image_accounting()
        
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

