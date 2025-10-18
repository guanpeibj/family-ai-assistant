#!/usr/bin/env python3
"""
P0 集成测试 - 基础记账功能 (V2 新框架)

测试用例：TC001 - TC010
优先级：P0（核心必测）

使用新的三层验证系统：
- 数据层：验证数据是否正确存储
- 智能层：AI评估意图理解、信息提取等
- 体验层：AI评估用户体验和人设契合度
"""

import asyncio
from base_new import IntegrationTestBase


class TestP0AccountingV2(IntegrationTestBase):
    """P0 基础记账功能测试 - V2版本"""
    
    def __init__(self):
        super().__init__(test_suite_name="p0_accounting_v2")
    
    async def test_tc001_simple_expense(self):
        """TC001: 简单记账 - 完整信息"""
        await self.run_test(
            test_id="TC001",
            test_name="简单记账-完整信息",
            message="今天买菜花了80元",
            expected_behavior={
                "intent": "记录支出",
                "key_actions": ["存储账目", "识别类目为食材", "记录金额80元"],
                "response_should": "确认记账成功，告知类目和金额"
            },
            data_verification={
                "should_store": True,
                "expected_data": {
                    "type": "expense",
                    "amount": 80.0,
                    "category": "食材",
                    "sub_category": "蔬菜",
                    "occurred_at": "today"
                },
                "tolerance": {
                    "amount": 0
                },
                "required_fields": ["type", "category", "sub_category", "amount"]
            }
        )
    
    async def test_tc002_large_expense(self):
        """TC002: 大额支出记录"""
        await self.run_test(
            test_id="TC002",
            test_name="大额支出记录",
            message="买了台电脑3500元",
            expected_behavior={
                "intent": "记录大额支出",
                "key_actions": ["存储账目", "识别类目", "记录金额"],
                "response_should": "确认记账，可能提示大额"
            },
            data_verification={
                "should_store": True,
                "expected_data": {
                    "type": "expense",
                    "amount": 3500.0,
                    "occurred_at": "today"
                },
                "tolerance": {
                    "amount": 0
                }
            }
        )
    
    async def test_tc003_income_record(self):
        """TC003: 收入记录"""
        await self.run_test(
            test_id="TC003",
            test_name="收入记录",
            message="今天发工资10000元",
            expected_behavior={
                "intent": "记录收入",
                "key_actions": ["存储收入记录", "记录金额"],
                "response_should": "确认收入记录成功"
            },
            data_verification={
                "should_store": True,
                "expected_data": {
                    "type": "income",
                    "amount": 10000.0,
                    "occurred_at": "today"
                }
            }
        )
    
    async def test_tc004_cross_month(self):
        """TC004: 跨月记账"""
        await self.run_test(
            test_id="TC004",
            test_name="跨月记账",
            message="记一下，上个月28号买了礼物200元",
            expected_behavior={
                "intent": "记录历史支出",
                "key_actions": ["存储账目", "正确识别时间为上月28号"],
                "response_should": "确认记录历史账目"
            },
            data_verification={
                "should_store": True,
                "expected_data": {
                    "type": "expense",
                    "amount": 200.0
                }
            }
        )
    
    async def test_tc005_category_mapping_food(self):
        """TC005: 类目映射-外出就餐"""
        await self.run_test(
            test_id="TC005",
            test_name="类目映射-外出就餐",
            message="外卖花了45元",
            expected_behavior={
                "intent": "记录外出就餐支出",
                "key_actions": ["识别为外出就餐类"],
                "response_should": "确认记账"
            },
            data_verification={
                "should_store": True,
                "expected_data": {
                    "type": "expense",
                    "category": "外出就餐",
                    "sub_category": "外卖",
                    "amount": 45.0
                },
                "required_fields": ["type", "category", "sub_category", "amount"]
            }
        )
    
    async def test_tc006_category_mapping_transport(self):
        """TC006: 类目映射-交通"""
        await self.run_test(
            test_id="TC006",
            test_name="类目映射-交通",
            message="打车去医院35元",
            expected_behavior={
                "intent": "记录交通支出",
                "key_actions": ["识别为交通类"],
                "response_should": "确认记账"
            },
            data_verification={
                "should_store": True,
                "expected_data": {
                    "type": "expense",
                    "category": "交通",
                    "sub_category": "打车",
                    "amount": 35.0
                },
                "required_fields": ["type", "category", "sub_category", "amount"]
            }
        )
    
    async def test_tc007_category_mapping_medical(self):
        """TC007: 类目映射-医疗保健"""
        await self.run_test(
            test_id="TC007",
            test_name="类目映射-医疗保健",
            message="买感冒药120元",
            expected_behavior={
                "intent": "记录医疗支出",
                "key_actions": ["识别为医疗保健类"],
                "response_should": "确认记账"
            },
            data_verification={
                "should_store": True,
                "expected_data": {
                    "type": "expense",
                    "category": "医疗保健",
                    "sub_category": "药品",
                    "amount": 120.0
                },
                "required_fields": ["type", "category", "sub_category", "amount"]
            }
        )
    
    async def test_tc008_category_mapping_education(self):
        """TC008: 类目映射-少儿培训"""
        await self.run_test(
            test_id="TC008",
            test_name="类目映射-少儿培训",
            message="孩子钢琴课200元",
            expected_behavior={
                "intent": "记录教育支出",
                "key_actions": ["识别为少儿培训类"],
                "response_should": "确认记账"
            },
            data_verification={
                "should_store": True,
                "expected_data": {
                    "type": "expense",
                    "category": "少儿培训",
                    "amount": 200.0
                }
            }
        )


async def main():
    """运行P0记账功能测试"""
    print("=" * 80)
    print("P0 集成测试 - 基础记账功能 (V2 新框架)")
    print("三层验证：数据层(40分) + 智能层(40分) + 体验层(20分)")
    print("=" * 80)
    print()
    
    tester = TestP0AccountingV2()
    
    # 设置
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        # 运行所有测试
        await tester.test_tc001_simple_expense()
        await tester.test_tc002_large_expense()
        await tester.test_tc003_income_record()
        await tester.test_tc004_cross_month()
        await tester.test_tc005_category_mapping_food()
        await tester.test_tc006_category_mapping_transport()
        await tester.test_tc007_category_mapping_medical()
        await tester.test_tc008_category_mapping_education()
        
        # 打印总结
        summary = tester.print_summary()
        
        # 判断是否通过
        if summary.get("pass_rate", 0) >= 0.8 and summary.get("avg_total_score", 0) >= 70:
            print("\n🎉 测试套件通过！")
            return 0
        else:
            print("\n⚠️  测试套件未达标")
            return 1
        
    except Exception as e:
        print(f"❌ 测试异常：{e}")
        return 1
        
    finally:
        await tester.teardown()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    import sys
    sys.exit(exit_code)
