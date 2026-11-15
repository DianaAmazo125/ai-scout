from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import structlog

from ai_scout.models import RawMessage
from ai_scout.storage.repository import LeadRepository
from ai_scout.telegram.resolver import build_message_link

log = structlog.get_logger(__name__)


class EventLike(Protocol):
    """Минимальный контракт события, который нужен обработчику."""

    chat_id: int
    raw_text: str | None
    sender_id: int | None
    message: Any

    async def get_sender(self) -> Any: ...

    async def get_chat(self) -> Any: ...


@dataclass(frozen=True)
class HandleResult:
    message: RawMessage
    inserted: bool


def chat_title(entity: Any, fallback_id: int) -> str:
    if entity is None:
        return str(fallback_id)
    return getattr(entity, "title", None) or getattr(entity, "first_name", None) or str(fallback_id)


def display_name(entity: Any) -> str | None:
    if entity is None:
        return None
    parts = [
        getattr(entity, "first_name", None),
        getattr(entity, "last_name", None),
    ]
    name = " ".join(part for part in parts if part).strip()
    return name or getattr(entity, "title", None) or getattr(entity, "username", None)


class MessageHandler:
    """Превращает событие Telegram в RawMessage и сохраняет его в БД.

    Не зависит от Telethon: в тестах и replay сюда приходят fake-события.
    """

    def __init__(
        self,
        repo: LeadRepository,
        *,
        ignore_forwards: bool = True,
        ignore_bots: bool = True,
    ) -> None:
        self._repo = repo
        self.ignore_forwards = ignore_forwards
        self.ignore_bots = ignore_bots

    async def handle(self, event: EventLike) -> HandleResult | None:
        """None — сообщение пропущено (фильтр) или обработка упала."""

        try:
            return await self._handle(event)
        except Exception:
            log.exception(
                "message_handling_failed",
                chat_id=event.chat_id,
                message_id=getattr(event.message, "id", None),
            )
            return None

    async def _handle(self, event: EventLike) -> HandleResult | None:
        message = event.message

        if self.ignore_forwards and message.fwd_from is not None:
            log.debug("skip_forwarded", chat_id=event.chat_id, message_id=message.id)
            return None

        text = (event.raw_text or "").strip()
        if not text:
            log.debug("skip_empty_text", chat_id=event.chat_id, message_id=message.id)
            return None

        sender = await event.get_sender()
        if self.ignore_bots and getattr(sender, "bot", False):
            log.debug("skip_bot", chat_id=event.chat_id, message_id=message.id)
            return None

        chat = await event.get_chat()
        title = chat_title(chat, event.chat_id)

        raw = RawMessage(
            chat_id=event.chat_id,
            chat_title=title,
            message_id=message.id,
            sender_id=getattr(sender, "id", None) or event.sender_id,
            sender_username=getattr(sender, "username", None),
            sender_name=display_name(sender),
            text=text,
            date=message.date,
            link=build_message_link(
                event.chat_id,
                message.id,
                getattr(chat, "username", None),
            ),
        )

        inserted = await self._repo.save_raw_message(raw)
        payload = {
            "chat": raw.chat_title,
            "chat_id": raw.chat_id,
            "message_id": raw.message_id,
            "sender": raw.sender_name or "unknown",
            "username": f"@{raw.sender_username}" if raw.sender_username else None,
            "link": raw.link,
            "text": raw.text,
        }

        if inserted:
            log.info("message_captured", **payload)
        else:
            log.info("message_duplicate", **payload)

        return HandleResult(message=raw, inserted=inserted)
