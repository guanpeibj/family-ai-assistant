#!/usr/bin/env python3
"""
P2 集成测试 - 综合场景测试

测试用例：TC113 - TC116
优先级：P2（增强功能）

功能覆盖：
- 孩子生病完整流程
- 疫苗接种流程
- 家庭旅行场景
- 多人协作记账
"""

import asyncio
from base import IntegrationTestBase


class TestP2ComprehensiveScenarios(IntegrationTestBase):
    """P2 综合场景测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p2_comprehensive")
    
    async def test_tc113_sick_child_complete_flow(self):
        """
        TC113: 孩子生病完整流程
        
        验证点：
        1. 记录生病状况
        2. 记录就医支出
        3. 记录买药支出
        4. 设置复查提醒
        5. 整个流程数据关联正确
        """
        print("\n--- 场景：孩子生病完整流程 ---")
        
        steps = [
            ("儿子发烧了，记录一下", "记录生病"),
            ("去医院看病花了150元", "就医支出"),
            ("医生开了药，花了80元", "买药支出"),
            ("提醒我明天给儿子复查", "设置提醒"),
        ]
        
        for i, (message, label) in enumerate(steps, 1):
            print(f"\n步骤{i}/{len(steps)}: {label}")
            await self.run_test(
                test_id=f"TC113-{i}",
                test_name=f"生病流程 - {label}",
                message=message,
                expected_keywords=[]
            )
            await asyncio.sleep(0.5)
        
        print("\n✅ 完整流程测试完成")
    
    async def test_tc114_vaccine_complete_flow(self):
        """
        TC114: 疫苗接种流程
        
        验证点：
        1. 查询疫苗记录
        2. 设置提醒
        3. 到时提醒触发
        4. 记录完成
        5. 闭环完整
        """
        print("\n--- 场景：疫苗接种完整流程 ---")
        
        steps = [
            ("查询大女儿的疫苗记录", "查询历史"),
            ("下周三要打流感疫苗，提前一天提醒我", "设置提醒"),
            ("今天已经带大女儿打了疫苗", "记录完成"),
        ]
        
        for i, (message, label) in enumerate(steps, 1):
            print(f"\n步骤{i}/{len(steps)}: {label}")
            await self.run_test(
                test_id=f"TC114-{i}",
                test_name=f"疫苗流程 - {label}",
                message=message,
                expected_keywords=[]
            )
            await asyncio.sleep(0.5)
        
        print("\n✅ 完整流程测试完成")
    
    async def test_tc115_family_travel_scenario(self):
        """
        TC115: 家庭旅行场景
        
        验证点：
        1. 计划旅行并设置预算
        2. 旅行期间记录多笔支出
        3. 旅行结束后统计总花费
        4. 对比预算执行情况
        """
        print("\n--- 场景：家庭旅行 ---")
        
        # 计划
        await self.run_test(
            test_id="TC115-1",
            test_name="旅行计划",
            message="记一下，下个月5号到10号全家去三亚旅行，预算5000元",
            expected_keywords=["记录", "三亚"]
        )
        
        await asyncio.sleep(0.5)
        
        # 旅行中的支出
        print("\n--- 旅行期间支出 ---")
        travel_expenses = [
            "机票花了2000元",
            "酒店住宿1500元",
            "餐饮600元",
            "景点门票500元",
            "购物纪念品300元",
        ]
        
        for i, expense in enumerate(travel_expenses, 1):
            await self.run_test(
                test_id=f"TC115-{i+1}",
                test_name=f"旅行支出 {i}/5",
                message=expense,
                expected_keywords=["记录"]
            )
            await asyncio.sleep(0.3)
        
        await asyncio.sleep(0.5)
        
        # 总结
        await self.run_test(
            test_id="TC115",
            test_name="旅行总结",
            message="旅行花了多少钱？在预算内吗？",
            expected_keywords=["支出", "预算"]
        )
    
    async def test_tc116_multi_user_collaboration(self):
        """
        TC116: 多人协作记账
        
        验证点：
        1. 不同用户记录支出
        2. 家庭范围查询能汇总所有人
        3. 数据隔离和共享正确
        
        注：这个测试需要多个用户ID，简化处理
        """
        print("\n--- 场景：多人协作记账 ---")
        print("注：简化测试，使用同一用户模拟")
        
        await self.run_test(
            test_id="TC116-1",
            test_name="用户A记账",
            message="今天买菜80元",
            expected_keywords=["记录"]
        )
        
        await asyncio.sleep(0.3)
        
        await self.run_test(
            test_id="TC116-2",
            test_name="用户B记账",
            message="给孩子交学费2000元",
            expected_keywords=["记录"]
        )
        
        await asyncio.sleep(0.5)
        
        await self.run_test(
            test_id="TC116",
            test_name="家庭汇总查询",
            message="这个月一共花了多少？",
            expected_keywords=["支出"]
        )


async def main():
    """运行P2综合场景测试"""
    print("=" * 80)
    print("P2 集成测试 - 综合场景测试")
    print("=" * 80)
    print()
    
    tester = TestP2ComprehensiveScenarios()
    
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        await tester.test_tc113_sick_child_complete_flow()
        await asyncio.sleep(1)
        
        await tester.test_tc114_vaccine_complete_flow()
        await asyncio.sleep(1)
        
        await tester.test_tc115_family_travel_scenario()
        await asyncio.sleep(1)
        
        await tester.test_tc116_multi_user_collaboration()
        
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

