from ai_scout.telegram.resolver import build_message_link


def test_public_chat_uses_username() -> None:
    link = build_message_link(-1001234567890, 42, "@freelance_chat")
    assert link == "https://t.me/freelance_chat/42"


def test_private_supergroup_uses_internal_id() -> None:
    link = build_message_link(-1001234567890, 42)
    assert link == "https://t.me/c/1234567890/42"


def test_private_user_uses_openmessage() -> None:
    link = build_message_link(123456789, 7)
    assert link == "tg://openmessage?user_id=123456789"


def test_basic_group_without_username_has_no_link() -> None:
    assert build_message_link(-123456789, 7) is None
