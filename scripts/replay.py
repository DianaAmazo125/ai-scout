from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import structlog  # noqa: E402

from ai_scout.logging import enable_utf8_stdout, setup_logging  # noqa: E402
from ai_scout.storage.db import Database  # noqa: E402
from ai_scout.storage.repository import LeadRepository  # noqa: E402
from ai_scout.telegram.fakes import event_from_dict  # noqa: E402
from ai_scout.telegram.handler import MessageHandler  # noqa: E402

log = structlog.get_logger("replay")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Прогон фикстур через MessageHandler + SQLite. Без Telegram и без .env.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=ROOT / "tests" / "fixtures" / "messages.json",
        help="JSON {scenario: message}",
    )
    parser.add_argument(
        "--db",
        default=str(ROOT / "data" / "replay.db"),
        help="путь к SQLite или :memory:",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="удалить replay-БД перед прогоном",
    )
    parser.add_argument(
        "--keep-forwards",
        action="store_true",
        help="не отбрасывать пересланные сообщения",
    )
    parser.add_argument(
        "--keep-bots",
        action="store_true",
        help="не отбрасывать сообщения от ботов",
    )
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--json-logs", action="store_true")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    fixtures = json.loads(args.fixture.read_text(encoding="utf-8"))
    if not isinstance(fixtures, dict) or not fixtures:
        print("Фикстура должна быть непустым JSON-объектом {scenario: message}", file=sys.stderr)
        return 2

    db = Database(args.db)
    await db.connect()
    repo = LeadRepository(db)
    handler = MessageHandler(
        repo,
        ignore_forwards=not args.keep_forwards,
        ignore_bots=not args.keep_bots,
    )

    saved = duplicates = skipped = 0
    try:
        for name, payload in fixtures.items():
            result = await handler.handle(event_from_dict(payload))
            if result is None:
                skipped += 1
                log.info("replay_skipped", scenario=name)
            elif result.inserted:
                saved += 1
                log.info("replay_saved", scenario=name)
            else:
                duplicates += 1
                log.info("replay_duplicate", scenario=name)

        total = await repo.total()
    finally:
        await db.close()

    print(
        f"\nИтог: сценариев={len(fixtures)}, сохранено={saved}, "
        f"дублей={duplicates}, пропущено={skipped}, в БД={total}"
    )
    return 0


def main() -> int:
    enable_utf8_stdout()
    args = parse_args()
    setup_logging(args.log_level, args.json_logs)

    if args.reset and args.db != ":memory:":
        Path(args.db).unlink(missing_ok=True)

    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
