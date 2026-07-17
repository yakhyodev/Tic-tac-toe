import pytest

from config import Settings


def set_required(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:token")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("WEBHOOK_BASE_URL", "https://bot.example.com")
    monkeypatch.delenv("WEBHOOK_URL", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")


def test_production_requires_webhook_secret(monkeypatch):
    set_required(monkeypatch)
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="WEBHOOK_SECRET"):
        Settings.from_env()


def test_webhook_url_is_composed_and_secret_validated(monkeypatch):
    set_required(monkeypatch)
    monkeypatch.setenv("WEBHOOK_SECRET", "Valid_secret-123")
    monkeypatch.setenv("WEBHOOK_PATH", "telegram")
    settings = Settings.from_env()
    assert settings.webhook_path == "/telegram"
    assert settings.webhook_url == "https://bot.example.com/telegram"


def test_production_rejects_non_https_webhook(monkeypatch):
    set_required(monkeypatch)
    monkeypatch.setenv("WEBHOOK_BASE_URL", "http://bot.example.com")
    monkeypatch.setenv("WEBHOOK_SECRET", "Valid_secret-123")
    with pytest.raises(RuntimeError, match="HTTPS"):
        Settings.from_env()
