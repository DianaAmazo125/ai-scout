from __future__ import annotations


def build_message_link(
    chat_id: int,
    message_id: int,
    username: str | None = None,
) -> str | None:
    """Ссылка на конкретное сообщение или на диалог с клиентом."""

    if username:
        return f"https://t.me/{username.lstrip('@')}/{message_id}"

    if chat_id < 0:
        raw = str(chat_id)
        # Супергруппы/каналы: -100<internal_id>
        if raw.startswith("-100") and len(raw) > 4:
            return f"https://t.me/c/{raw[4:]}/{message_id}"
        # Обычная группа без username — стабильной ссылки нет.
        return None

    if chat_id > 0:
        # Личный диалог: открыть чат с пользователем.
        return f"tg://openmessage?user_id={chat_id}"

    return None
