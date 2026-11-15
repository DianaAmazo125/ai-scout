from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CONFIG_PATH = Path("config/settings.yaml")


class ConfigError(RuntimeError):
    """Понятная ошибка конфигурации вместо трейсбека pydantic."""


class StrictModel(BaseModel):
    """Запрещаем опечатки в YAML: лишний ключ — ошибка на старте."""

    model_config = ConfigDict(extra="forbid")


class Secrets(BaseSettings):
    """Секреты только из окружения / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    telegram_api_id: int
    telegram_api_hash: str = Field(min_length=8)
    telegram_phone: str | None = None
    telegram_bot_token: str | None = None
    telegram_notify_chat_id: int | None = None
    anthropic_api_key: str | None = None

    @field_validator(
        "telegram_phone",
        "telegram_bot_token",
        "anthropic_api_key",
        mode="before",
    )
    @classmethod
    def _empty_str_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("telegram_notify_chat_id", mode="before")
    @classmethod
    def _empty_int_to_none(cls, value: Any) -> Any:
        if value is None or value == "":
            return None
        return value


class TelegramConfig(StrictModel):
    session_path: Path = Path("data/scout.session")
    source_chats: list[str | int] = Field(default_factory=list)
    ignore_forwards: bool = True
    ignore_bots: bool = True
    catch_up: bool = False

    @field_validator("source_chats")
    @classmethod
    def _clean_chats(cls, value: list[str | int]) -> list[str | int]:
        cleaned: list[str | int] = []
        for item in value:
            if isinstance(item, str):
                item = item.strip()
                if not item:
                    continue
            cleaned.append(item)
        return cleaned


class StorageConfig(StrictModel):
    db_path: Path = Path("data/scout.db")


class FiltersConfig(StrictModel):
    whitelist: list[str] = Field(default_factory=list)
    stopwords: list[str] = Field(default_factory=list)
    min_length: int = 40
    max_length: int = 4000


class AIConfig(StrictModel):
    model: str = "claude-sonnet-4-5"
    max_difficulty: int = 3
    max_input_chars: int = 4000
    concurrency: int = 2
    daily_budget_usd: float = 3.0


class PipelineConfig(StrictModel):
    queue_size: int = 200
    workers: int = 2


class LoggingConfig(StrictModel):
    level: str = "INFO"
    json_logs: bool = False


class AppConfig(StrictModel):
    project_root: Path
    secrets: Secrets
    telegram: TelegramConfig
    storage: StorageConfig
    filters: FiltersConfig = Field(default_factory=FiltersConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def _default_config_path() -> Path:
    env_path = os.getenv("AI_SCOUT_CONFIG")
    if env_path:
        return Path(env_path).expanduser()

    cwd_candidate = Path.cwd() / DEFAULT_CONFIG_PATH
    if cwd_candidate.exists():
        return cwd_candidate

    # editable-install: src/ai_scout/config.py -> <project root>
    return Path(__file__).resolve().parents[2] / DEFAULT_CONFIG_PATH


def _resolve_path(path: Path, base: Path) -> Path:
    path = path.expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def _format_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error["loc"]) or "<root>"
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts)


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path).expanduser() if path else _default_config_path()
    config_path = config_path.resolve()

    if not config_path.exists():
        raise ConfigError(
            f"не найден файл настроек: {config_path}. Запусти из корня проекта или укажи --config."
        )

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"не удалось разобрать {config_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"корень {config_path.name} должен быть словарём")

    project_root = config_path.parent.parent
    env_file = project_root / ".env"

    try:
        secrets = Secrets(_env_file=str(env_file) if env_file.exists() else None)
    except ValidationError as exc:
        raise ConfigError(
            "не хватает секретов: "
            f"{_format_validation_error(exc)}. "
            "Скопируй .env.example в .env и заполни."
        ) from exc

    try:
        telegram = TelegramConfig(**raw.get("telegram", {}))
        storage = StorageConfig(**raw.get("storage", {}))
        filters = FiltersConfig(**raw.get("filters", {}))
        ai = AIConfig(**raw.get("ai", {}))
        pipeline = PipelineConfig(**raw.get("pipeline", {}))
        logging_config = LoggingConfig(**raw.get("logging", {}))
    except ValidationError as exc:
        raise ConfigError(f"ошибка в {config_path}: {_format_validation_error(exc)}") from exc

    telegram.session_path = _resolve_path(telegram.session_path, project_root)
    storage.db_path = _resolve_path(storage.db_path, project_root)

    return AppConfig(
        project_root=project_root,
        secrets=secrets,
        telegram=telegram,
        storage=storage,
        filters=filters,
        ai=ai,
        pipeline=pipeline,
        logging=logging_config,
    )
