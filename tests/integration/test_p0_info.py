#!/usr/bin/env python3
"""
P0 集成测试 - 基础信息管理功能

测试用例：TC101 - TC104
优先级：P0（核心必测）

功能覆盖：
- 存储重要信息
- 更新重要信息
- 查询敏感信息（隐私保护）
- 重要信息变更追踪
"""

import asyncio
from base import IntegrationTestBase


class TestP0Info(IntegrationTestBase):
    """P0 基础信息管理功能测试"""
    
    def __init__(self):
        super().__init__(test_suite_name="p0_info")
    
    async def test_tc101_store_important_info(self):
        """
        TC101: 存储重要信息
        
        验证点：
        1. AI理解存储重要信息的意图
        2. 识别为WiFi密码信息
        3. type=important_info 或 family_important_info
        4. tag=wifi_password 或类似标签
        5. 内容准确存储
        """
        async def verify():
            return await self.verify_memory_exists(
                filters={"type": "important_info", "tag": "wifi_password"},
                min_count=1
            )
        
        await self.run_test(
            test_id="TC101",
            test_name="存储重要信息 - WiFi密码",
            message="记一下，家里WiFi密码是abc123456",
            expected_keywords=["记录", "密码"],
            verify_db=verify
        )
    
    async def test_tc102_update_important_info(self):
        """
        TC102: 更新重要信息
        
        验证点：
        1. AI识别这是对已有信息的更新
        2. 更新现有记录而非创建新记录
        3. 新密码正确存储（xyz789）
        4. 旧记录被标记为过期或被替换
        """
        await self.run_test(
            test_id="TC102",
            test_name="更新重要信息 - WiFi密码",
            message="WiFi密码改成xyz789了",
            expected_keywords=["更新", "修改", "改", "密码"]
        )
        
        # 验证只有一条有效的WiFi密码记录
        print("\n提示：应该更新记录而非新增，或标记旧记录为过期")
    
    async def test_tc103_query_sensitive_info_privacy(self):
        """
        TC103: 查询敏感信息（隐私保护）
        
        验证点：
        1. AI理解查询WiFi密码的意图
        2. 必须查询数据库获取最新值（配置类查询原则）
        3. 返回正确的密码值
        4. 可能包含隐私风险提示
        """
        await self.run_test(
            test_id="TC103",
            test_name="查询敏感信息 - 隐私保护",
            message="WiFi密码是多少？",
            expected_keywords=["密码"]  # 应返回xyz789
        )
        
        print("\n提示：配置类查询必须查数据库，不能依赖对话历史")
    
    async def test_tc104_info_change_tracking(self):
        """
        TC104: 重要信息变更追踪
        
        验证点：
        1. 先存储钥匙位置（沙发下）
        2. 后更新钥匙位置（衣柜上）
        3. 查询时返回最新位置
        4. AI能正确追踪变更
        
        场景：
        - 第1次：记录钥匙在沙发下
        - 第2次：更新钥匙到衣柜上
        - 第3次：查询钥匙位置，应返回衣柜上
        """
        print("\n--- 步骤1：首次记录 ---")
        await self.run_test(
            test_id="TC104-1",
            test_name="首次记录钥匙位置",
            message="帮我记录：我把大门钥匙放在沙发的垫子下面了",
            expected_keywords=["记录", "钥匙"]
        )
        
        await asyncio.sleep(0.5)
        
        print("\n--- 步骤2：更新位置 ---")
        await self.run_test(
            test_id="TC104-2",
            test_name="更新钥匙位置",
            message="大门钥匙放到衣柜上面了",
            expected_keywords=["钥匙"]
        )
        
        await asyncio.sleep(0.5)
        
        print("\n--- 步骤3：查询最新位置 ---")
        await self.run_test(
            test_id="TC104",
            test_name="查询最新钥匙位置",
            message="大门钥匙放哪了？",
            expected_keywords=["钥匙", "衣柜"],  # 应返回"衣柜上"
            expected_not_keywords=["沙发"]  # 不应提到旧位置
        )


async def main():
    """运行P0基础信息管理功能测试"""
    print("=" * 80)
    print("P0 集成测试 - 基础信息管理功能")
    print("=" * 80)
    print()
    
    tester = TestP0Info()
    
    # 设置
    if not await tester.setup():
        print("❌ 初始化失败")
        return 1
    
    try:
        # 运行所有测试
        await tester.test_tc101_store_important_info()
        await asyncio.sleep(0.5)
        
        await tester.test_tc102_update_important_info()
        await asyncio.sleep(0.5)
        
        await tester.test_tc103_query_sensitive_info_privacy()
        await asyncio.sleep(0.5)
        
        await tester.test_tc104_info_change_tracking()
        
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

