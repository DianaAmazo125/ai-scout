from __future__ import annotations

from pathlib import Path

import aiosqlite
import structlog

log = structlog.get_logger(__name__)

SCHEMA_VERSION = 1

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS leads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id         INTEGER NOT NULL,
    chat_title      TEXT,
    message_id      INTEGER NOT NULL,
    sender_id       INTEGER,
    sender_username TEXT,
    sender_name     TEXT,
    text            TEXT NOT NULL,
    link            TEXT,
    message_date    TEXT NOT NULL,
    received_at     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'received',
    difficulty      INTEGER,
    fit             TEXT,
    verdict_json    TEXT,
    draft_reply     TEXT,
    sent_at         TEXT,
    UNIQUE(chat_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_received_at ON leads(received_at);
"""


class Database:
    """Одно долгоживущее подключение на процесс + простые миграции."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._in_memory = self.path == ":memory:"
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if not self._in_memory:
            clean_path = str(self.path).split("=")[-1].strip("'\" )").replace("WindowsPath(", "")
            Path(clean_path).parent.mkdir(parents=True, exist_ok=True)
            conn = await aiosqlite.connect(clean_path)
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA foreign_keys=ON")
            await conn.execute("PRAGMA busy_timeout=5000")
            self._conn = conn
            await self._migrate()
        else:
            conn = await aiosqlite.connect(self.path)
            conn.row_factory = aiosqlite.Row
            self._conn = conn
            await self._migrate()

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("база не подключена: сначала вызови Database.connect()")
        return self._conn

    async def _migrate(self) -> None:
        cursor = await self.conn.execute("PRAGMA user_version")
        row = await cursor.fetchone()
        version = int(row[0]) if row else 0

        if version == 0:
            await self.conn.executescript(SCHEMA_V1)
            await self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            await self.conn.commit()
            log.info("database_migrated", path=self.path, version=SCHEMA_VERSION)
        elif version > SCHEMA_VERSION:
            raise RuntimeError(f"база новее кода: schema={version}, ожидалось {SCHEMA_VERSION}")
        else:
            log.debug("database_ready", path=self.path, version=version)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
