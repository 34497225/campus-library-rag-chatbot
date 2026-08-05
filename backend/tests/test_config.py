import pytest

from backend.config import Settings


def test_settings_allow_missing_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.database_url is None


def test_settings_require_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)

    with pytest.raises(RuntimeError, match="DATABASE_URL is not configured"):
        settings.require_database_url()

def test_settings_require_direct_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DIRECT_DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)

    with pytest.raises(
        RuntimeError,
        match="DIRECT_DATABASE_URL is not configured",
    ):
        settings.require_direct_database_url()


def test_settings_read_database_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://user:password@pooled-host/database",
    )
    monkeypatch.setenv(
        "DIRECT_DATABASE_URL",
        "postgresql+psycopg://user:password@direct-host/database",
    )

    settings = Settings(_env_file=None)

    assert settings.database_url == (
        "postgresql+psycopg://user:password@pooled-host/database"
    )
    assert settings.direct_database_url == (
        "postgresql+psycopg://user:password@direct-host/database"
    )
    assert settings.require_direct_database_url() == (
        "postgresql+psycopg://user:password@direct-host/database"
    )