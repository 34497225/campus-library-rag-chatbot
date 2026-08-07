import pytest
from pydantic import ValidationError

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


def test_settings_require_jwt_secret_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 測試不能受到開發者電腦上真實環境變數影響。
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    settings = Settings(_env_file=None)

    with pytest.raises(
        RuntimeError,
        match="JWT_SECRET_KEY is not configured",
    ):
        settings.require_jwt_secret_key()


def test_settings_reject_short_jwt_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 這個測試值刻意不足 32 bytes，用來確認安全檢查有效。
    monkeypatch.setenv("JWT_SECRET_KEY", "too-short")
    settings = Settings(_env_file=None)

    with pytest.raises(
        RuntimeError,
        match="JWT_SECRET_KEY must be at least 32 bytes",
    ):
        settings.require_jwt_secret_key()


def test_settings_read_jwt_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 全部都是測試假值，不使用正式環境的 JWT secret。
    test_secret = "test-secret-key-for-settings-at-least-32-bytes"
    monkeypatch.setenv("JWT_SECRET_KEY", test_secret)
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "45")

    settings = Settings(_env_file=None)

    assert settings.require_jwt_secret_key() == test_secret
    assert settings.jwt_algorithm == "HS256"

    # 環境變數本來是字串 "45"；
    # Pydantic Settings 應自動將它轉換成整數 45。
    assert settings.access_token_expire_minutes == 45


@pytest.mark.parametrize(
    "invalid_minutes",
    [0, -1],
)
def test_settings_reject_non_positive_token_expiration(
    monkeypatch: pytest.MonkeyPatch,
    invalid_minutes: int,
) -> None:
    # 環境變數原本是字串，Pydantic 會先轉成 int，
    # 再確認它是否大於零。
    monkeypatch.setenv(
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        str(invalid_minutes),
    )

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
