from __future__ import annotations

from datetime import UTC, datetime

from ai_scout.models import LeadStatus, RawMessage
from ai_scout.storage.db import Database


class LeadRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def save_raw_message(self, message: RawMessage) -> bool:
        """Сохранить сообщение. False — такой (chat_id, message_id) уже есть."""

        cursor = await self.db.conn.execute(
            """
            INSERT OR IGNORE INTO leads (
                chat_id, chat_title, message_id,
                sender_id, sender_username, sender_name,
                text, link, message_date, received_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.chat_id,
                message.chat_title,
                message.message_id,
                message.sender_id,
                message.sender_username,
                message.sender_name,
                message.text,
                message.link,
                message.date.isoformat(),
                datetime.now(UTC).isoformat(),
                LeadStatus.RECEIVED.value,
            ),
        )
        await self.db.conn.commit()
        return cursor.rowcount == 1

    async def total(self) -> int:
        cursor = await self.db.conn.execute("SELECT COUNT(*) AS count FROM leads")
        row = await cursor.fetchone()
        return int(row["count"]) if row else 0
