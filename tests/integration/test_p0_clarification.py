#!/usr/bin/env python3
"""
P0 集成测试 - 澄清功能

测试用例：TC121 - TC124
优先级：P0（核心必测）

功能覆盖：
- 多字段缺失的逐步澄清
- 提供候选项引导
- 多轮对话上下文理解
- 澄清后的完整执行验证
"""

import asyncio
from base import IntegrationTestBase


class TestP0Clarification(IntegrationTestBase):
    """P0 澄清功能测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p0_clarification")
    
    async def test_tc121_multi_field_clarification(self):
        """
        TC121: 多字段缺失澄清
        
        验证点：
        1. 识别缺少类别和金额
        2. 一次只问一个问题（不要一次问多个）
        3. 逐步引导用户补充信息
        
注：完整的多轮对话在TC124中测试
        """
        await self.run_test(
            test_id="TC121",
            test_name="多字段缺失澄清",
            message="记账：买了东西",
            expected_keywords=["什么", "多少", "金额"]  # 应该询问具体内容或金额
        )
    
    async def test_tc122_provide_options(self):
        """
        TC122: 提供候选项引导
        
        验证点：
        1. 识别"孩子"但未指定具体人员
        2. 列出家庭成员供选择
        3. 可能使用列表或编号格式
        4. 便于用户快速选择
        """
        await self.run_test(
            test_id="TC122",
            test_name="提供候选项引导",
            message="给孩子买了衣服100元",
            expected_keywords=["哪个", "孩子"]  # 可能列出：大女儿、二女儿、儿子
        )
    
    async def test_tc123_multi_turn_context(self):
        """
        TC123: 多轮对话上下文理解
        
        验证点：
        1. AI记住前面对话的主题
        2. 理解"餐饮呢"指的是餐饮支出
        3. 理解"比上个月"继续前面的对比话题
        4. 保持对话连贯性
        """
        print("\n--- 轮1：查询总支出 ---")
        await self.run_test(
            test_id="TC123-1",
            test_name="多轮对话 - 第1轮",
            message="这个月花了多少钱？",
            expected_keywords=["支出"]
        )
        
        await asyncio.sleep(0.5)
        
        print("\n--- 轮2：继续问餐饮 ---")
        await self.run_test(
            test_id="TC123-2",
            test_name="多轮对话 - 第2轮",
            message="餐饮呢？",
            expected_keywords=["餐饮"]  # 应理解指餐饮支出
        )
        
        await asyncio.sleep(0.5)
        
        print("\n--- 轮3：继续对比 ---")
        await self.run_test(
            test_id="TC123",
            test_name="多轮对话 - 第3轮",
            message="比上个月多还是少？",
            expected_keywords=["餐饮", "上个月"]  # 应理解是对比餐饮支出
        )
    
    async def test_tc124_clarification_execution(self):
        """
        TC124: 澄清后的执行验证
        
        验证点：
        1. 第1轮：缺少信息，发起澄清
        2. 第2轮：补充金额，继续澄清
        3. 第3轮：补充人员，完整执行
        4. 最终数据正确存储
        
        完整流程测试
        """
        print("\n--- 轮1：发起记账，缺少金额和人员 ---")
        await self.run_test(
            test_id="TC124-1",
            test_name="澄清流程 - 第1轮（发起）",
            message="记账：买了书",
            expected_keywords=["多少", "金额"]  # 应询问金额
        )
        
        await asyncio.sleep(0.5)
        
        print("\n--- 轮2：补充金额，仍缺人员 ---")
        await self.run_test(
            test_id="TC124-2",
            test_name="澄清流程 - 第2轮（补充金额）",
            message="50元",
            expected_keywords=["谁", "给谁"]  # 应询问给谁买的
        )
        
        await asyncio.sleep(0.5)
        
        print("\n--- 轮3：补充人员，完整执行 ---")
        await self.run_test(
            test_id="TC124",
            test_name="澄清流程 - 第3轮（完成）",
            message="大女儿",
            expected_keywords=["记录", "50"]  # 应确认记录成功
        )
        
        # 验证最终数据
        async def verify():
            return await self.verify_memory_exists(
                filters={"type": "expense", "person": "大女儿", "category": "教育"},
                min_count=1
            )
        
        print("\n--- 验证最终数据 ---")
        success, msg = await verify()
        print(f"数据验证: {'✅' if success else '❌'} {msg}")


async def main():
    """运行P0澄清功能测试"""
    print("=" * 80)
    print("P0 集成测试 - 澄清功能")
    print("=" * 80)
    print()
    
    tester = TestP0Clarification()
    
    # 设置
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        # 运行所有测试
        await tester.test_tc121_multi_field_clarification()
        await asyncio.sleep(0.5)
        
        await tester.test_tc122_provide_options()
        await asyncio.sleep(0.5)
        
        await tester.test_tc123_multi_turn_context()
        await asyncio.sleep(0.5)
        
        await tester.test_tc124_clarification_execution()
        
        # 打印总结
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

