#!/usr/bin/env python3
"""
批量导入日历/学期/家庭日程数据到 memories（通过 MCP HTTP Wrapper）。

用法：
  python scripts/import_calendar_data.py --path data/calendar --user-id <UUID或标识> --apply
  python scripts/import_calendar_data.py --path data/calendar --user-id <UUID或标识> --dry-run

特性：
  - 支持 JSON/YAML 文件（.json/.yaml/.yml），未来可扩展 ICS
  - 幂等导入：使用 external_id/version 进行软去重（先 search 再 store）
  - 每个 event 生成一条 memory，ai_understanding.type = "calendar_event"
  - 可选根据 reminder_policies 生成 schedule_reminder（占位，当前仅打印计划）
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List

import httpx
import yaml

MCP_URL = os.getenv("MCP_SERVER_URL", "http://faa-mcp:8000")


def load_events_from_file(path: str) -> List[Dict[str, Any]]:
    ext = os.path.splitext(path)[1].lower()
    with open(path, "r", encoding="utf-8") as f:
        if ext == ".json":
            data = json.load(f)
        elif ext in (".yaml", ".yml"):
            data = yaml.safe_load(f)
        else:
            # 暂不支持 ICS，这里跳过
            return []
    events = data.get("events") if isinstance(data, dict) else None
    return events if isinstance(events, list) else []


async def mcp_search(client: httpx.AsyncClient, user_id: str, external_id: str) -> List[Dict[str, Any]]:
    payload = {
        "query": "",
        "user_id": user_id,
        "filters": {
            "jsonb_equals": {"external_id": external_id, "type": "calendar_event"},
            "limit": 5,
        },
    }
    resp = await client.post(f"{MCP_URL}/tool/search", json=payload, timeout=20.0)
    resp.raise_for_status()
    return resp.json()


async def mcp_store(client: httpx.AsyncClient, user_id: str, content: str, ai_data: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "content": content,
        "ai_data": ai_data,
        "user_id": user_id,
    }
    resp = await client.post(f"{MCP_URL}/tool/store", json=payload, timeout=20.0)
    resp.raise_for_status()
    return resp.json()


def event_to_memory_fields(event: Dict[str, Any], default_source: str) -> Dict[str, Any]:
    title = event.get("title") or "日程"
    start_at = event.get("start_at")
    end_at = event.get("end_at")
    all_day = event.get("all_day")
    category = event.get("category")
    persons = event.get("persons") if isinstance(event.get("persons"), list) else []
    notes = event.get("notes")
    uid = event.get("uid") or event.get("id") or f"evt-{abs(hash(title + (start_at or '')))}"
    source = event.get("source") or default_source
    version = event.get("version") or "1.0"

    # content（可读）
    time_span = f"{start_at}" if (not end_at or start_at == end_at) else f"{start_at} ~ {end_at}"
    content = f"{time_span} {title}"
    if category:
        content += f"（{category}）"

    ai_data: Dict[str, Any] = {
        "type": "calendar_event",
        "title": title,
        "category": category,
        "tags": event.get("tags") or [],
        "persons": persons,
        "location": event.get("location"),
        "notes": notes,
        "start_at": start_at,
        "end_at": end_at,
        "all_day": all_day,
        "recurrence": event.get("recurrence"),
        "data_source": source,
        "external_id": uid,
        "version": version,
        "timezone": event.get("timezone"),
        # 使 occurred_at 可用于时间排序/过滤
        "occurred_at": start_at,
    }
    # 可选提醒策略，仅记录在 ai_data 中，实际设置提醒可由后续任务处理
    if isinstance(event.get("reminder_policies"), list):
        ai_data["reminder_policies"] = event["reminder_policies"]

    return {"content": content, "ai_data": ai_data}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Import calendar/school/family routines to memories via MCP")
    parser.add_argument("--path", required=True, help="root directory containing calendar data files")
    parser.add_argument("--user-id", required=True, help="target user id or stable identifier")
    parser.add_argument("--apply", action="store_true", help="actually write to DB via MCP store")
    parser.add_argument("--dry-run", action="store_true", help="only print plan without writing")
    args = parser.parse_args()

    root = args.path
    user_id = args["user_id"] if isinstance(args, dict) else args.user_id
    do_apply = args.apply and not args.dry_run

    files: List[str] = []
    for base, _, names in os.walk(root):
        for n in names:
            if n.lower().endswith((".json", ".yaml", ".yml")):
                files.append(os.path.join(base, n))

    if not files:
        print("No calendar files found.")
        return

    async with httpx.AsyncClient() as client:
        imported, skipped, failed = 0, 0, 0
        for fp in sorted(files):
            events = load_events_from_file(fp)
            if not events:
                continue
            default_source = os.path.relpath(fp, root)
            for ev in events:
                try:
                    fields = event_to_memory_fields(ev, default_source)
                    ext_id = fields["ai_data"].get("external_id")
                    # 幂等：先查是否已存在相同 external_id 的 calendar_event
                    existing = await mcp_search(client, user_id, ext_id)
                    exists = any(isinstance(x, dict) and not x.get("_meta") for x in existing)
                    if exists:
                        skipped += 1
                        print(f"SKIP  {ext_id} already exists")
                        continue
                    if args.dry_run:
                        print(f"PLAN  import {ext_id}: {fields['content']}")
                        imported += 1
                    elif do_apply:
                        res = await mcp_store(client, user_id, fields["content"], fields["ai_data"])
                        ok = bool(res.get("success"))
                        if ok:
                            imported += 1
                            print(f"OK    {ext_id} -> id={res.get('id')}")
                        else:
                            failed += 1
                            print(f"FAIL  {ext_id}: {res}")
                except Exception as e:
                    failed += 1
                    print(f"ERROR {e}")

        print(f"Done. imported={imported}, skipped={skipped}, failed={failed}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())


