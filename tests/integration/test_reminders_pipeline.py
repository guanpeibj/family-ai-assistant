#!/usr/bin/env python3
"""
提醒流水测试 - 验证 schedule_reminder → check_and_send_reminders 的联动
"""
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import uuid

from sqlalchemy import select

from base_new import IntegrationTestBase
from src.services.engine_provider import ai_engine
from src.db.database import get_session
from src.db.models import Reminder


class TestRemindersPipeline(IntegrationTestBase):
    def __init__(self):
        super().__init__(test_suite_name="reminder_pipeline")

    async def test_daily_repeat_reschedule(self):
        await self.setup()
        tz = ZoneInfo("Asia/Shanghai")
        now = datetime.now(tz)
        remind_at = (now - timedelta(minutes=1)).isoformat()
        ai_data = {
            "type": "routine_action",
            "scope": "family",
            "message": "测试群提醒",
            "source": "test_reminder_pipeline"
        }
        store_result = await ai_engine._call_mcp_tool(
            'store',
            content="家庭提醒：测试群提醒",
            ai_data=ai_data,
            user_id=self.test_user_id
        )
        assert store_result.get("success"), "store tool failed"
        memory_id = store_result["id"]
        payload = {
            "scope": "family",
            "target_names": ["测试家庭"],
            "message": "测试家庭，今晚记得带回快递。",
            "timezone": "Asia/Shanghai",
            "repeat_rule": {
                "frequency": "daily",
                "time": now.strftime("%H:%M"),
                "timezone": "Asia/Shanghai"
            },
            "external_key": "test:reminder_pipeline"
        }
        schedule_result = await ai_engine._call_mcp_tool(
            'schedule_reminder',
            memory_id=memory_id,
            remind_at=remind_at,
            payload=payload,
            external_key=payload["external_key"]
        )
        assert schedule_result.get("success"), "schedule_reminder tool failed"

        sent_messages = []

        async def fake_send(user_id: str, content: str) -> bool:
            sent_messages.append((user_id, content))
            return True

        await ai_engine.check_and_send_reminders(fake_send)

        assert len(sent_messages) == 1
        assert sent_messages[0][1] == payload["message"]

        async with get_session() as session:
            query = select(Reminder).where(Reminder.memory_id == uuid.UUID(memory_id))
            result = await session.execute(query)
            reminders = result.scalars().all()
            assert any(r.sent_at is not None for r in reminders), "original reminder should be marked sent"
            pending = [r for r in reminders if r.sent_at is None]
            assert len(pending) == 1, "a new reminder should be scheduled for the next occurrence"
            assert pending[0].remind_at.tzinfo is not None
            assert pending[0].remind_at > datetime.now(tz)

        await self.cleanup()


if __name__ == "__main__":
    test = TestRemindersPipeline()
    asyncio.run(test.test_daily_repeat_reschedule())
