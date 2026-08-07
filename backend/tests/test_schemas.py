import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.schemas import (
    TokenResponse,
    UserCreate,
    UserLogin,
    UserRead,
)


def test_user_create_normalizes_email() -> None:
    user = UserCreate(
        email="  Student@Example.COM  ",
        password="safe-password",
    )

    assert user.email == "student@example.com"


def test_user_create_preserves_password_whitespace() -> None:
    # 密碼前後的空白可能是使用者刻意設定的內容，不能自動刪除。
    password = "  safe-password  "

    user = UserCreate(
        email="student@example.com",
        password=password,
    )

    assert user.password == password


def test_user_create_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        UserCreate(
            email="not-an-email",
            password="safe-password",
        )


def test_user_create_rejects_short_password() -> None:
    with pytest.raises(ValidationError):
        UserCreate(
            email="student@example.com",
            password="short",
        )


def test_user_login_rejects_empty_password() -> None:
    with pytest.raises(ValidationError):
        UserLogin(
            email="student@example.com",
            password="",
        )


def test_user_read_accepts_orm_style_attributes() -> None:
    user_id = uuid.uuid4()
    created_at = datetime.now(timezone.utc)

    # SimpleNamespace 模擬具有屬性的 SQLAlchemy ORM 物件，
    # 不需要連接真正的 Neon 資料庫。
    orm_user = SimpleNamespace(
        id=user_id,
        email="student@example.com",
        password_hash="must-never-appear-in-response",
        created_at=created_at,
    )

    response = UserRead.model_validate(orm_user)

    assert response.id == user_id
    assert response.email == "student@example.com"
    assert response.created_at == created_at

    # UserRead 沒有宣告 password_hash，因此不會出現在 API 輸出。
    assert "password_hash" not in response.model_dump()


def test_token_response_uses_bearer_type() -> None:
    response = TokenResponse(access_token="fake-token-for-testing")

    assert response.access_token == "fake-token-for-testing"
    assert response.token_type == "bearer"
