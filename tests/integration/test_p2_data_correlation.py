#!/usr/bin/env python3
"""
P2 集成测试 - 数据关联性

测试用例：TC421 - TC423
优先级：P2（增强功能）

功能覆盖：
- 家庭成员关联正确性
- 线程隔离正确性
- 共享线程数据访问
"""

import asyncio
from base import IntegrationTestBase


class TestP2DataCorrelation(IntegrationTestBase):
    """P2 数据关联性测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p2_correlation")
    
    async def test_tc421_member_correlation(self):
        """
        TC421: 家庭成员关联正确性
        
        验证点：
        1. 给三个孩子分别记录信息
        2. 每条记录正确关联到对应person
        3. 查询时能正确筛选
        4. 不会混淆不同人员的数据
        """
        print("\n--- 给三个孩子分别记录 ---")
        
        records = [
            ("给大女儿买书120元", "大女儿"),
            ("二女儿钢琴课200元", "二女儿"),
            ("儿子游泳课150元", "儿子"),
        ]
        
        for message, person in records:
            await self.run_test(
                test_id="TC421-setup",
                test_name=f"记录{person}数据",
                message=message,
                expected_keywords=["记录", person]
            )
            await asyncio.sleep(0.3)
        
        await asyncio.sleep(0.5)
        
        print("\n--- 验证：查询特定人员数据 ---")
        await self.run_test(
            test_id="TC421",
            test_name="查询大女儿的支出",
            message="这个月给大女儿花了多少钱？",
            expected_keywords=["大女儿", "120"]
        )
    
    async def test_tc422_thread_isolation(self):
        """
        TC422: 线程隔离正确性
        
        验证点：
        1. 在不同thread_id中记录信息
        2. 查询时只返回当前线程数据
        3. 线程隔离有效
        4. 不会泄露其他线程信息
        """
        print("\n--- 在线程A中记录 ---")
        await self.run_test(
            test_id="TC422-1",
            test_name="线程A记录",
            message="买菜80元",
            expected_keywords=["记录"],
            context={"thread_id": "thread_A"}
        )
        
        await asyncio.sleep(0.3)
        
        print("\n--- 在线程B中记录 ---")
        await self.run_test(
            test_id="TC422-2",
            test_name="线程B记录",
            message="打车50元",
            expected_keywords=["记录"],
            context={"thread_id": "thread_B"}
        )
        
        await asyncio.sleep(0.5)
        
        print("\n--- 验证：在线程A中查询 ---")
        await self.run_test(
            test_id="TC422",
            test_name="线程A查询",
            message="今天花了多少钱？",
            expected_keywords=["80"],  # 应只返回线程A的80元
            expected_not_keywords=["50"],  # 不应包含线程B的50元
            context={"thread_id": "thread_A"}
        )
    
    async def test_tc423_shared_thread_access(self):
        """
        TC423: 共享线程数据访问
        
        验证点：
        1. 在家庭群（shared_thread=true）中记录
        2. 家庭成员都能查询到
        3. 数据正确共享
        4. 统计包含所有家庭成员的数据
        """
        print("\n--- 在家庭群中记录 ---")
        await self.run_test(
            test_id="TC423-1",
            test_name="家庭群记录",
            message="买菜花了150元",
            expected_keywords=["记录"],
            context={"thread_id": "family_group", "shared_thread": True}
        )
        
        await asyncio.sleep(0.5)
        
        print("\n--- 验证：家庭范围查询 ---")
        await self.run_test(
            test_id="TC423",
            test_name="家庭群查询",
            message="家里今天花了多少钱？",
            expected_keywords=["150", "支出"],
            context={"thread_id": "family_group", "shared_thread": True}
        )


async def main():
    """运行P2数据关联性测试"""
    print("=" * 80)
    print("P2 集成测试 - 数据关联性")
    print("=" * 80)
    print()
    
    tester = TestP2DataCorrelation()
    
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        await tester.test_tc421_member_correlation()
        await asyncio.sleep(0.5)
        
        await tester.test_tc422_thread_isolation()
        await asyncio.sleep(0.5)
        
        await tester.test_tc423_shared_thread_access()
        
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

