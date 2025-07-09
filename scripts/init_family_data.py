#!/usr/bin/env python3
"""
初始化家庭基本信息脚本
在系统首次使用时运行，预设一些基本的家庭信息
"""
import asyncio
import httpx
import os
from datetime import datetime
import uuid

# API 配置
API_BASE = os.getenv('API_BASE', 'http://localhost:8000')
USER_ID = os.getenv('INIT_USER_ID', str(uuid.uuid4()))

# 家庭基本信息
FAMILY_INFO = [
    {
        "content": "我们家有3个孩子：儿子（最小），大女儿，二女儿",
        "ai_data": {
            "intent": "family_info",
            "type": "family_members",
            "members": [
                {"name": "儿子", "role": "child", "order": 3, "gender": "male"},
                {"name": "大女儿", "role": "child", "order": 1, "gender": "female"},
                {"name": "二女儿", "role": "child", "order": 2, "gender": "female"}
            ]
        }
    },
    {
        "content": "家庭成员：爸爸（我），妈妈（妻子），3个孩子",
        "ai_data": {
            "intent": "family_info",
            "type": "family_structure",
            "total_members": 5,
            "adults": 2,
            "children": 3
        }
    },
    {
        "content": "我是孩子的爸爸，也是妻子的丈夫，负责家庭的主要收入",
        "ai_data": {
            "intent": "family_info",
            "type": "self_info",
            "role": "father",
            "responsibility": "main_income"
        }
    },
    {
        "content": "妻子独自在家照顾3个孩子，非常辛苦",
        "ai_data": {
            "intent": "family_info",
            "type": "spouse_info",
            "role": "mother",
            "responsibility": "childcare",
            "status": "stay_at_home"
        }
    }
]


async def initialize_family_data():
    """初始化家庭基本信息"""
    print("开始初始化家庭基本信息...")
    
    async with httpx.AsyncClient() as client:
        # 首先测试API连接
        try:
            response = await client.get(f"{API_BASE}/health")
            if response.status_code != 200:
                print(f"❌ API健康检查失败: {response.status_code}")
                return
            print("✅ API连接正常")
        except Exception as e:
            print(f"❌ 无法连接到API: {e}")
            return
        
        # 初始化家庭信息
        for info in FAMILY_INFO:
            try:
                # 通过消息接口发送，让AI处理
                response = await client.post(
                    f"{API_BASE}/message",
                    json={
                        "content": info["content"],
                        "user_id": USER_ID
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    print(f"✅ 已记录: {info['content'][:30]}...")
                    print(f"   AI回复: {result.get('response', '')[:50]}...")
                else:
                    print(f"❌ 记录失败: {info['content'][:30]}...")
                    
            except Exception as e:
                print(f"❌ 错误: {e}")
        
        # 设置一些常用提醒
        print("\n设置常用提醒...")
        reminders = [
            "提醒我每天早上8点给孩子们吃维生素",
            "每月15号提醒我查看家庭财务状况",
            "每周日晚上提醒我准备下周的家庭安排"
        ]
        
        for reminder in reminders:
            try:
                response = await client.post(
                    f"{API_BASE}/message",
                    json={
                        "content": reminder,
                        "user_id": USER_ID
                    }
                )
                
                if response.status_code == 200:
                    print(f"✅ 已设置提醒: {reminder}")
                else:
                    print(f"❌ 设置提醒失败: {reminder}")
                    
            except Exception as e:
                print(f"❌ 错误: {e}")
    
    print(f"\n✨ 初始化完成！")
    print(f"用户ID: {USER_ID}")
    print(f"请保存此用户ID，用于后续的Threema绑定")


if __name__ == "__main__":
    asyncio.run(initialize_family_data()) 