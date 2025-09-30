#!/usr/bin/env python3
"""
FAA 家庭数据初始化脚本

目标：
- 读取家庭配置 JSON（私有或示例）
- 将关键资料写入数据库（memories + 家庭结构表）
- 为 AI 提供丰富、可进化的家庭上下文

数据来源优先级：
1. 环境变量 FAMILY_DATA_JSON
2. 本地 family_private_data.json（私有，不纳入仓库）
3. 示例 family_data_example.json
"""
import asyncio
import json
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from src.db.database import get_session
from src.db.models import (
    ChannelType,
    FamilyHousehold,
    FamilyMember,
    FamilyMemberAccount,
    Memory,
    User,
    UserChannel,
)

PRIVATE_DATA_FILE = Path("family_private_data.json")
EXAMPLE_DATA_FILE = Path("family_data_example.json")


def load_family_data() -> Dict[str, Any]:
    data_env = os.getenv('FAMILY_DATA_JSON')
    if data_env:
        try:
            print("🔐 从环境变量加载家庭数据")
            return json.loads(data_env)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"FAMILY_DATA_JSON 不是有效 JSON: {exc}")

    if PRIVATE_DATA_FILE.exists():
        print(f"📁 加载私有家庭数据: {PRIVATE_DATA_FILE}")
        with PRIVATE_DATA_FILE.open('r', encoding='utf-8') as fh:
            return json.load(fh)

    if EXAMPLE_DATA_FILE.exists():
        print(f"📋 使用示例数据: {EXAMPLE_DATA_FILE}")
        print("💡 提示：复制为 family_private_data.json 并填写真实数据")
        with EXAMPLE_DATA_FILE.open('r', encoding='utf-8') as fh:
            return json.load(fh)

    raise SystemExit("没有可用的家庭数据源，请配置 FAMILY_DATA_JSON 或提供 family_private_data.json")


async def get_or_create_user(session) -> uuid.UUID:
    result = await session.execute(select(User.id).order_by(User.created_at.asc()).limit(1))
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    user = User(id=uuid.uuid4())
    session.add(user)
    await session.flush()
    return user.id


