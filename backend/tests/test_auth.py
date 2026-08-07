import uuid
from collections.abc import Generator
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.auth as auth
from backend.config import Settings
from backend.database import Base, get_db_session
from backend.dependencies import get_settings
from backend.main import app
from backend.repositories import get_user_by_email
from backend.security import (
    create_access_token,
    decode_access_token,
    verify_password,
)

# 測試只使用假 JWT secret，不讀取真實 .env。
TEST_SETTINGS = Settings(
    _env_file=None,
    jwt_secret_key="test-secret-key-for-auth-api-at-least-32-bytes",
    jwt_algorithm="HS256",
    access_token_expire_minutes=30,
)

@pytest.fixture
def client_and_engine() -> Generator[
    tuple[TestClient, Engine],
    None,
    None,
]:
    """Provide a FastAPI client backed by temporary SQLite."""

    # 使用記憶體 SQLite，測試不會連接正式 Neon。
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_get_db_session() -> Generator[
        Session,
        None,
        None,
    ]:
        # FastAPI 每個測試請求都取得獨立 Session，
        # 但共用同一個記憶體 SQLite engine。
        with Session(engine) as session:
            yield session

    # FastAPI dependency override 會取代正式 get_db_session，
    # 因此測試不需要 DATABASE_URL，也不會連到 Neon。
    app.dependency_overrides[get_db_session] = (
        override_get_db_session
    )

    app.dependency_overrides[get_settings] = lambda: TEST_SETTINGS

    try:
        with TestClient(app) as client:
            yield client, engine
    finally:
        # 測試結束一定要清除 override，
        # 避免影響其他測試檔案。
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_register_creates_user_with_hashed_password(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, engine = client_and_engine
    plaintext_password = "safe-password"

    response = client.post(
        "/auth/register",
        json={
            "email": "  Student@Example.COM  ",
            "password": plaintext_password,
        },
    )

    assert response.status_code == 201

    response_data = response.json()
    assert response_data["email"] == "student@example.com"
    assert "id" in response_data
    assert "created_at" in response_data

    # API 回應絕對不能包含明文密碼或 password_hash。
    assert "password" not in response_data
    assert "password_hash" not in response_data

    # 直接檢查隔離資料庫，確認保存的是可驗證的 Argon2 hash。
    with Session(engine) as session:
        stored_user = get_user_by_email(
            session,
            "student@example.com",
        )

        assert stored_user is not None
        assert stored_user.password_hash != plaintext_password
        assert verify_password(
            plaintext_password,
            stored_user.password_hash,
        ) is True


def test_register_rejects_duplicate_email(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine
    registration_data = {
        "email": "student@example.com",
        "password": "safe-password",
    }

    first_response = client.post(
        "/auth/register",
        json=registration_data,
    )
    second_response = client.post(
        "/auth/register",
        json=registration_data,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json() == {
        "detail": "Email is already registered."
    }


def test_register_rejects_duplicate_email_with_different_case(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine

    first_response = client.post(
        "/auth/register",
        json={
            "email": "Student@Example.com",
            "password": "safe-password",
        },
    )
    second_response = client.post(
        "/auth/register",
        json={
            "email": "student@example.COM",
            "password": "another-safe-password",
        },
    )

    # Schema 會將兩個 Email 都正規化為 student@example.com。
    assert first_response.status_code == 201
    assert second_response.status_code == 409


def test_register_rejects_invalid_email(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine

    response = client.post(
        "/auth/register",
        json={
            "email": "not-an-email",
            "password": "safe-password",
        },
    )

    # 422 表示 JSON 格式正確，但欄位未通過 Pydantic 驗證。
    assert response.status_code == 422


def test_register_rejects_short_password(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine

    response = client.post(
        "/auth/register",
        json={
            "email": "student@example.com",
            "password": "short",
        },
    )

    assert response.status_code == 422

def test_login_returns_access_token(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine

    register_response = client.post(
        "/auth/register",
        json={
            "email": "student@example.com",
            "password": "safe-password",
        },
    )

    assert register_response.status_code == 201
    registered_user_id = register_response.json()["id"]

    # 使用不同大小寫，確認 UserLogin schema 也會正規化 Email。
    login_response = client.post(
        "/auth/login",
        json={
            "email": "Student@Example.COM",
            "password": "safe-password",
        },
    )

    assert login_response.status_code == 200

    response_data = login_response.json()
    assert response_data["token_type"] == "bearer"
    assert isinstance(response_data["access_token"], str)

    # 解開測試 token，確認 sub 是剛註冊的使用者 ID。
    subject = decode_access_token(
        response_data["access_token"],
        TEST_SETTINGS,
    )

    assert subject == registered_user_id


def test_login_rejects_wrong_password(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine

    client.post(
        "/auth/register",
        json={
            "email": "student@example.com",
            "password": "correct-password",
        },
    )

    response = client.post(
        "/auth/login",
        json={
            "email": "student@example.com",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid email or password."
    }
    assert response.headers["www-authenticate"] == "Bearer"


def test_login_rejects_unknown_email(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine

    response = client.post(
        "/auth/login",
        json={
            "email": "missing@example.com",
            "password": "any-password",
        },
    )

    assert response.status_code == 401

    # 不存在帳號和錯誤密碼必須得到相同訊息，
    # 避免洩漏哪些 Email 已經註冊。
    assert response.json() == {
        "detail": "Invalid email or password."
    }
    assert response.headers["www-authenticate"] == "Bearer"

def test_login_unknown_email_still_verifies_password(
    client_and_engine: tuple[TestClient, Engine],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = client_and_engine

    # 用 mock 確認不存在帳號時仍呼叫 verify_password，
    # 不測量時間，因為時間測試在 CI 中容易不穩定。
    verify_password_mock = MagicMock(return_value=False)
    monkeypatch.setattr(
        auth,
        "verify_password",
        verify_password_mock,
    )

    response = client.post(
        "/auth/login",
        json={
            "email": "missing@example.com",
            "password": "any-password",
        },
    )

    assert response.status_code == 401
    verify_password_mock.assert_called_once()

    # 第二個參數應為有效的 Argon2 dummy hash。
    used_hash = verify_password_mock.call_args.args[1]
    assert used_hash.startswith("$argon2id$")

def test_me_returns_authenticated_user(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine

    register_response = client.post(
        "/auth/register",
        json={
            "email": "student@example.com",
            "password": "safe-password",
        },
    )
    login_response = client.post(
        "/auth/login",
        json={
            "email": "student@example.com",
            "password": "safe-password",
        },
    )

    access_token = login_response.json()["access_token"]

    response = client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {access_token}",
        },
    )

    assert response.status_code == 200

    response_data = response.json()
    assert response_data["id"] == register_response.json()["id"]
    assert response_data["email"] == "student@example.com"

    # /me 不得洩漏任何密碼相關欄位。
    assert "password" not in response_data
    assert "password_hash" not in response_data


def test_me_rejects_missing_token(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine

    response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Could not validate credentials."
    }
    assert response.headers["www-authenticate"] == "Bearer"


def test_me_rejects_invalid_token(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine

    response = client.get(
        "/auth/me",
        headers={
            "Authorization": "Bearer not-a-valid-jwt",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Could not validate credentials."
    }


def test_me_rejects_expired_token(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine

    expired_token = create_access_token(
        subject=str(uuid.uuid4()),
        settings=TEST_SETTINGS,
        # 建立時已經過期一秒。
        expires_delta=timedelta(seconds=-1),
    )

    response = client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {expired_token}",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Could not validate credentials."
    }


def test_me_rejects_token_for_missing_user(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine

    # 這個 token 簽章和期限都合法，
    # 但 sub 對應的使用者不存在於測試資料庫。
    token = create_access_token(
        subject=str(uuid.uuid4()),
        settings=TEST_SETTINGS,
    )

    response = client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Could not validate credentials."
    }

def test_me_rejects_non_uuid_subject(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine

    # Token 本身的簽章和期限合法，
    # 但 sub 無法轉換成 User.id 所需的 UUID。
    token = create_access_token(
        subject="not-a-valid-uuid",
        settings=TEST_SETTINGS,
    )

    response = client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Could not validate credentials."
    }


def test_me_rejects_non_bearer_authentication(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine

    # /auth/me 只接受 Bearer token，不接受 Basic authentication。
    response = client.get(
        "/auth/me",
        headers={
            "Authorization": "Basic fake-credentials",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Could not validate credentials."
    }
    assert response.headers["www-authenticate"] == "Bearer"
