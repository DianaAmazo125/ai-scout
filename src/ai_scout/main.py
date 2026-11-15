from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

import structlog
from telethon import TelegramClient

from ai_scout.config import AppConfig, ConfigError, load_config
from ai_scout.logging import enable_utf8_stdout, setup_logging
from ai_scout.storage.db import Database
from ai_scout.storage.repository import LeadRepository
from ai_scout.telegram.handler import MessageHandler
from ai_scout.telegram.listener import TelegramListener, resolve_chats

log = structlog.get_logger(__name__)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ai-scout",
        description="AI-скаут: слушает фриланс-чаты Telegram и логирует новые сообщения.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="путь к settings.yaml (по умолчанию config/settings.yaml)",
    )
    parser.add_argument(
        "--chat",
        action="append",
        default=[],
        metavar="CHAT",
        help="@username или числовой ID чата; можно указать несколько раз",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="слушать все входящие сообщения (удобно для первого теста)",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help="DEBUG / INFO / WARNING / ERROR",
    )
    parser.add_argument(
        "--json-logs",
        action="store_true",
        help="писать логи в JSON (для дальнейшего парсинга)",
    )
    return parser.parse_args(argv)


async def run(config: AppConfig, chats: Sequence[str | int], listen_all: bool) -> int:
    db = Database(config.storage.db_path)
    await db.connect()
    repo = LeadRepository(db)

    session_path = config.telegram.session_path
    session_path.parent.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(
        str(session_path),
        config.secrets.telegram_api_id,
        config.secrets.telegram_api_hash,
        catch_up=config.telegram.catch_up,
    )

    try:
        await client.connect()
        if not await client.is_user_authorized():
            log.error(
                "session_not_authorized",
                session=str(session_path),
                hint="запусти: python scripts/login.py",
            )
            return 2

        me = await client.get_me()
        log.info(
            "telegram_connected",
            user_id=me.id,
            username=me.username,
            name=me.first_name,
        )

        watched = None
        if listen_all:
            log.warning("watch_all_incoming", reason="флаг --all")
        else:
            watched = await resolve_chats(client, chats)
            if not watched:
                log.error(
                    "no_chats_resolved",
                    hint="проверь source_chats/--chat; аккаунт должен состоять в этих чатах",
                )
                return 2

        handler = MessageHandler(
            repo=repo,
            ignore_forwards=config.telegram.ignore_forwards,
            ignore_bots=config.telegram.ignore_bots,
        )
        listener = TelegramListener(client=client, chats=watched, handler=handler)
        listener.register()

        log.info(
            "scout_running",
            db=str(config.storage.db_path),
            session=str(session_path),
            stop="Ctrl+C",
        )
        await client.run_until_disconnected()
        return 0
    finally:
        if client.is_connected():
            await client.disconnect()
        await db.close()


def cli(argv: Sequence[str] | None = None) -> int:
    enable_utf8_stdout()
    args = _parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 2

    setup_logging(
        level=args.log_level or config.logging.level,
        json_logs=args.json_logs or config.logging.json_logs,
    )

    chats: list[str | int] = list(args.chat) if args.chat else list(config.telegram.source_chats)

    if not chats and not args.all:
        log.error(
            "no_chats_configured",
            hint=(
                "добавь source_chats в config/settings.yaml, "
                "укажи --chat @username или запусти с --all"
            ),
        )
        return 2

    if args.all and chats:
        log.warning("all_mode_overrides_chats", ignored=len(chats))

    try:
        return asyncio.run(run(config, chats, args.all))
    except KeyboardInterrupt:
        log.info("scout_stopped")
        return 0
    except Exception:
        log.exception("scout_failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(cli())
