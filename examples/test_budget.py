#!/usr/bin/env python3
"""
预算功能测试脚本

测试场景：
1. 预算查询
2. 记账并触发预算检查
3. 类目映射测试
4. 预算修改
5. 支出统计和分析
6. 月度报告生成

使用方法：
    python examples/test_budget.py
"""
import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ai_engine import ai_engine
import structlog

logger = structlog.get_logger(__name__)


class BudgetTester:
    """预算功能测试类"""
    
    def __init__(self, user_id: str = "test_user"):
        self.user_id = user_id
        self.test_results = []
    
    async def setup(self):
        """初始化设置"""
        logger.info("test_setup_start")
        
        try:
            # AIEngineV2 在 __init__ 时已完成初始化
            logger.info("test_setup_complete")
            return True
        except Exception as e:
            logger.error("test_setup_failed", error=str(e))
            return False
    
    async def run_test(self, test_name: str, message: str, expected_keywords: list = None):
        """运行单个测试"""
        
        print()
        print("=" * 60)
        print(f"测试：{test_name}")
        print("=" * 60)
        print(f"输入：{message}")
        print()
        
        try:
            start_time = datetime.now()
            
            # 调用 AI 引擎
            response = await ai_engine.process_message(
                content=message,
                user_id=self.user_id,
                context={"channel": "api", "thread_id": "test_budget"}
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            print("AI 回复：")
            print(response)
            print()
            print(f"耗时：{duration:.2f}秒")
            
            # 验证关键词
            success = True
            if expected_keywords:
                missing = []
                for keyword in expected_keywords:
                    if keyword.lower() not in response.lower():
                        missing.append(keyword)
                        success = False
                
                if missing:
                    print(f"⚠️ 缺少关键词：{', '.join(missing)}")
            
            # 记录结果
            self.test_results.append({
                "test": test_name,
                "success": success,
                "duration": duration,
                "response_length": len(response)
            })
            
            if success:
                print("✅ 测试通过")
            else:
                print("❌ 测试未完全通过（可能是预期的）")
            
            return response
            
        except Exception as e:
            logger.error("test_failed", test=test_name, error=str(e))
            print(f"❌ 测试失败：{e}")
            
            self.test_results.append({
                "test": test_name,
                "success": False,
                "error": str(e)
            })
            
            return None
    
    async def test_1_query_budget(self):
        """测试1：查询预算"""
        return await self.run_test(
            "查询预算",
            "这个月预算还剩多少？",
            expected_keywords=["预算", "支出"]
        )
    
    async def test_2_record_expense_food(self):
        """测试2：记录餐饮支出（测试类目映射）"""
        return await self.run_test(
            "记账 - 餐饮类",
            "今天买菜花了280元",
            expected_keywords=["记录", "280"]
        )
    
    async def test_3_record_expense_transport(self):
        """测试3：记录交通支出"""
        return await self.run_test(
            "记账 - 交通类",
            "打车去医院，花了35块",
            expected_keywords=["记录", "35"]
        )
    
    async def test_4_record_expense_medical(self):
        """测试4：记录医疗支出"""
        return await self.run_test(
            "记账 - 医疗类",
            "给孩子买感冒药120元",
            expected_keywords=["记录", "120"]
        )
    
    async def test_5_record_large_expense(self):
        """测试5：记录大额支出（触发提醒）"""
        return await self.run_test(
            "大额支出",
            "买了台电脑，3500元",
            expected_keywords=["记录", "3500"]
        )
    
    async def test_6_category_summary(self):
        """测试6：分类统计"""
        return await self.run_test(
            "分类统计",
            "这个月各类支出分别是多少？",
            expected_keywords=["支出"]
        )
    
    async def test_7_modify_budget(self):
        """测试7：修改预算"""
        return await self.run_test(
            "修改预算",
            "下个月预算调整为12000元",
            expected_keywords=["预算", "12000"]
        )
    
    async def test_8_category_budget_adjust(self):
        """测试8：调整类目预算"""
        return await self.run_test(
            "调整类目预算",
            "餐饮预算调到3500元",
            expected_keywords=["餐饮", "3500"]
        )
    
    async def test_9_expense_trend(self):
        """测试9：支出趋势分析"""
        return await self.run_test(
            "趋势分析",
            "本月支出有什么异常吗？",
            expected_keywords=[]  # AI 自由发挥
        )
    
    async def test_10_multiple_expenses(self):
        """测试10：连续记账测试预算提醒"""
        
        print()
        print("=" * 60)
        print("测试：连续记账（模拟预算消耗）")
        print("=" * 60)
        
        expenses = [
            ("买菜花了150元", "餐饮"),
            ("外卖80元", "餐饮"),
            ("孩子钢琴课200元", "教育"),
            ("电影票100元", "娱乐"),
            ("加油300元", "交通"),
        ]
        
        for expense, category in expenses:
            response = await self.run_test(
                f"记账 - {category}",
                expense,
                expected_keywords=["记录"]
            )
            await asyncio.sleep(0.5)  # 稍微延迟避免太快
        
        return response
    
    async def print_summary(self):
        """打印测试总结"""
        
        print()
        print("=" * 60)
        print("测试总结")
        print("=" * 60)
        
        total = len(self.test_results)
        passed = sum(1 for r in self.test_results if r.get('success'))
        failed = total - passed
        
        print(f"总测试数：{total}")
        print(f"✅ 通过：{passed}")
        print(f"❌ 失败：{failed}")
        
        if self.test_results:
            avg_duration = sum(r.get('duration', 0) for r in self.test_results) / total
            print(f"平均耗时：{avg_duration:.2f}秒")
        
        print()
        
        # 详细结果
        print("详细结果：")
        for i, result in enumerate(self.test_results, 1):
            status = "✅" if result.get('success') else "❌"
            duration = result.get('duration', 0)
            test_name = result.get('test', 'Unknown')
            print(f"{i}. {status} {test_name} ({duration:.2f}s)")
            if 'error' in result:
                print(f"   错误：{result['error']}")
        
        print()


async def main():
    """主测试流程"""
    
    print()
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 15 + "预算功能测试脚本" + " " * 27 + "║")
    print("╚" + "═" * 58 + "╝")
    print()
    
    tester = BudgetTester(user_id="test_user")
    
    # 设置
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        # 运行所有测试
        print("开始执行测试...")
        print()
        
        # 基础测试
        await tester.test_1_query_budget()
        await tester.test_2_record_expense_food()
        await tester.test_3_record_expense_transport()
        await tester.test_4_record_expense_medical()
        await tester.test_5_record_large_expense()
        await tester.test_6_category_summary()
        
        # 预算管理测试
        await tester.test_7_modify_budget()
        await tester.test_8_category_budget_adjust()
        
        # 分析测试
        await tester.test_9_expense_trend()
        
        # 综合测试
        await tester.test_10_multiple_expenses()
        
        # 打印总结
        await tester.print_summary()
        
        print("✅ 测试完成！")
        print()
        print("📝 注意事项：")
        print("1. 某些测试可能因为数据不足而无法完全验证")
        print("2. AI的回复可能会根据上下文有所不同")
        print("3. 建议查看AI回复内容，验证逻辑是否正确")
        print()
        
        return 0
        
    except Exception as e:
        logger.error("test_main_exception", error=str(e))
        print(f"❌ 测试异常：{e}")
        return 1
    finally:
        # AIEngineV2 不需要显式关闭
        pass


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
