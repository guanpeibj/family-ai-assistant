#!/usr/bin/env python3
"""
P0 集成测试 - 基础健康记录功能

测试用例：TC026 - TC028
优先级：P0（核心必测）

功能覆盖：
- 记录身高
- 记录体重
- 记录体检结果（多指标）
"""

import asyncio
from base import IntegrationTestBase


class TestP0Health(IntegrationTestBase):
    """P0 基础健康记录功能测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p0_health")
    
    async def test_tc026_record_height(self):
        """
        TC026: 记录身高
        
        验证点：
        1. AI理解健康记录意图
        2. 正确提取人员（儿子）
        3. 正确提取指标（身高）和数值（92cm）
        4. occurred_at设置为当前时间
        5. 数据库正确存储
        """
        async def verify():
            return await self.verify_memory_exists(
                filters={"type": "health", "person": "儿子", "metric": "身高"},
                min_count=1
            )
        
        await self.run_test(
            test_id="TC026",
            test_name="记录身高",
            message="儿子今天身高92cm",
            expected_keywords=["记录", "92"],
            verify_db=verify
        )
    
    async def test_tc027_record_weight(self):
        """
        TC027: 记录体重
        
        验证点：
        1. AI理解体重记录意图
        2. 正确提取人员（大女儿）
        3. 正确提取指标（体重）和数值（25kg）
        4. 数据库正确存储
        """
        async def verify():
            return await self.verify_memory_exists(
                filters={"type": "health", "person": "大女儿", "metric": "体重"},
                min_count=1
            )
        
        await self.run_test(
            test_id="TC027",
            test_name="记录体重",
            message="大女儿体重25kg",
            expected_keywords=["记录", "25"],
            verify_db=verify
        )
    
    async def test_tc028_record_checkup_multiple_metrics(self):
        """
        TC028: 记录体检结果（多指标）
        
        验证点：
        1. AI理解体检记录意图
        2. 从一条消息中提取多个健康指标
        3. 人员：二女儿
        4. 指标：身高85cm、体重16kg、视力正常
        5. 可能创建多条记录或一条综合记录
        """
        await self.run_test(
            test_id="TC028",
            test_name="记录体检结果 - 多指标",
            message="今天带二女儿体检，身高85cm，体重16kg，视力正常",
            expected_keywords=["记录", "85", "16"]
        )
        
        # 验证至少记录了身高和体重
        async def verify_height():
            return await self.verify_memory_exists(
                filters={"person": "二女儿", "metric": "身高"},
                min_count=1
            )
        
        async def verify_weight():
            return await self.verify_memory_exists(
                filters={"person": "二女儿", "metric": "体重"},
                min_count=1
            )
        
        print("\n--- 验证多指标记录 ---")
        success_h, msg_h = await verify_height()
        print(f"身高记录: {'✅' if success_h else '❌'} {msg_h}")
        
        success_w, msg_w = await verify_weight()
        print(f"体重记录: {'✅' if success_w else '❌'} {msg_w}")


async def main():
    """运行P0基础健康记录功能测试"""
    print("=" * 80)
    print("P0 集成测试 - 基础健康记录功能")
    print("=" * 80)
    print()
    
    tester = TestP0Health()
    
    # 设置
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        # 运行所有测试
        await tester.test_tc026_record_height()
        await asyncio.sleep(0.5)
        
        await tester.test_tc027_record_weight()
        await asyncio.sleep(0.5)
        
        await tester.test_tc028_record_checkup_multiple_metrics()
        
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

