#!/usr/bin/env python3
"""
P1 集成测试 - 语音输入处理

测试用例：TC059 - TC062
优先级：P1（重要功能）

功能覆盖：
- 语音记账（完整信息）
- 语音记账（口语化数字）
- 语音记账（需补充）
- 语音查询

注意：实际测试需要准备音频文件或模拟转写结果
"""

import asyncio
from base import IntegrationTestBase


class TestP1MultimodalVoice(IntegrationTestBase):
    """P1 语音输入处理测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p1_voice")
    
    async def test_tc059_voice_accounting_complete(self):
        """
        TC059: 语音记账 - 完整信息
        
        验证点：
        1. 系统接收语音并转写为文字
        2. AI理解转写后的口语化表达
        3. 正确提取金额（四十五块 → 45元）
        4. 正确识别类目（外卖 → 餐饮）
        5. 成功记账
        
        模拟方式：
        - 实际场景：发送音频文件
        - 测试场景：模拟转写后的文本
        """
        # 模拟语音转写后的文本
        transcribed_text = "今天中午点外卖花了四十五块钱"
        
        await self.run_test(
            test_id="TC059",
            test_name="语音记账 - 完整信息",
            message=transcribed_text,
            expected_keywords=["记录", "45", "外卖"],
            context={"source": "voice", "transcription": transcribed_text}
        )
    
    async def test_tc060_voice_accounting_colloquial_numbers(self):
        """
        TC060: 语音记账 - 口语化数字
        
        验证点：
        1. 识别口语化数字表达
        2. "三块五" → 3.5元
        3. "买菜" → 餐饮类目
        4. 准确记账
        """
        await self.run_test(
            test_id="TC060",
            test_name="语音记账 - 口语化数字",
            message="买菜三块五",
            expected_keywords=["记录"],
            context={"source": "voice"}
        )
        
        # 验证金额
        async def verify():
            memory = await self.get_latest_memory(memory_type="expense")
            if memory and memory.amount == 3.5:
                return True, "金额正确识别为3.5"
            return False, f"金额识别错误：{memory.amount if memory else 'None'}"
        
        print("\n--- 验证口语化数字识别 ---")
        success, msg = await verify()
        print(f"验证结果: {'✅' if success else '❌'} {msg}")
    
    async def test_tc061_voice_accounting_need_supplement(self):
        """
        TC061: 语音记账 - 需补充
        
        验证点：
        1. 识别缺少金额信息
        2. 发起澄清询问
        3. 语气自然友好
        4. 用户补充后完成记账
        """
        print("\n--- 步骤1：发起记账，缺少金额 ---")
        await self.run_test(
            test_id="TC061-1",
            test_name="语音记账 - 缺少金额",
            message="给孩子买了本书",
            expected_keywords=["多少", "金额"],
            context={"source": "voice"}
        )
        
        await asyncio.sleep(0.5)
        
        print("\n--- 步骤2：补充金额和人员 ---")
        await self.run_test(
            test_id="TC061",
            test_name="补充信息 - 完成记账",
            message="五十块钱，给大女儿买的",
            expected_keywords=["记录", "50"],
            context={"source": "voice"}
        )
    
    async def test_tc062_voice_query(self):
        """
        TC062: 语音查询
        
        验证点：
        1. 理解语音查询意图
        2. 正确解析查询条件
        3. 返回准确结果
        4. 响应自然流畅
        """
        # 先记录一些数据
        print("\n--- 准备测试数据 ---")
        await self.run_test(
            test_id="TC062-setup",
            test_name="准备数据",
            message="买菜花了八十元",
            expected_keywords=["记录"],
            context={"source": "voice"}
        )
        
        await asyncio.sleep(0.5)
        
        print("\n--- 主测试：语音查询 ---")
        await self.run_test(
            test_id="TC062",
            test_name="语音查询预算",
            message="这个月预算还剩多少",
            expected_keywords=["预算"],
            context={"source": "voice"}
        )


async def main():
    """运行P1语音输入处理测试"""
    print("=" * 80)
    print("P1 集成测试 - 语音输入处理")
    print("=" * 80)
    print()
    
    tester = TestP1MultimodalVoice()
    
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        await tester.test_tc059_voice_accounting_complete()
        await asyncio.sleep(0.5)
        
        await tester.test_tc060_voice_accounting_colloquial_numbers()
        await asyncio.sleep(0.5)
        
        await tester.test_tc061_voice_accounting_need_supplement()
        await asyncio.sleep(0.5)
        
        await tester.test_tc062_voice_query()
        
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

