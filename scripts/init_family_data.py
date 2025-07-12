#!/usr/bin/env python3
"""
阿福(FAA) 家庭数据初始化脚本
支持从本地私有配置文件加载家庭信息
"""
import asyncio
import json
import uuid
from datetime import datetime, date
import os
import sys
from pathlib import Path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.database import get_db
from src.core.logging import setup_logging

# 设置日志
logger = setup_logging()

# 私有数据文件路径
PRIVATE_DATA_FILE = Path("family_private_data.json")
EXAMPLE_DATA_FILE = Path("family_data_example.json")


def load_family_data():
    """加载家庭数据，优先从环境变量读取，然后从文件读取"""
    # 首先尝试从环境变量读取（CI/CD部署时使用）
    family_data_env = os.getenv('FAMILY_DATA_JSON')
    if family_data_env:
        try:
            print("🔐 从环境变量加载家庭数据")
            return json.loads(family_data_env)
        except json.JSONDecodeError as e:
            print(f"❌ 环境变量 FAMILY_DATA_JSON 格式不正确: {e}")
    
    # 然后尝试从私有文件读取（本地开发时使用）
    if PRIVATE_DATA_FILE.exists():
        print(f"📁 加载私有家庭数据: {PRIVATE_DATA_FILE}")
        with open(PRIVATE_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    elif EXAMPLE_DATA_FILE.exists():
        print(f"📋 使用示例数据: {EXAMPLE_DATA_FILE}")
        print("💡 提示：创建 family_private_data.json 来使用你的真实家庭数据")
        with open(EXAMPLE_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        print("❌ 错误：找不到家庭数据文件")
        print(f"请创建 {PRIVATE_DATA_FILE} 或 {EXAMPLE_DATA_FILE}")
        sys.exit(1)


async def init_family_data():
    """初始化家庭基础数据"""
    print("🏠 开始初始化家庭数据...")
    
    # 加载家庭数据
    family_data = load_family_data()
    
    async with get_db() as db:
        # 1. 创建默认用户（如果不存在）
        user_id = uuid.uuid4()
        
        # 检查是否已有用户
        existing_user = await db.fetchrow(
            "SELECT id FROM users WHERE username = $1",
            family_data.get("username", "family_default")
        )
        
        if existing_user:
            user_id = existing_user['id']
            print(f"✓ 使用已存在的用户: {user_id}")
        else:
            # 创建新用户
            await db.execute(
                """
                INSERT INTO users (id, username, created_at)
                VALUES ($1, $2, $3)
                """,
                user_id, 
                family_data.get("username", "family_default"), 
                datetime.now()
            )
            print(f"✓ 创建新用户: {user_id}")
        
        # 2. 初始化家庭成员信息
        if "family_members" in family_data:
            for member in family_data["family_members"]:
                memory_id = uuid.uuid4()
                await db.execute(
                    """
                    INSERT INTO memories (
                        id, user_id, content, ai_understanding,
                        created_at, occurred_at
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    memory_id,
                    user_id,
                    member['content'],
                    json.dumps(member['ai_understanding'], ensure_ascii=False),
                    datetime.now(),
                    datetime.now()
                )
            print(f"✓ 家庭成员信息初始化完成 ({len(family_data['family_members'])}人)")
        
        # 3. 初始化家庭重要信息
        if "important_info" in family_data:
            for info in family_data["important_info"]:
                memory_id = uuid.uuid4()
                await db.execute(
                    """
                    INSERT INTO memories (
                        id, user_id, content, ai_understanding,
                        created_at, occurred_at
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    memory_id,
                    user_id,
                    info['content'],
                    json.dumps(info['ai_understanding'], ensure_ascii=False),
                    datetime.now(),
                    datetime.now()
                )
            print(f"✓ 家庭重要信息初始化完成 ({len(family_data['important_info'])}条)")
        
        # 4. 初始化常用联系人
        if "contacts" in family_data:
            for contact in family_data["contacts"]:
                memory_id = uuid.uuid4()
                await db.execute(
                    """
                    INSERT INTO memories (
                        id, user_id, content, ai_understanding,
                        created_at, occurred_at
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    memory_id,
                    user_id,
                    contact['content'],
                    json.dumps(contact['ai_understanding'], ensure_ascii=False),
                    datetime.now(),
                    datetime.now()
                )
            print(f"✓ 常用联系人初始化完成 ({len(family_data['contacts'])}个)")
        
        # 5. 初始化日常习惯和偏好
        if "preferences" in family_data:
            for pref in family_data["preferences"]:
                memory_id = uuid.uuid4()
                await db.execute(
                    """
                    INSERT INTO memories (
                        id, user_id, content, ai_understanding,
                        created_at, occurred_at
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    memory_id,
                    user_id,
                    pref['content'],
                    json.dumps(pref['ai_understanding'], ensure_ascii=False),
                    datetime.now(),
                    datetime.now()
                )
            print(f"✓ 日常习惯和偏好初始化完成 ({len(family_data['preferences'])}条)")
        
        # 6. 设置Threema渠道（优先使用配置文件中的ID）
        threema_id = family_data.get("threema_id") or os.getenv('USER_THREEMA_ID')
        if threema_id:
            await db.execute(
                """
                INSERT INTO user_channels (user_id, channel, channel_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, channel) DO UPDATE
                SET channel_id = $3
                """,
                user_id, 'threema', threema_id
            )
            print(f"✓ Threema渠道配置完成: {threema_id}")
        
        print("\n🎉 家庭数据初始化成功！")
        print(f"用户ID: {user_id}")
        
        if PRIVATE_DATA_FILE.exists():
            print("\n✅ 已使用你的私有家庭数据")
        else:
            print("\n⚠️  当前使用的是示例数据")
            print("要使用真实数据，请：")
            print(f"1. 复制 {EXAMPLE_DATA_FILE} 为 {PRIVATE_DATA_FILE}")
            print("2. 编辑 family_private_data.json 填入你的真实家庭信息")
            print("3. 重新运行此脚本")
        
        print("\n现在可以开始使用阿福了！")


if __name__ == "__main__":
    asyncio.run(init_family_data()) 