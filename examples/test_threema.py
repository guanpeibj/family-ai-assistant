#!/usr/bin/env python3
"""
Threema 集成测试脚本
用于测试 Threema 消息的发送和接收
"""
import asyncio
import httpx
import json
from datetime import datetime
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

API_BASE = os.getenv('API_BASE', 'http://localhost:8000')


async def test_api_health():
    """测试 API 健康状态"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_BASE}/health")
        print(f"Health check: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200


async def test_direct_message():
    """测试直接消息处理"""
    async with httpx.AsyncClient() as client:
        # 测试消息
        data = {
            "content": "今天买菜花了58元",
            "user_id": "00000000-0000-0000-0000-000000000000"  # 测试用户ID
        }
        
        response = await client.post(
            f"{API_BASE}/message",
            json=data
        )
        
        print(f"\n直接消息测试:")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")
        
        return response.status_code == 200


async def test_threema_webhook():
    """模拟 Threema webhook 调用"""
    async with httpx.AsyncClient() as client:
        # 模拟 Threema webhook 数据
        # 注意：这只是模拟，实际的加密数据需要用真实的 Threema 密钥
        webhook_data = {
            "from": "TESTUSER",
            "to": "*GATEWAY",
            "messageId": "0123456789abcdef",
            "date": str(int(datetime.now().timestamp())),
            "nonce": "000102030405060708090a0b0c0d0e0f1011121314151617",
            "box": "48656c6c6f20576f726c64",  # 这是假的加密数据
            "mac": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            "nickname": "测试用户"
        }
        
        response = await client.post(
            f"{API_BASE}/webhook/threema",
            data=webhook_data
        )
        
        print(f"\nThreema webhook 测试:")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")
        
        # 即使处理失败，也应该返回 200（避免 Threema 重试）
        return response.status_code == 200


async def test_reminder():
    """测试提醒功能"""
    async with httpx.AsyncClient() as client:
        # 先创建一个记忆
        data = {
            "content": "下周三给孩子打疫苗",
            "user_id": "00000000-0000-0000-0000-000000000000"
        }
        
        response = await client.post(
            f"{API_BASE}/message",
            json=data
        )
        
        print(f"\n提醒功能测试:")
        print(f"创建提醒: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")
        
        return response.status_code == 200


async def main():
    """运行所有测试"""
    print("=== FAA Threema 集成测试 ===\n")
    
    # 测试列表
    tests = [
        ("API 健康检查", test_api_health),
        ("直接消息处理", test_direct_message),
        ("Threema Webhook", test_threema_webhook),
        ("提醒功能", test_reminder),
    ]
    
    # 运行测试
    results = []
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, "✅ 通过" if result else "❌ 失败"))
        except Exception as e:
            results.append((name, f"❌ 错误: {e}"))
    
    # 打印总结
    print("\n=== 测试总结 ===")
    for name, result in results:
        print(f"{name}: {result}")


if __name__ == "__main__":
    asyncio.run(main()) 