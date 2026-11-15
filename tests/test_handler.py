import json
from pathlib import Path

import pytest

from ai_scout.storage.db import Database
from ai_scout.storage.repository import LeadRepository
from ai_scout.telegram.fakes import event_from_dict
from ai_scout.telegram.handler import MessageHandler

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "messages.json").read_text(encoding="utf-8")
)


async def _make_handler(tmp_path, **kwargs):
    db = Database(tmp_path / "test.db")
    await db.connect()
    repo = LeadRepository(db)
    return db, repo, MessageHandler(repo, **kwargs)


@pytest.mark.asyncio
async def test_saves_lead_and_dedupes(tmp_path) -> None:
    db, repo, handler = await _make_handler(tmp_path)

    try:
        first = await handler.handle(event_from_dict(FIXTURES["lead_python_parser"]))
        second = await handler.handle(event_from_dict(FIXTURES["lead_python_parser"]))

        assert first is not None and first.inserted is True
        assert second is not None and second.inserted is False
        assert await repo.total() == 1
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_skips_forwarded_bot_and_empty(tmp_path) -> None:
    db, repo, handler = await _make_handler(tmp_path)

    try:
        assert await handler.handle(event_from_dict(FIXTURES["forwarded"])) is None
        assert await handler.handle(event_from_dict(FIXTURES["from_bot"])) is None
        assert await handler.handle(event_from_dict(FIXTURES["empty_media"])) is None
        assert await repo.total() == 0
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_ignore_flags_can_be_disabled(tmp_path) -> None:
    db, repo, handler = await _make_handler(
        tmp_path,
        ignore_forwards=False,
        ignore_bots=False,
    )

    try:
        forwarded = await handler.handle(event_from_dict(FIXTURES["forwarded"]))
        bot = await handler.handle(event_from_dict(FIXTURES["from_bot"]))

        assert forwarded is not None and forwarded.inserted is True
        assert bot is not None and bot.inserted is True
        assert await repo.total() == 2
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_links_for_public_supergroup_and_private_user(tmp_path) -> None:
    db, _, handler = await _make_handler(tmp_path)

    try:
        public = await handler.handle(event_from_dict(FIXTURES["lead_python_parser"]))
        supergroup = await handler.handle(event_from_dict(FIXTURES["lead_website"]))
        private = await handler.handle(event_from_dict(FIXTURES["private_client"]))

        assert public is not None
        assert public.message.link == "https://t.me/freelance_chat/101"

        assert supergroup is not None
        assert supergroup.message.link == "https://t.me/c/9876543210/202"

        assert private is not None
        assert private.message.link == "tg://openmessage?user_id=555000111"
        assert private.message.chat_title == "Мария"
    finally:
        await db.close()
