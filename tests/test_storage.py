from datetime import UTC, datetime

import pytest

from ai_scout.models import RawMessage
from ai_scout.storage.db import Database
from ai_scout.storage.repository import LeadRepository


def _message() -> RawMessage:
    return RawMessage(
        chat_id=-1001234567890,
        chat_title="Freelance Chat",
        message_id=42,
        sender_id=123456789,
        sender_username="ivan",
        sender_name="Ivan",
        text="Нужен парсер карточек товара на Python",
        date=datetime(2026, 11, 4, 12, 0, tzinfo=UTC),
        link="https://t.me/freelance_chat/42",
    )


@pytest.mark.asyncio
async def test_save_and_dedupe(tmp_path) -> None:
    db = Database(tmp_path / "test.db")
    await db.connect()
    repo = LeadRepository(db)

    try:
        assert await repo.save_raw_message(_message()) is True
        assert await repo.save_raw_message(_message()) is False
        assert await repo.total() == 1
    finally:
        await db.close()
