from __future__ import annotations

import asyncio
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import structlog  # noqa: E402
from telethon import TelegramClient  # noqa: E402

from ai_scout.logging import enable_utf8_stdout, setup_logging  # noqa: E402

log = structlog.get_logger("login")


def load_env_direct(env_path: Path) -> None:
    """Читает ключи напрямую из .env без внешних библиотек и YAML."""
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


async def main() -> int:
    enable_utf8_stdout()
    setup_logging("INFO", False)
    load_env_direct(ROOT / ".env")

    api_id_raw = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    phone = os.getenv("TELEGRAM_PHONE", "").strip()

    if not api_id_raw or not api_hash or not phone:
        print("Ошибка: в .env не заполнены TELEGRAM_API_ID, TELEGRAM_API_HASH или TELEGRAM_PHONE", file=sys.stderr)
        return 2

    session_path = ROOT / "data" / "scout_session"
    session_path.parent.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(
        str(session_path),
        int(api_id_raw),
        api_hash,
        device_model="Desktop",
        system_version="Windows 10",
        app_version="5.8.0",
        lang_code="ru",
        system_lang_code="ru-RU",
    )


    try:
        print(f"Вход в Telegram для номера {phone}. Код придёт в приложение/чат от Telegram.")
        await client.start(
            phone=phone,
            password=lambda: getpass.getpass("Пароль 2FA (если включён): "),
        )
        me = await client.get_me()
        log.info(
            "login_ok",
            user_id=me.id,
            username=me.username,
            name=me.first_name,
            session=f"{session_path}.session",
        )
        print(f"\nГотово! Сессия сохранена: {session_path}.session")
        return 0
    except Exception:
        log.exception("login_failed")
        return 1
    finally:
        if client.is_connected():
            await client.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
