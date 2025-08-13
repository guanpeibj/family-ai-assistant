#!/usr/bin/env python3
"""
FAA 家庭数据初始化脚本（将“家庭设定”写入 memories，不放 system prompt）

数据来源优先级：
- 环境变量 FAMILY_DATA_JSON
- 本地文件 family_private_data.json（私有）
- 示例文件 family_data_example.json（示例）
"""
import asyncio
import json
import uuid
from datetime import datetime
import os
import sys
from pathlib import Path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.database import get_session
from src.db.models import User, Memory

PRIVATE_DATA_FILE = Path("family_private_data.json")
EXAMPLE_DATA_FILE = Path("family_data_example.json")


def load_family_data() -> dict:
    data_env = os.getenv('FAMILY_DATA_JSON')
    if data_env:
        try:
            print("🔐 从环境变量加载家庭数据")
            return json.loads(data_env)
        except json.JSONDecodeError as e:
            print(f"❌ FAMILY_DATA_JSON 不是有效的 JSON: {e}")
    if PRIVATE_DATA_FILE.exists():
        print(f"📁 加载私有家庭数据: {PRIVATE_DATA_FILE}")
        with open(PRIVATE_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    if EXAMPLE_DATA_FILE.exists():
        print(f"📋 使用示例数据: {EXAMPLE_DATA_FILE}")
        print("💡 提示：创建 family_private_data.json 使用真实数据")
        with open(EXAMPLE_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    print("❌ 没有可用的家庭数据源。请配置 FAMILY_DATA_JSON 或提供 family_private_data.json/family_data_example.json")
    sys.exit(1)


async def get_or_create_user(session) -> uuid.UUID:
    # 如果已有用户，复用第一个；否则创建
    result = await session.execute("SELECT id FROM users ORDER BY created_at ASC LIMIT 1")
    row = result.first()
    if row and row[0]:
        return row[0]
    new_id = uuid.uuid4()
    session.add(User(id=new_id))
    await session.flush()
    return new_id


async def insert_memory(session, user_id: uuid.UUID, content: str, ai_understanding: dict) -> None:
    mem = Memory(
        id=uuid.uuid4(),
        user_id=user_id,
        content=content,
        ai_understanding=ai_understanding,
        occurred_at=datetime.now(),
    )
    session.add(mem)
    await session.flush()


def build_family_profile_aiu(family_data: dict) -> dict:
    # 统一的家庭设定结构，完全开放；供 AI 检索与使用
    profile = {
        "type": "family_profile",
        "created_from": family_data.get("source", "init_script"),
        "created_at": datetime.now().isoformat(),
    }
    # 成员
    if isinstance(family_data.get("family_members"), list):
        profile["members"] = family_data["family_members"]
    # 偏好/规则
    if isinstance(family_data.get("preferences"), list):
        profile["preferences"] = family_data["preferences"]
    # 重要信息
    if isinstance(family_data.get("important_info"), list):
        profile["important_info"] = family_data["important_info"]
    # 联系人
    if isinstance(family_data.get("contacts"), list):
        profile["contacts"] = family_data["contacts"]
    # 其他任意扩展字段
    for key in ("address", "budget", "medical_notes", "notes"):
        if key in family_data:
            profile[key] = family_data[key]
    return profile


async def init_family_data():
    print("🏠 开始初始化家庭设定到 memories...")
    family_data = load_family_data()

    async with get_session() as session:
        user_id = await get_or_create_user(session)
        print(f"✓ 使用用户: {user_id}")

        # 1) 家庭总设定（单条）
        family_profile = build_family_profile_aiu(family_data)
        await insert_memory(session, user_id, content="家庭设定初始化", ai_understanding=family_profile)
        print("✓ 已写入家庭设定 (family_profile)")

        # 2) 个体成员档案（可选，多条）
        members = family_data.get("family_members") or []
        if isinstance(members, list):
            for m in members:
                aiu = {
                    "type": "family_member_profile",
                    "person": m.get("name") or m.get("id") or "unknown",
                    "role": m.get("role"),
                    "birthday": m.get("birthday"),
                    "notes": m.get("notes"),
                }
                await insert_memory(session, user_id, content=f"成员档案：{aiu['person']}", ai_understanding=aiu)
            print(f"✓ 成员档案初始化完成 ({len(members)} 人)")

        # 3) 可选：重要信息/偏好/联系人作为独立记忆（如果需要更细粒度）
        for block_key, block_type in (
            ("important_info", "family_important_info"),
            ("preferences", "family_preference"),
            ("contacts", "family_contact"),
        ):
            items = family_data.get(block_key)
            if isinstance(items, list):
                for item in items:
                    aiu = {"type": block_type, **item}
                    content = item.get("content") or f"{block_key}"
                    await insert_memory(session, user_id, content=content, ai_understanding=aiu)
                print(f"✓ {block_key} 初始化完成 ({len(items)} 条)")

    print("\n🎉 家庭设定初始化完成！后续个性化可由 AI 在运行中继续补充。")


if __name__ == "__main__":
    asyncio.run(init_family_data())