def slugify(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    slug = re.sub(r'[^0-9A-Za-z]+', '_', str(value))
    slug = re.sub(r'_+', '_', slug).strip('_').lower()
    return slug or None


def canonical_member_key(member: Dict[str, Any], index: int, used: set) -> str:
    """
    生成成员的唯一key，优先使用JSON中定义的member_key字段
    确保幂等性：相同的输入总是生成相同的key
    """
    candidates = [
        member.get('member_key'),  # 最高优先级：JSON中显式定义的
        member.get('key'),
        slugify(member.get('role')),
        slugify(member.get('name')),
        f"member_{index + 1}",
    ]
    key: Optional[str] = None
    for candidate in candidates:
        if candidate:
            key = slugify(candidate) if isinstance(candidate, str) else candidate
            if key:
                break
    if not key:
        key = f"member_{index + 1}"

    # 不再添加后缀，保持key的稳定性
    # 如果key已存在于数据库中，sync_members会更新而不是创建新记录
    used.add(key)
    return key


def resolve_channel(channel_name: Optional[str]) -> Optional[ChannelType]:
    if not channel_name:
        return None
    try:
        return ChannelType(channel_name.lower())
    except ValueError:
        try:
            return ChannelType[channel_name.upper()]
        except KeyError:
            return None


async def ensure_household(session, family_data: Dict[str, Any]) -> FamilyHousehold:
    raw = family_data.get('household') or {}
    slug = slugify(raw.get('slug') or family_data.get('username') or 'primary') or 'family'
    display_name = raw.get('display_name') or family_data.get('household_name') or "家庭"
    description = raw.get('description')
    config_payload = {
        'timezone': raw.get('timezone'),
        'preferences': family_data.get('preferences'),
        'important_info': family_data.get('important_info'),
        'contacts': family_data.get('contacts'),
        'source': family_data.get('source'),
    }
    config = {k: v for k, v in config_payload.items() if v}

    stmt = select(FamilyHousehold).where(FamilyHousehold.slug == slug)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        existing.display_name = display_name
        existing.description = description
        merged = existing.config or {}
        merged.update(config)
        existing.config = merged
        return existing

    household = FamilyHousehold(
        slug=slug,
        display_name=display_name,
        description=description,
        config=config,
    )
    session.add(household)
    await session.flush()
    return household


async def ensure_user_channel(session, channel: ChannelType, channel_user_id: str, channel_data: Dict[str, Any], is_primary: Optional[bool]) -> uuid.UUID:
    channel_value = channel.value if isinstance(channel, ChannelType) else str(channel).lower()
    stmt = select(UserChannel).where(
        UserChannel.channel == channel_value,
        UserChannel.channel_user_id == channel_user_id,
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        existing.channel_data = channel_data or existing.channel_data
        if is_primary is not None:
            existing.is_primary = bool(is_primary)
        return existing.user_id

    user = User(id=uuid.uuid4())
    session.add(user)
    await session.flush()

    session.add(
        UserChannel(
            user_id=user.id,
            channel=channel_value,
            channel_user_id=channel_user_id,
            channel_data=channel_data or {},
            is_primary=bool(is_primary),
        )
    )
    await session.flush()
    return user.id


async def link_member_account(session, member_id: uuid.UUID, user_id: uuid.UUID, *, is_primary: bool = False, labels: Optional[Dict[str, Any]] = None) -> None:
    # 确保用户存在于users表中
    user_stmt = select(User).where(User.id == user_id)
    user_exists = (await session.execute(user_stmt)).scalar_one_or_none()
    if not user_exists:
        session.add(User(id=user_id))
        await session.flush()
    
    stmt = select(FamilyMemberAccount).where(
        FamilyMemberAccount.member_id == member_id,
        FamilyMemberAccount.user_id == user_id,
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        existing.is_primary = existing.is_primary or bool(is_primary)
        if labels:
            merged = existing.labels or {}
            merged.update(labels)
            existing.labels = merged
    else:
        session.add(
            FamilyMemberAccount(
                member_id=member_id,
                user_id=user_id,
                is_primary=bool(is_primary),
                labels=labels or {},
            )
        )
    await session.flush()


async def sync_members(
    session,
    household: FamilyHousehold,
    members_data: List[Dict[str, Any]],
) -> Dict[str, Tuple[FamilyMember, Dict[str, Any]]]:
    stmt = select(FamilyMember).where(FamilyMember.household_id == household.id)
    existing_members = {m.member_key: m for m in (await session.execute(stmt)).scalars()}
    used_keys = set(existing_members.keys())

    synced: Dict[str, Tuple[FamilyMember, Dict[str, Any]]] = {}

    for idx, raw_member in enumerate(members_data):
        key = canonical_member_key(raw_member, idx, used_keys)
        profile_payload = dict(raw_member)
        profile_payload['member_key'] = key

        names_block = profile_payload.get('names') if isinstance(profile_payload.get('names'), dict) else {}
        display_name = (
            names_block.get('preferred')
            or raw_member.get('name')
            or names_block.get('nickname')
            or raw_member.get('display_name')
            or key
        )
        relationship = raw_member.get('role')
        life_status = profile_payload.get('life_status') if isinstance(profile_payload.get('life_status'), dict) else {}
        is_alive = (life_status.get('status') or 'alive') != 'deceased'

        member = existing_members.pop(key, None)
        if member is None:
            member = FamilyMember(
                household_id=household.id,
                member_key=key,
                display_name=display_name,
                relationship=relationship,
                profile=profile_payload,
                is_active=is_alive,
            )
            session.add(member)
            await session.flush()
        else:
            member.display_name = display_name
            member.relationship = relationship
            member.profile = profile_payload
            member.is_active = is_alive

        synced[key] = (member, profile_payload)

    for member in existing_members.values():
        member.is_active = False

    return synced


async def sync_member_accounts(
    session,
    member: FamilyMember,
    account_entries: List[Dict[str, Any]],
    member_profile: Optional[Dict[str, Any]] = None,
) -> bool:
    if not account_entries:
        return False

    processed = False
    for entry in account_entries:
        channel_type = resolve_channel(entry.get('channel'))
        channel_user_id = entry.get('channel_user_id')
        if not channel_type or not channel_user_id:
            continue

        channel_data = entry.get('channel_data') or {
            k: v for k, v in entry.items() if k not in {'channel', 'channel_user_id', 'is_primary', 'labels', 'user_id'}
        }
        is_primary = entry.get('is_primary')
        labels = entry.get('labels') if isinstance(entry.get('labels'), dict) else None

        user_id_value = entry.get('user_id') or (member_profile.get('user_id') if member_profile else None)
        user_uuid: Optional[uuid.UUID] = None
        if user_id_value:
            try:
                user_uuid = uuid.UUID(str(user_id_value))
            except ValueError:
                user_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"faa:{user_id_value}")
                labels = labels or {}
                labels.setdefault('alias', str(user_id_value))

        if user_uuid is None:
            user_uuid = await ensure_user_channel(session, channel_type, channel_user_id, channel_data, is_primary)

        await link_member_account(session, member.id, user_uuid, is_primary=bool(is_primary), labels=labels)
        processed = True

    return processed


def build_family_profile_aiu(family_data: Dict[str, Any], household: FamilyHousehold) -> Dict[str, Any]:
    profile = {
        "type": "family_profile",
        "family_scope": True,
        "household_id": str(household.id),
        "household_slug": household.slug,
        "created_from": family_data.get("source", "init_script"),
        "created_at": datetime.now().isoformat(),
    }
    for field in ("family_members", "preferences", "important_info", "contacts"):
        if isinstance(family_data.get(field), list):
            profile[field] = family_data[field]
    for key in ("address", "budget", "medical_notes", "notes"):
        if key in family_data:
            profile[key] = family_data[key]
    return profile


async def insert_memory(session, user_id: uuid.UUID, content: str, ai_understanding: Dict[str, Any]) -> None:
    session.add(
        Memory(
            id=uuid.uuid4(),
            user_id=user_id,
            content=content,
            ai_understanding=ai_understanding,
            occurred_at=datetime.now(),
        )
    )
    await session.flush()


async def init_family_data() -> None:
    print("🏠 开始初始化家庭设定到数据库...")
    family_data = load_family_data()
    members_payload = family_data.get("family_members") or []

    async with get_session() as session:
        primary_user_id = await get_or_create_user(session)
        print(f"✓ 使用用户: {primary_user_id}")

        household = await ensure_household(session, family_data)
        print(f"✓ 家庭已建立/更新：{household.display_name} (slug={household.slug})")

        members_synced = await sync_members(session, household, members_payload if isinstance(members_payload, list) else [])
        print(f"✓ 成员同步完成，共 {len(members_synced)} 人")

        # 同步账户信息
        for key, (member, profile) in members_synced.items():
            life_status = profile.get('life_status') if isinstance(profile.get('life_status'), dict) else {}
            if life_status.get('status') == 'deceased':
                continue
            account_entries = []
            if isinstance(profile.get('accounts'), list):
                account_entries.extend(profile['accounts'])

            # 兼容顶层 threema_id：默认绑定给父亲
            if profile.get('role') == 'father' and family_data.get('threema_id'):
                account_entries.append({
                    'channel': 'threema',
                    'channel_user_id': family_data['threema_id'],
                    'is_primary': True,
                    'labels': {'source': 'legacy_threema_id'},
                })

            linked = await sync_member_accounts(session, member, account_entries, profile)
            if linked:
                print(f"  ↳ 绑定账号：{profile.get('name') or key} ({len(account_entries)} 条)")

        # 1) 家庭总设定
        family_profile = build_family_profile_aiu(family_data, household)
        await insert_memory(session, primary_user_id, content="家庭设定初始化", ai_understanding=family_profile)
        print("✓ 已写入家庭设定 (family_profile)")

        # 2) 成员档案（逐条写入，供语义检索）
        for key, (member, profile) in members_synced.items():
            aiu = {
                "type": "family_member_profile",
                "family_scope": True,
                "household_id": str(household.id),
                "household_slug": household.slug,
                "member_key": key,
                "person": profile.get('name') or key,
                "role": profile.get('role'),
                "birthday": profile.get('birthday'),
                "notes": profile.get('notes'),
                "profile": profile,
                "names": profile.get('names'),
                "life_status": profile.get('life_status'),
            }
            await insert_memory(session, primary_user_id, content=f"成员档案：{aiu['person']}", ai_understanding=aiu)
        if members_synced:
            print(f"✓ 成员档案初始化完成 ({len(members_synced)} 人)")

        # 3) 重要信息 / 偏好 / 联系人
        for block_key, block_type in (
            ("important_info", "family_important_info"),
            ("preferences", "family_preference"),
            ("contacts", "family_contact"),
        ):
            items = family_data.get(block_key)
            if not isinstance(items, list):
                continue
            for item in items:
                aiu = {
                    "type": block_type,
                    "family_scope": True,
                    "household_id": str(household.id),
                    "household_slug": household.slug,
                    **item,
                }
                content = item.get("content") or block_key
                await insert_memory(session, primary_user_id, content=content, ai_understanding=aiu)
            if items:
                print(f"✓ {block_key} 初始化完成 ({len(items)} 条)")

    print("\n🎉 家庭设定初始化完成。AI 将在运行时自动利用这些资料，实现更贴心的管家体验。")


if __name__ == "__main__":
    asyncio.run(init_family_data())
