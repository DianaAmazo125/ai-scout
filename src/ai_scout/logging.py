from __future__ import annotations

import logging
import sys

import structlog


def enable_utf8_stdout() -> None:
    """Чтобы кириллица в консоли Windows не превращалась в кракозябры."""

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def setup_logging(level: str = "INFO", json_logs: bool = False) -> None:
    """Единый формат для structlog и stdlib (Telethon, aiosqlite)."""

    enable_utf8_stdout()

    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    timestamper = (
        structlog.processors.TimeStamper(fmt="iso", utc=True)
        if json_logs
        else structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False)
    )

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer = (
        structlog.processors.JSONRenderer(ensure_ascii=False)
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric_level)

    # Не засоряем консоль служебными логами библиотек.
    logging.getLogger("telethon").setLevel(max(numeric_level, logging.WARNING))
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
