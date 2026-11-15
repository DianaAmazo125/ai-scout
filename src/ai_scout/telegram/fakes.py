"""Fake-события Telethon для тестов и replay без сети."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class FakeSender:
    id: int | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    bot: bool = False


@dataclass(slots=True)
class FakeChat:
    title: str | None = None
    username: str | None = None
    first_name: str | None = None


@dataclass(slots=True)
class FakeMessage:
    id: int
    date: datetime
    fwd_from: Any | None = None


@dataclass(slots=True)
class FakeEvent:
    message: FakeMessage
    chat_id: int
    raw_text: str | None
    sender_id: int | None
    _chat: FakeChat
    _sender: FakeSender | None

    async def get_chat(self) -> FakeChat:
        return self._chat

    async def get_sender(self) -> FakeSender | None:
        return self._sender


def event_from_dict(data: dict[str, Any]) -> FakeEvent:
    """Собираем событие из словаря фикстуры (см. tests/fixtures/messages.json)."""

    sender = None
    if data.get("sender_id") is not None:
        sender = FakeSender(
            id=data.get("sender_id"),
            username=data.get("sender_username"),
            first_name=data.get("sender_first_name"),
            last_name=data.get("sender_last_name"),
            bot=bool(data.get("is_bot", False)),
        )

    chat = FakeChat(
        title=data.get("chat_title"),
        username=data.get("chat_username"),
        first_name=data.get("chat_first_name"),
    )

    raw_date = data.get("date")
    date = datetime.fromisoformat(raw_date) if isinstance(raw_date, str) else datetime.now(UTC)

    message = FakeMessage(
        id=int(data["message_id"]),
        date=date,
        fwd_from=object() if data.get("forwarded") else None,
    )

    return FakeEvent(
        message=message,
        chat_id=int(data["chat_id"]),
        raw_text=data.get("text"),
        sender_id=data.get("sender_id"),
        _chat=chat,
        _sender=sender,
    )
