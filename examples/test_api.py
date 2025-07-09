"""
简单的API测试示例
"""
import httpx
import asyncio
from datetime import datetime, timedelta


async def test_api():
    """测试FAA API的基本功能"""
    base_url = "http://localhost:8000"
    
    # 测试用户ID（需要在.env中配置）
    user_id = "test_user"
    
    async with httpx.AsyncClient() as client:
        # 1. 健康检查
        print("1. 健康检查...")
        response = await client.get(f"{base_url}/health")
        print(f"健康状态: {response.json()}\n")
        
        # 2. 记录支出
        print("2. 记录支出...")
        response = await client.post(
            f"{base_url}/message",
            json={
                "content": "今天买菜花了58元",
                "user_id": user_id
            }
        )
        print(f"响应: {response.json()['response']}\n")
        
        # 3. 记录收入
        print("3. 记录收入...")
        response = await client.post(
            f"{base_url}/message",
            json={
                "content": "收到工资8000元",
                "user_id": user_id
            }
        )
        print(f"响应: {response.json()['response']}\n")
        
        # 4. 记录健康数据
        print("4. 记录健康数据...")
        response = await client.post(
            f"{base_url}/message",
            json={
                "content": "儿子今天身高92cm，体重15kg",
                "user_id": user_id
            }
        )
        print(f"响应: {response.json()['response']}\n")
        
        # 5. 设置提醒
        print("5. 设置提醒...")
        remind_time = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d 15:00")
        response = await client.post(
            f"{base_url}/message",
            json={
                "content": f"提醒我明天下午3点给大女儿打疫苗",
                "user_id": user_id
            }
        )
        print(f"响应: {response.json()['response']}\n")
        
        # 6. 查询本月支出
        print("6. 查询本月支出...")
        response = await client.post(
            f"{base_url}/message",
            json={
                "content": "这个月花了多少钱？",
                "user_id": user_id
            }
        )
        print(f"响应: {response.json()['response']}\n")
        
        # 7. 查询健康记录
        print("7. 查询健康记录...")
        response = await client.post(
            f"{base_url}/message",
            json={
                "content": "儿子最近的身高体重变化",
                "user_id": user_id
            }
        )
        print(f"响应: {response.json()['response']}\n")


if __name__ == "__main__":
    print("=== Family AI Assistant API 测试 ===\n")
    asyncio.run(test_api()) 