from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import structlog
from telethon import TelegramClient, events
from telethon import utils as tg_utils

from ai_scout.telegram.handler import MessageHandler, chat_title

log = structlog.get_logger(__name__)


async def resolve_chats(
    client: TelegramClient,
    chats: Sequence[str | int],
) -> list[Any]:
    """Превращаем @username/ID в entity и сразу сообщаем, что не нашлось."""

    resolved: list[Any] = []
    for chat in chats:
        try:
            entity = await client.get_entity(chat)
        except Exception as exc:  # Telethon бросает разные типы
            log.error("chat_resolve_failed", chat=chat, error=str(exc))
            continue

        resolved.append(entity)
        log.info(
            "chat_resolved",
            chat=chat,
            chat_id=tg_utils.get_peer_id(entity),
            title=chat_title(entity, tg_utils.get_peer_id(entity)),
        )
    return resolved


class TelegramListener:
    """Тонкая обёртка Telethon: подписывается на события и отдаёт их handler'у."""

    def __init__(
        self,
        client: TelegramClient,
        chats: Sequence[Any] | None,
        handler: MessageHandler,
    ) -> None:
        self._client = client
        self._chats = list(chats) if chats else None
        self._handler = handler

    def register(self) -> None:
        self._client.add_event_handler(
            self._on_new_message,
            events.NewMessage(chats=self._chats, incoming=True),
        )
        log.info(
            "listener_registered",
            mode="all_incoming" if self._chats is None else "selected_chats",
            chats=len(self._chats) if self._chats else "all",
            ignore_forwards=self._handler.ignore_forwards,
            ignore_bots=self._handler.ignore_bots,
        )

    async def _on_new_message(self, event: events.NewMessage.Event) -> None:
        await self._handler.handle(event)
