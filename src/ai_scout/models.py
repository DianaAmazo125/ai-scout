from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class LeadStatus(StrEnum):
    RECEIVED = "received"
    FILTERED_OUT = "filtered_out"
    EVALUATED = "evaluated"
    SENT = "sent"
    FAILED = "failed"


class RawMessage(BaseModel):
    """Сообщение из Telegram в том виде, в котором оно попадает в БД."""

    model_config = ConfigDict(frozen=True)

    chat_id: int
    chat_title: str
    message_id: int
    sender_id: int | None = None
    sender_username: str | None = None
    sender_name: str | None = None
    text: str
    date: datetime
    link: str | None = None
