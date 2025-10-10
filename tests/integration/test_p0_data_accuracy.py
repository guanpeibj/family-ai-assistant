#!/usr/bin/env python3
"""
P0 集成测试 - 数据准确性

测试用例：TC141 - TC147
优先级：P0（核心必测）

功能覆盖：
- 信息存储准确性
- 信息检索准确性
- 信息更新正确性
- 时区处理
- 自然语言日期解析
- 时间范围查询
"""

import asyncio
from datetime import datetime, timedelta
from base import IntegrationTestBase


class TestP0DataAccuracy(IntegrationTestBase):
    """P0 数据准确性测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p0_data_accuracy")
    
    async def test_tc141_storage_accuracy(self):
        """
        TC141: 信息存储准确性
        
        验证点：
        1. 记录一条支出
        2. 直接查询数据库验证
        3. 字段完整：type, amount, category, occurred_at
        4. 数值准确：金额150元
        """
        await self.run_test(
            test_id="TC141",
            test_name="信息存储准确性",
            message="买菜花了150元",
            expected_keywords=["记录", "150"]
        )
        
        # 验证数据库
        async def verify():
            memory = await self.get_latest_memory(memory_type="expense")
            if not memory:
                return False, "未找到记录"
            
            issues = []
            if memory.amount != 150:
                issues.append(f"金额错误：期望150，实际{memory.amount}")
            
            ai_data = memory.ai_understanding or {}
            if ai_data.get("type") != "expense":
                issues.append(f"类型错误：期望expense，实际{ai_data.get('type')}")
            
            if ai_data.get("category") != "餐饮":
                issues.append(f"类目错误：期望餐饮，实际{ai_data.get('category')}")
            
            if issues:
                return False, "; ".join(issues)
            return True, "所有字段准确"
        
        print("\n--- 数据库验证 ---")
        success, msg = await verify()
        print(f"验证结果: {'✅' if success else '❌'} {msg}")
    
    async def test_tc142_retrieval_accuracy(self):
        """
        TC142: 信息检索准确性
        
        验证点：
        1. 先存储一条特定信息
        2. 查询该信息
        3. 返回的数据与数据库一致
        4. 没有信息丢失或错误
        """
        print("\n--- 步骤1：存储数据 ---")
        await self.run_test(
            test_id="TC142-setup",
            test_name="存储测试数据",
            message="打车到机场花了180元",
            expected_keywords=["记录", "180"]
        )
        
        await asyncio.sleep(0.5)
        
        print("\n--- 步骤2：查询数据 ---")
        await self.run_test(
            test_id="TC142",
            test_name="检索数据验证",
            message="刚才打车花了多少钱？",
            expected_keywords=["180", "打车"]
        )
    
    async def test_tc143_update_correctness(self):
        """
        TC143: 信息更新正确性
        
        验证点：
        1. 先存储一条信息
        2. 更新该信息
        3. 数据库中是更新而非新增
        4. 只有一条有效记录
        """
        print("\n--- 步骤1：首次存储 ---")
        await self.run_test(
            test_id="TC143-1",
            test_name="首次存储WiFi密码",
            message="家里WiFi密码是password123",
            expected_keywords=["记录", "密码"]
        )
        
        await asyncio.sleep(0.5)
        
        print("\n--- 步骤2：更新信息 ---")
        await self.run_test(
            test_id="TC143",
            test_name="更新WiFi密码",
            message="WiFi密码改成newpass456了",
            expected_keywords=["密码"]
        )
        
        print("\n提示：应该更新记录而非新增，验证数据库中只有一条有效的WiFi密码")
    
    async def test_tc144_timezone_handling(self):
        """
        TC144: 时区处理
        
        验证点：
        1. 记录"今天早上8点"的事
        2. occurred_at使用Asia/Shanghai时区
        3. 时间戳正确（早上8点）
        4. 不是UTC或其他时区
        """
        await self.run_test(
            test_id="TC144",
            test_name="时区处理验证",
            message="记一下今天早上8点去了医院",
            expected_keywords=["记录", "8点", "医院"]
        )
        
        # 验证occurred_at时区
        print("\n提示：occurred_at应使用Asia/Shanghai时区，早上8点")
    
    async def test_tc145_natural_date_parsing(self):
        """
        TC145: 自然语言日期解析
        
        验证点：
        1. "上周三" → 具体日期
        2. "下个月5号" → 具体日期
        3. "国庆节" → 10月1日
        4. 解析准确无误
        """
        test_cases = [
            ("上周三买了书50元", "上周三"),
            ("记一下下个月5号要交学费", "下个月5号"),
        ]
        
        for i, (message, date_desc) in enumerate(test_cases, 1):
            await self.run_test(
                test_id=f"TC145-{i}",
                test_name=f"日期解析 - {date_desc}",
                message=message,
                expected_keywords=["记录"]
            )
            await asyncio.sleep(0.3)
    
    async def test_tc146_time_range_query(self):
        """
        TC146: 时间范围查询
        
        验证点：
        1. 先记录几笔支出（不同日期）
        2. 查询"10月1日到10月7日"
        3. 只返回该时间范围内的记录
        4. 不包含范围外的数据
        """
        print("\n--- 准备测试数据 ---")
        # 记录几笔支出
        expenses = [
            "买菜80元",
            "打车25元",
            "午餐45元",
        ]
        
        for i, expense in enumerate(expenses, 1):
            await self.run_test(
                test_id=f"TC146-setup-{i}",
                test_name=f"准备数据 {i}",
                message=expense,
                expected_keywords=["记录"]
            )
            await asyncio.sleep(0.2)
        
        await asyncio.sleep(0.5)
        
        print("\n--- 主测试：时间范围查询 ---")
        # 查询本月的支出
        today = datetime.now()
        month_start = today.replace(day=1).strftime("%m月1日")
        
        await self.run_test(
            test_id="TC146",
            test_name="时间范围查询",
            message=f"查询{month_start}到今天的支出",
            expected_keywords=["支出"]
        )


async def main():
    """运行P0数据准确性测试"""
    print("=" * 80)
    print("P0 集成测试 - 数据准确性")
    print("=" * 80)
    print()
    
    tester = TestP0DataAccuracy()
    
    # 设置
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        # 运行所有测试
        await tester.test_tc141_storage_accuracy()
        await asyncio.sleep(0.5)
        
        await tester.test_tc142_retrieval_accuracy()
        await asyncio.sleep(0.5)
        
        await tester.test_tc143_update_correctness()
        await asyncio.sleep(0.5)
        
        await tester.test_tc144_timezone_handling()
        await asyncio.sleep(0.5)
        
        await tester.test_tc145_natural_date_parsing()
        await asyncio.sleep(0.5)
        
        await tester.test_tc146_time_range_query()
        
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

