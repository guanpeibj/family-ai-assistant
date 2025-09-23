"""家庭上下文服务：为 AI 层提供家庭/成员的元数据"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional, Set

import structlog
from sqlalchemy import select, text

from ..core.config import settings
from ..db.database import get_session
from ..db import models

logger = structlog.get_logger(__name__)

_CACHE_TTL_SECONDS = 60.0
_NAMESPACE = uuid.NAMESPACE_URL


def _normalize_user_id(raw: Optional[str]) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    try:
        return str(uuid.UUID(cleaned))
    except Exception:
        return str(uuid.uuid5(_NAMESPACE, f"faa:{cleaned}"))


class HouseholdService:
    """负责聚合家庭/成员数据，便于 prompt 注入。"""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_expiry: float = 0.0

    async def get_context(self, *, refresh: bool = False) -> Dict[str, Any]:
        now = time.monotonic()
        if not refresh and self._cache and now < self._cache_expiry:
            return self._cache

        async with self._lock:
            if refresh or self._cache is None or now >= self._cache_expiry:
                self._cache = await self._load_context()
                self._cache_expiry = time.monotonic() + _CACHE_TTL_SECONDS
        return self._cache or {}

    async def _load_context(self) -> Dict[str, Any]:
        households_payload: List[Dict[str, Any]] = []
        members_payload: List[Dict[str, Any]] = []
        accounts_by_member: Dict[str, Dict[str, Any]] = {}
        mapped_user_ids: Set[str] = set()

        async with get_session() as session:
            households = (await session.execute(select(models.FamilyHousehold))).scalars().all()
            if not households:
                # 自动创建一个默认家庭，确保下游 prompt 始终有可用结构
                default_household = models.FamilyHousehold(
                    slug="primary",
                    display_name="家庭",
                    description="自动创建的默认家庭",
                    config={'auto_created': True},
                )
                session.add(default_household)
                await session.flush()
                households = [default_household]
                logger.info("household.auto_created", household_id=str(default_household.id))

            for household in households:
                households_payload.append({
                    'id': str(household.id),
                    'slug': household.slug,
                    'display_name': household.display_name,
                    'description': household.description,
                    'config': household.config or {},
                })

            members = (await session.execute(select(models.FamilyMember))).scalars().all()
            member_ids = [m.id for m in members]

            if member_ids:
                account_rows = await session.execute(
                    select(
                        models.FamilyMemberAccount.member_id,
                        models.FamilyMemberAccount.user_id,
                        models.FamilyMemberAccount.is_primary,
                        models.FamilyMemberAccount.labels,
                        models.UserChannel.channel,
                        models.UserChannel.channel_user_id,
                        models.UserChannel.is_primary.label('channel_is_primary'),
                    )
                    .outerjoin(
                        models.UserChannel,
                        models.UserChannel.user_id == models.FamilyMemberAccount.user_id,
                    )
                    .where(models.FamilyMemberAccount.member_id.in_(member_ids))
                )

                for row in account_rows:
                    member_id = str(row.member_id)
                    user_id = str(row.user_id)
                    mapped_user_ids.add(user_id)
                    target = accounts_by_member.setdefault(
                        member_id,
                        {
                            'user_ids': [],
                            'accounts': [],
                        },
                    )
                    if user_id not in target['user_ids']:
                        target['user_ids'].append(user_id)
                    channel_entry = None
                    if row.channel is not None:
                        channel_entry = {
                            'channel': row.channel.value if hasattr(row.channel, 'value') else str(row.channel),
                            'channel_user_id': row.channel_user_id,
                            'is_primary': bool(row.channel_is_primary) if row.channel_is_primary is not None else False,
                        }
                    target['accounts'].append(
                        {
                            'user_id': user_id,
                            'is_primary': bool(row.is_primary),
                            'labels': row.labels or {},
                            'channel': channel_entry,
                        }
                    )

            for member in members:
                member_id_str = str(member.id)
                account_info = accounts_by_member.get(member_id_str, {'user_ids': [], 'accounts': []})
                members_payload.append({
                    'id': member_id_str,
                    'household_id': str(member.household_id),
                    'member_key': member.member_key,
                    'display_name': member.display_name,
                    'relationship': member.relationship,
                    'profile': member.profile or {},
                    'is_active': bool(member.is_active),
                    'user_ids': account_info['user_ids'],
                    'accounts': account_info['accounts'],
                })

            implicit_user_ids: Set[str] = set()
            try:
                # 通过已有记忆推断家庭范围的 user_id
                rows = await session.execute(
                    text(
                        "SELECT DISTINCT user_id FROM memories "
                        "WHERE ai_understanding @> '{""family_scope"": true}'::jsonb"
                    )
                )
                implicit_user_ids = {str(row.user_id) for row in rows if row.user_id is not None}
            except Exception as exc:
                logger.warning("household.collect_family_scope_failed", error=str(exc))

        config_user_ids = {
            _normalize_user_id(raw)
            for raw in settings.get_family_shared_user_ids()
            if raw
        }
        config_user_ids.discard(None)

        family_user_ids = set(mapped_user_ids)
        family_user_ids.update(uid for uid in config_user_ids if uid)
        family_user_ids.update(implicit_user_ids)

        context = {
            'households': households_payload,
            'members': members_payload,
            'members_index': {m['member_key']: m for m in members_payload},
            'family_scope': {
                'user_ids': sorted(family_user_ids),
                'implicit_user_ids': sorted(implicit_user_ids),
                'configured_user_ids': sorted(uid for uid in config_user_ids if uid),
            },
        }
        return context


household_service = HouseholdService()
