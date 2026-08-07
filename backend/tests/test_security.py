from datetime import timedelta

from backend.config import Settings
from backend.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_creates_argon2id_hash() -> None:
    password = "correct-horse-battery-staple"

    password_hash = hash_password(password)

    assert password_hash.startswith("$argon2id$")
    assert password_hash != password


def test_hash_password_uses_a_unique_salt() -> None:
    password = "same-password"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != second_hash


def test_verify_password_accepts_correct_password() -> None:
    password_hash = hash_password("correct-password")

    assert verify_password("correct-password", password_hash) is True


def test_verify_password_rejects_wrong_password() -> None:
    password_hash = hash_password("correct-password")

    assert verify_password("wrong-password", password_hash) is False


def test_verify_password_rejects_invalid_hash() -> None:
    assert verify_password("any-password", "not-an-argon2-hash") is False


# 測試使用獨立假設定，不讀取開發者電腦上的真實 .env。
TEST_SETTINGS = Settings(
    _env_file=None,
    jwt_secret_key="test-secret-key-for-unit-tests-at-least-32-bytes",
    jwt_algorithm="HS256",
    access_token_expire_minutes=30,
)

# 另一組合法但內容不同的設定，用來測試錯誤簽章。
WRONG_SECRET_SETTINGS = Settings(
    _env_file=None,
    jwt_secret_key="wrong-test-key-for-unit-tests-at-least-32-bytes",
    jwt_algorithm="HS256",
    access_token_expire_minutes=30,
)


def test_access_token_returns_its_subject() -> None:
    # 使用測試設定建立 token。
    token = create_access_token(
        subject="user-123",
        settings=TEST_SETTINGS,
    )

    # 使用同一組設定驗證後，應取得原本的 sub。
    assert decode_access_token(token, TEST_SETTINGS) == "user-123"


def test_access_token_rejects_wrong_secret() -> None:
    token = create_access_token(
        subject="user-123",
        settings=TEST_SETTINGS,
    )

    # 使用不同 secret 驗證，簽章不符，應回傳 None。
    assert decode_access_token(token, WRONG_SECRET_SETTINGS) is None


def test_access_token_rejects_expired_token() -> None:
    token = create_access_token(
        subject="user-123",
        settings=TEST_SETTINGS,
        # 負一秒代表 token 建立時就已過期。
        expires_delta=timedelta(seconds=-1),
    )

    assert decode_access_token(token, TEST_SETTINGS) is None


def test_access_token_rejects_invalid_token() -> None:
    # 這不是合法 JWT 格式，應安全地回傳 None。
    assert decode_access_token(
        "not-a-valid-jwt",
        TEST_SETTINGS,
    ) is None
