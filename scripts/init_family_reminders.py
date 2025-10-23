#!/usr/bin/env python3
"""
根据家庭配置初始化自动提醒

数据来源：
- family_private_data.json / FAMILY_DATA_JSON
- 侧重处理 routines.ai_actions、seasonal_playbook.ai_reminders

实现思路（遵循AI驱动原则）：
- 通过 MCP.store 创建一条描述型记忆（保持结构开放）
- 调用 MCP.schedule_reminder 注入 AI 生成的 payload（scope/targets/repeat_rule/message）
- 所有时间策略由数据定义，工程仅负责解析时间与重复规则
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx
from zoneinfo import ZoneInfo
import calendar


import sys
import os

# 将 scripts 目录和项目根目录添加到 Python 路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, script_dir)
sys.path.insert(0, project_root)

from init_family_data import load_family_data  # 复用相同的数据加载逻辑
from src.core.config import settings

MCP_URL = settings.MCP_SERVER_URL if hasattr(settings, "MCP_SERVER_URL") else "http://faa-mcp:8000"
DEFAULT_TIME = "09:00"


def parse_time(value: Optional[str]) -> Tuple[int, int]:
    if not value:
        return 9, 0
    try:
        parts = value.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        return hour % 24, minute % 60
    except Exception:
        return 9, 0


def parse_offset(value: Optional[str]) -> timedelta:
    if not value or not isinstance(value, str):
        return timedelta()
    value = value.strip()
    if not value:
        return timedelta()
    sign = 1
    if value.startswith("-"):
        sign = -1
        value = value[1:]
    elif value.startswith("+"):
        value = value[1:]
    unit = 'm'
    if value[-1] in ('m', 'h', 'd'):
        unit = value[-1]
        value = value[:-1]
    try:
        amount = int(value)
    except Exception:
        return timedelta()
    if unit == 'm':
        return timedelta(minutes=amount * sign)
    if unit == 'h':
        return timedelta(hours=amount * sign)
    if unit == 'd':
        return timedelta(days=amount * sign)
    return timedelta()


def next_daily_occurrence(now_local: datetime, routine_time: str, offset: timedelta) -> datetime:
    hour, minute = parse_time(routine_time)
    candidate = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now_local:
        candidate += timedelta(days=1)
    return candidate + offset


def weekday_to_int(name: str) -> Optional[int]:
    mapping = {
        'monday': 0,
        'tuesday': 1,
        'wednesday': 2,
        'thursday': 3,
        'friday': 4,
        'saturday': 5,
        'sunday': 6,
    }
    if not name:
        return None
    key = name.strip().lower()
    return mapping.get(key)


def next_weekly_occurrence(now_local: datetime, routine_day: Optional[str], routine_time: str, offset: timedelta) -> datetime:
    hour, minute = parse_time(routine_time)
    start = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    target_weekday = weekday_to_int(routine_day) if routine_day else None
    if target_weekday is None:
        target_weekday = start.weekday()
    days_ahead = (target_weekday - start.weekday()) % 7
    candidate = start + timedelta(days=days_ahead)
    if candidate <= now_local:
        candidate += timedelta(days=7)
    return candidate + offset


def next_monthly_occurrence(now_local: datetime, routine_day: Optional[int], routine_time: str, offset: timedelta) -> datetime:
    hour, minute = parse_time(routine_time or DEFAULT_TIME)
    day = routine_day if isinstance(routine_day, int) else now_local.day
    year = now_local.year
    month = now_local.month
    candidate = now_local.replace(day=min(day, calendar.monthrange(year, month)[1]), hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now_local:
        month += 1
        year += (month - 1) // 12
        month = ((month - 1) % 12) + 1
        day = min(day, calendar.monthrange(year, month)[1])
        candidate = candidate.replace(year=year, month=month, day=day)
    return candidate + offset


async def mcp_store(client: httpx.AsyncClient, content: str, ai_data: Dict[str, Any], user_id: str) -> Optional[str]:
    resp = await client.post(f"{MCP_URL}/tool/store", json={
        "content": content,
        "ai_data": ai_data,
        "user_id": user_id
    }, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()
    if data.get("success"):
        return data.get("id")
    return None


async def mcp_schedule_reminder(
    client: httpx.AsyncClient,
    memory_id: str,
    remind_at: str,
    payload: Dict[str, Any],
    external_key: Optional[str]
):
    body = {
        "memory_id": memory_id,
        "remind_at": remind_at,
        "payload": payload,
    }
    if external_key:
        body["external_key"] = external_key
    resp = await client.post(f"{MCP_URL}/tool/schedule_reminder", json=body, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def build_repeat_rule(routine: Dict[str, Any], timezone_name: str) -> Dict[str, Any]:
    routine_type = (routine.get("type") or "daily").lower()
    rule: Dict[str, Any] = {"timezone": timezone_name}
    if routine_type == "daily":
        rule["frequency"] = "daily"
        rule["time"] = routine.get("time") or DEFAULT_TIME
    elif routine_type == "weekly":
        rule["frequency"] = "weekly"
        rule["time"] = routine.get("time") or DEFAULT_TIME
        rule["weekday"] = routine.get("day")
    elif routine_type == "monthly":
        rule["frequency"] = "monthly"
        rule["time"] = routine.get("time") or DEFAULT_TIME
        day = routine.get("day")
        if isinstance(day, int):
            rule["day"] = day
    else:
        rule["frequency"] = "daily"
        rule["time"] = routine.get("time") or DEFAULT_TIME
    return rule


def resolve_target_keys(routine: Dict[str, Any], action: Dict[str, Any]) -> List[str]:
    if isinstance(action.get("target_member_keys"), list):
        return [str(k) for k in action["target_member_keys"]]
    if isinstance(routine.get("participants"), list):
        return [str(k) for k in routine["participants"]]
    return []


async def init_family_reminders(apply: bool = False, include_seasonal: bool = True):
    family_data = load_family_data()
    timezone_name = (
        family_data.get("household", {}).get("timezone")
        or family_data.get("timezone")
        or "Asia/Shanghai"
    )
    tz = ZoneInfo(timezone_name)
    now_local = datetime.now(tz)
    shared_user_ids = settings.get_family_shared_user_ids()
    default_user_id = shared_user_ids[0] if shared_user_ids else "family_default"
    
    async with httpx.AsyncClient() as client:
        scheduled = 0
        routines = family_data.get("routines") or []
        for routine in routines:
            actions = routine.get("ai_actions")
            if not isinstance(actions, list):
                continue
            routine_type = (routine.get("type") or "daily").lower()
            repeat_rule = build_repeat_rule(routine, timezone_name)
            for idx, action in enumerate(actions):
                message = action.get("message")
                if not isinstance(message, str) or not message.strip():
                    continue
                offset = parse_offset(action.get("time_offset"))
                if routine_type == "weekly":
                    remind_dt = next_weekly_occurrence(now_local, routine.get("day"), routine.get("time") or DEFAULT_TIME, offset)
                elif routine_type == "monthly":
                    day_raw = routine.get("day")
                    day_value = int(day_raw) if isinstance(day_raw, int) else None
                    remind_dt = next_monthly_occurrence(now_local, day_value, routine.get("time") or DEFAULT_TIME, offset)
                else:
                    remind_dt = next_daily_occurrence(now_local, routine.get("time") or DEFAULT_TIME, offset)
                payload = {
                    "scope": "personal" if len(resolve_target_keys(routine, action)) == 1 else "family",
                    "target_member_keys": resolve_target_keys(routine, action),
                    "message": message.strip(),
                    "timezone": timezone_name,
                    "repeat_rule": repeat_rule,
                    "external_key": f"routine:{routine.get('name','unknown')}:{idx}",
                    "routine_name": routine.get("name"),
                    "routine_type": routine_type
                }
                ai_data = {
                    "type": "routine_action",
                    "routine_name": routine.get("name"),
                    "routine_type": routine_type,
                    "message": message.strip(),
                    "target_member_keys": payload["target_member_keys"],
                    "timezone": timezone_name,
                    "repeat_rule": repeat_rule,
                    "scope": payload["scope"],
                    "source": "family_routine_seed",
                }
                content = f"{routine.get('name') or 'Routine'} - {message.strip()}"
                memory_id = await mcp_store(client, content, ai_data, default_user_id) if apply else "dry-run-memory-id"
                if not memory_id:
                    print(f"⚠️  未能写入 routine 记忆：{content}")
                    continue
                result = await mcp_schedule_reminder(
                    client,
                    memory_id if apply else "dry-run-memory-id",
                    remind_dt.isoformat(),
                    payload,
                    payload.get("external_key")
                ) if apply else {"success": True}
                if result.get("success"):
                    scheduled += 1
                    mode = "创建" if apply else "计划"
                    print(f"✓ {mode}提醒：{payload['external_key']} @ {remind_dt.isoformat()}")
                else:
                    print(f"⚠️  提醒创建失败：{payload.get('external_key')} -> {result}")
        
        if include_seasonal:
            seasonal = family_data.get("seasonal_playbook") or []
            for block in seasonal:
                reminders = block.get("ai_reminders")
                if not isinstance(reminders, list):
                    continue
                season = block.get("season")
                for idx, reminder in enumerate(reminders):
                    message = reminder.get("message")
                    if not isinstance(message, str) or not message.strip():
                        continue
                    payload = {
                        "scope": "family",
                        "message": message.strip(),
                        "timezone": timezone_name,
                        "trigger": reminder.get("trigger"),
                        "season": season,
                        "external_key": f"seasonal:{season}:{idx}"
                    }
                    ai_data = {
                        "type": "seasonal_reminder_playbook",
                        "season": season,
                        "message": message.strip(),
                        "trigger": reminder.get("trigger"),
                        "scope": "family",
                        "timezone": timezone_name,
                        "source": "seasonal_playbook"
                    }
                    memory_id = await mcp_store(client, f"季节提醒 - {season}", ai_data, default_user_id) if apply else "dry-run-memory-id"
                    remind_dt = (datetime.now(tz) + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
                    if result := (await mcp_schedule_reminder(
                        client,
                        memory_id if apply else "dry-run-memory-id",
                        remind_dt.isoformat(),
                        payload,
                        payload.get("external_key")
                    ) if apply else {"success": True}):
                        if result.get("success"):
                            scheduled += 1
                            mode = "创建" if apply else "计划"
                            print(f"✓ {mode}季节提醒：{payload['external_key']} @ {remind_dt.isoformat()}")
                        else:
                            print(f"⚠️  季节提醒失败：{payload.get('external_key')} -> {result}")
        
        print(f"\n共 {'创建' if apply else '计划'} {scheduled} 条提醒。")


def main():
    parser = argparse.ArgumentParser(description="初始化家庭自动提醒")
    parser.add_argument("--apply", action="store_true", help="实际写入数据库（默认仅预览计划）")
    parser.add_argument("--include-seasonal", action="store_true", help="包含 seasonal_playbook 提醒（默认包含）")
    args = parser.parse_args()
    asyncio.run(init_family_reminders(apply=args.apply, include_seasonal=args.include_seasonal or True))


if __name__ == "__main__":
    main()
