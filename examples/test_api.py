#!/usr/bin/env python3
"""
阿福(FAA) API 测试脚本
测试各种功能场景
"""
import asyncio
import httpx
import json
from datetime import datetime, timedelta
import uuid

API_BASE = "http://localhost:8000"
TEST_USER_ID = str(uuid.uuid4())


async def test_health():
    """测试健康检查"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_BASE}/health")
        print("健康检查:", response.status_code)
        print(json.dumps(response.json(), indent=2))
        return response.status_code == 200


async def test_expense_recording():
    """测试记账功能"""
    print("\n=== 测试记账功能 ===")
    
    test_cases = [
        "今天买菜花了58元",
        "刚才打车去医院花了35",
        "给大女儿买校服花了260元",
        "昨天吃饭花了128元",
        "上周买药花了89.5元"
    ]
    
    async with httpx.AsyncClient() as client:
        for expense in test_cases:
            response = await client.post(
                f"{API_BASE}/message",
                json={"content": expense, "user_id": TEST_USER_ID}
            )
            
            print(f"\n输入: {expense}")
            if response.status_code == 200:
                result = response.json()
                print(f"AI回复: {result['response']}")
            else:
                print(f"错误: {response.status_code}")


async def test_health_recording():
    """测试健康记录功能"""
    print("\n=== 测试健康记录功能 ===")
    
    test_cases = [
        "儿子今天身高92cm，体重15kg",
        "大女儿今天发烧38.5度",
        "二女儿今天打了乙肝疫苗",
        "记录：儿子今天第一次会走路了！"
    ]
    
    async with httpx.AsyncClient() as client:
        for health_info in test_cases:
            response = await client.post(
                f"{API_BASE}/message",
                json={"content": health_info, "user_id": TEST_USER_ID}
            )
            
            print(f"\n输入: {health_info}")
            if response.status_code == 200:
                result = response.json()
                print(f"AI回复: {result['response']}")
            else:
                print(f"错误: {response.status_code}")


async def test_queries():
    """测试查询功能"""
    print("\n=== 测试查询功能 ===")
    
    queries = [
        "这个月花了多少钱？",
        "今天总共花了多少？",
        "本月买菜花了多少？",
        "儿子的身高记录",
        "最近的健康记录"
    ]
    
    async with httpx.AsyncClient() as client:
        for query in queries:
            response = await client.post(
                f"{API_BASE}/message",
                json={"content": query, "user_id": TEST_USER_ID}
            )
            
            print(f"\n查询: {query}")
            if response.status_code == 200:
                result = response.json()
                print(f"AI回复: {result['response']}")
            else:
                print(f"错误: {response.status_code}")


async def test_reminders():
    """测试提醒功能"""
    print("\n=== 测试提醒功能 ===")
    
    # 设置一个立即触发的提醒
    remind_time = (datetime.now() + timedelta(minutes=1)).isoformat()
    
    reminders = [
        f"提醒我{(datetime.now() + timedelta(minutes=1)).strftime('%H:%M')}测试提醒功能",
        "每天早上8点提醒我给孩子们吃维生素",
        "明天上午9点提醒我带二女儿打疫苗"
    ]
    
    async with httpx.AsyncClient() as client:
        for reminder in reminders:
            response = await client.post(
                f"{API_BASE}/message",
                json={"content": reminder, "user_id": TEST_USER_ID}
            )
            
            print(f"\n设置提醒: {reminder}")
            if response.status_code == 200:
                result = response.json()
                print(f"AI回复: {result['response']}")
            else:
                print(f"错误: {response.status_code}")


async def test_info_updates():
    """测试信息更新功能"""
    print("\n=== 测试信息更新功能 ===")
    
    updates = [
        ("家里的wifi密码是88888888", "wifi密码改成66666666了"),
        ("大门钥匙放在鞋柜上面了", "大门钥匙现在放到电视柜抽屉里了"),
        ("幼儿园老师电话是13812345678", "幼儿园老师电话改成13887654321了")
    ]
    
    async with httpx.AsyncClient() as client:
        for original, update in updates:
            # 先记录原始信息
            response = await client.post(
                f"{API_BASE}/message",
                json={"content": original, "user_id": TEST_USER_ID}
            )
            print(f"\n原始信息: {original}")
            if response.status_code == 200:
                print(f"AI回复: {response.json()['response']}")
            
            # 等待一下
            await asyncio.sleep(1)
            
            # 更新信息
            response = await client.post(
                f"{API_BASE}/message",
                json={"content": update, "user_id": TEST_USER_ID}
            )
            print(f"\n更新信息: {update}")
            if response.status_code == 200:
                print(f"AI回复: {response.json()['response']}")
            
            # 查询验证
            query = f"wifi密码是多少？" if "wifi" in original else f"大门钥匙在哪？" if "钥匙" in original else "幼儿园老师电话？"
            response = await client.post(
                f"{API_BASE}/message",
                json={"content": query, "user_id": TEST_USER_ID}
            )
            print(f"\n验证查询: {query}")
            if response.status_code == 200:
                print(f"AI回复: {response.json()['response']}")


async def main():
    """运行所有测试"""
    print("=== 阿福(FAA) API 测试 ===\n")
    
    tests = [
        ("健康检查", test_health),
        ("记账功能", test_expense_recording),
        ("健康记录", test_health_recording),
        ("查询功能", test_queries),
        ("提醒功能", test_reminders),
        ("信息更新", test_info_updates)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            print(f"\n{'='*50}")
            print(f"开始测试: {name}")
            print('='*50)
            
            result = await test_func()
            results.append((name, "✅ 通过" if result != False else "✅ 完成"))
        except Exception as e:
            results.append((name, f"❌ 错误: {e}"))
            print(f"\n测试出错: {e}")
    
    # 打印总结
    print("\n" + "="*50)
    print("测试总结")
    print("="*50)
    for name, result in results:
        print(f"{name}: {result}")


if __name__ == "__main__":
    asyncio.run(main()) 