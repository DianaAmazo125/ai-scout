from pathlib import Path

import pytest

from ai_scout.config import ConfigError, load_config


def _write_config(tmp_path: Path, body: str) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    path = config_dir / "settings.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_load_config_resolves_relative_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "123456")
    monkeypatch.setenv("TELEGRAM_API_HASH", "0123456789abcdef0123456789abcdef")

    config_path = _write_config(
        tmp_path,
        """
telegram:
  source_chats:
    - "@freelance_chat"
    - -1001234567890
storage:
  db_path: data/test.db
""",
    )

    config = load_config(config_path)

    assert config.secrets.telegram_api_id == 123456
    assert config.telegram.source_chats == ["@freelance_chat", -1001234567890]
    assert config.storage.db_path == (tmp_path / "data" / "test.db").resolve()
    assert config.telegram.session_path == (tmp_path / "data" / "scout.session").resolve()


def test_missing_secrets_raise_config_error(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)

    config_path = _write_config(tmp_path, "telegram:\n  source_chats: []\n")

    with pytest.raises(ConfigError, match="не хватает секретов"):
        load_config(config_path)


def test_unknown_yaml_key_raises_config_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "123456")
    monkeypatch.setenv("TELEGRAM_API_HASH", "0123456789abcdef0123456789abcdef")

    config_path = _write_config(tmp_path, "telegram:\n  source_chatz: []\n")

    with pytest.raises(ConfigError, match="source_chatz"):
        load_config(config_path)
