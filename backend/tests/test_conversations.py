import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.config import Settings
from backend.database import Base, get_db_session
from backend.dependencies import get_settings
from backend.main import app
from backend.repositories import (
    get_conversation_for_owner,
    get_user_by_email,
)


# 測試只使用假的 JWT secret。
# _env_file=None 保證測試不會讀取真正的 .env。
TEST_SETTINGS = Settings(
    _env_file=None,
    jwt_secret_key=(
        "test-secret-key-for-conversation-api-at-least-32-bytes"
    ),
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

    # 使用記憶體 SQLite，避免測試連到 Neon。
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
        # API request 使用測試資料庫 Session，
        # 不使用 backend.database 中的正式 Neon engine。
        with Session(engine) as session:
            yield session

    # FastAPI dependency override 將正式依賴換成測試版本。
    app.dependency_overrides[get_db_session] = (
        override_get_db_session
    )
    app.dependency_overrides[get_settings] = lambda: TEST_SETTINGS

    try:
        with TestClient(app) as client:
            yield client, engine
    finally:
        # 測試結束後清除 override，避免污染其他測試。
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def register_and_login(
    client: TestClient,
    email: str = "student@example.com",
) -> str:
    """Create one test user and return its access token."""

    register_response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "safe-password",
        },
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "safe-password",
        },
    )
    assert login_response.status_code == 200

    return login_response.json()["access_token"]


def bearer_headers(access_token: str) -> dict[str, str]:
    """Build the Authorization header shared by protected API requests."""

    return {"Authorization": f"Bearer {access_token}"}


def create_conversation_via_api(
    client: TestClient,
    access_token: str,
    title: str,
) -> dict[str, str]:
    """Create one conversation and return its JSON response."""

    response = client.post(
        "/conversations",
        headers=bearer_headers(access_token),
        json={"title": title},
    )
    assert response.status_code == 201

    return response.json()


def test_create_conversation_for_authenticated_user(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, engine = client_and_engine
    access_token = register_and_login(client)

    response = client.post(
        "/conversations",
        headers={
            "Authorization": f"Bearer {access_token}",
        },
        json={
            "title": "  Library opening hours  ",
        },
    )

    assert response.status_code == 201

    response_data = response.json()

    # Schema 應去除標題前後空白。
    assert response_data["title"] == "Library opening hours"

    # Response 應包含對話的公開資訊。
    assert "id" in response_data
    assert "created_at" in response_data
    assert "updated_at" in response_data

    # user_id 是內部授權資料，不需要暴露給前端。
    assert "user_id" not in response_data

    # 直接檢查測試資料庫，確認對話真的屬於登入使用者。
    with Session(engine) as session:
        user = get_user_by_email(
            session,
            "student@example.com",
        )
        assert user is not None

        stored_conversation = get_conversation_for_owner(
            session=session,
            conversation_id=uuid.UUID(response_data["id"]),
            owner_id=user.id,
        )

        assert stored_conversation is not None
        assert stored_conversation.title == "Library opening hours"


def test_create_conversation_rejects_missing_token(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine

    response = client.post(
        "/conversations",
        json={
            "title": "Unauthenticated conversation",
        },
    )

    # get_current_user 會在 endpoint 寫入資料前拒絕請求。
    assert response.status_code == 401
    assert response.json() == {
        "detail": "Could not validate credentials."
    }


def test_create_conversation_rejects_owner_injection(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine
    access_token = register_and_login(client)

    response = client.post(
        "/conversations",
        headers={
            "Authorization": f"Bearer {access_token}",
        },
        json={
            "title": "Injected owner",
            "user_id": str(uuid.uuid4()),
        },
    )

    # ConversationCreate 設定 extra="forbid"，
    # 因此額外傳入 user_id 會得到 validation error。
    assert response.status_code == 422


def test_list_conversations_returns_empty_list_for_new_user(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine
    access_token = register_and_login(client)

    response = client.get(
        "/conversations",
        headers=bearer_headers(access_token),
    )

    assert response.status_code == 200
    assert response.json() == []


def test_list_conversations_returns_only_owned_records(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine
    owner_token = register_and_login(client, "owner@example.com")

    create_conversation_via_api(client, owner_token, "First conversation")
    create_conversation_via_api(client, owner_token, "Second conversation")

    other_token = register_and_login(client, "other@example.com")
    create_conversation_via_api(
        client,
        other_token,
        "Other user's conversation",
    )

    response = client.get(
        "/conversations",
        headers=bearer_headers(owner_token),
    )

    assert response.status_code == 200
    response_data = response.json()

    assert {item["title"] for item in response_data} == {
        "First conversation",
        "Second conversation",
    }
    assert all("user_id" not in item for item in response_data)


def test_read_conversation_returns_owned_record(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine
    access_token = register_and_login(client)
    created = create_conversation_via_api(
        client,
        access_token,
        "My private conversation",
    )

    response = client.get(
        f"/conversations/{created['id']}",
        headers=bearer_headers(access_token),
    )

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["title"] == "My private conversation"
    assert "user_id" not in response.json()


def test_read_conversation_hides_other_owners_records(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine
    owner_token = register_and_login(client, "owner@example.com")
    private_conversation = create_conversation_via_api(
        client,
        owner_token,
        "Owner only",
    )
    other_token = register_and_login(client, "other@example.com")

    inaccessible_response = client.get(
        f"/conversations/{private_conversation['id']}",
        headers=bearer_headers(other_token),
    )
    missing_response = client.get(
        f"/conversations/{uuid.uuid4()}",
        headers=bearer_headers(other_token),
    )

    expected_error = {"detail": "Conversation not found."}
    assert inaccessible_response.status_code == 404
    assert missing_response.status_code == 404
    assert inaccessible_response.json() == expected_error
    assert missing_response.json() == expected_error


def test_owner_can_rename_conversation(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine
    access_token = register_and_login(client)
    created = create_conversation_via_api(
        client,
        access_token,
        "Original title",
    )

    response = client.patch(
        f"/conversations/{created['id']}",
        headers=bearer_headers(access_token),
        json={"title": "  Renamed conversation  "},
    )

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["title"] == "Renamed conversation"


def test_rename_conversation_hides_other_owners_records(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine
    owner_token = register_and_login(client, "owner@example.com")
    created = create_conversation_via_api(client, owner_token, "Private")
    other_token = register_and_login(client, "other@example.com")

    response = client.patch(
        f"/conversations/{created['id']}",
        headers=bearer_headers(other_token),
        json={"title": "Unauthorized rename"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Conversation not found."}

    # 原擁有者再次讀取，確認攻擊者沒有修改資料。
    owner_response = client.get(
        f"/conversations/{created['id']}",
        headers=bearer_headers(owner_token),
    )
    assert owner_response.status_code == 200
    assert owner_response.json()["title"] == "Private"


def test_owner_can_delete_conversation(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine
    access_token = register_and_login(client)
    created = create_conversation_via_api(client, access_token, "Delete me")

    response = client.delete(
        f"/conversations/{created['id']}",
        headers=bearer_headers(access_token),
    )

    assert response.status_code == 204
    assert response.content == b""

    read_response = client.get(
        f"/conversations/{created['id']}",
        headers=bearer_headers(access_token),
    )
    assert read_response.status_code == 404


def test_delete_conversation_hides_other_owners_records(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine
    owner_token = register_and_login(client, "owner@example.com")
    created = create_conversation_via_api(client, owner_token, "Private")
    other_token = register_and_login(client, "other@example.com")

    response = client.delete(
        f"/conversations/{created['id']}",
        headers=bearer_headers(other_token),
    )

    assert response.status_code == 404

    # 別人刪除失敗後，原擁有者的資料仍存在。
    owner_response = client.get(
        f"/conversations/{created['id']}",
        headers=bearer_headers(owner_token),
    )
    assert owner_response.status_code == 200


def test_owner_can_create_user_message_without_role_injection(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine
    access_token = register_and_login(client)
    created = create_conversation_via_api(client, access_token, "Messages")
    message_url = f"/conversations/{created['id']}/messages"

    response = client.post(
        message_url,
        headers=bearer_headers(access_token),
        json={"content": "  Where is the library?  "},
    )

    assert response.status_code == 201
    assert response.json()["conversation_id"] == created["id"]
    assert response.json()["role"] == "user"
    assert response.json()["content"] == "Where is the library?"

    # role 是伺服器權限，不允許用戶端冒充 assistant。
    injected_response = client.post(
        message_url,
        headers=bearer_headers(access_token),
        json={
            "content": "Fake assistant answer",
            "role": "assistant",
        },
    )
    assert injected_response.status_code == 422


def test_owner_can_list_messages_and_empty_conversation(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine
    access_token = register_and_login(client)
    created = create_conversation_via_api(client, access_token, "Messages")
    message_url = f"/conversations/{created['id']}/messages"

    empty_response = client.get(
        message_url,
        headers=bearer_headers(access_token),
    )
    assert empty_response.status_code == 200
    assert empty_response.json() == []

    for content in ["First question", "Second question"]:
        response = client.post(
            message_url,
            headers=bearer_headers(access_token),
            json={"content": content},
        )
        assert response.status_code == 201

    list_response = client.get(
        message_url,
        headers=bearer_headers(access_token),
    )

    assert list_response.status_code == 200
    assert {message["content"] for message in list_response.json()} == {
        "First question",
        "Second question",
    }
    assert all(
        message["role"] == "user"
        for message in list_response.json()
    )


def test_owner_can_persist_assistant_message_without_role_field(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    """The dedicated endpoint should choose the assistant role server-side."""

    client, _ = client_and_engine
    access_token = register_and_login(client)
    created = create_conversation_via_api(client, access_token, "RAG chat")
    assistant_url = (
        f"/conversations/{created['id']}/messages/assistant"
    )

    response = client.post(
        assistant_url,
        headers=bearer_headers(access_token),
        json={"content": "  The library closes at 9 PM.  "},
    )

    assert response.status_code == 201
    assert response.json()["role"] == "assistant"
    assert response.json()["content"] == "The library closes at 9 PM."

    injected_response = client.post(
        assistant_url,
        headers=bearer_headers(access_token),
        json={"content": "Fake", "role": "user"},
    )
    assert injected_response.status_code == 422


def test_assistant_message_endpoint_hides_other_owner_conversation(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    """A second account must receive the same 404 as a missing resource."""

    client, _ = client_and_engine
    owner_token = register_and_login(client, "owner@example.com")
    created = create_conversation_via_api(client, owner_token, "Private")
    other_token = register_and_login(client, "other@example.com")

    response = client.post(
        f"/conversations/{created['id']}/messages/assistant",
        headers=bearer_headers(other_token),
        json={"content": "Unauthorized answer"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Conversation not found."}


def test_message_endpoints_hide_other_owners_conversation(
    client_and_engine: tuple[TestClient, Engine],
) -> None:
    client, _ = client_and_engine
    owner_token = register_and_login(client, "owner@example.com")
    created = create_conversation_via_api(client, owner_token, "Private")
    other_token = register_and_login(client, "other@example.com")
    message_url = f"/conversations/{created['id']}/messages"

    create_response = client.post(
        message_url,
        headers=bearer_headers(other_token),
        json={"content": "Unauthorized message"},
    )
    list_response = client.get(
        message_url,
        headers=bearer_headers(other_token),
    )

    expected_error = {"detail": "Conversation not found."}
    assert create_response.status_code == 404
    assert list_response.status_code == 404
    assert create_response.json() == expected_error
    assert list_response.json() == expected_error


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("GET", "/conversations", None),
        ("GET", f"/conversations/{uuid.uuid4()}", None),
        (
            "PATCH",
            f"/conversations/{uuid.uuid4()}",
            {"title": "No authentication"},
        ),
        ("DELETE", f"/conversations/{uuid.uuid4()}", None),
        (
            "POST",
            f"/conversations/{uuid.uuid4()}/messages",
            {"content": "No authentication"},
        ),
        (
            "POST",
            f"/conversations/{uuid.uuid4()}/messages/assistant",
            {"content": "No authentication"},
        ),
        ("GET", f"/conversations/{uuid.uuid4()}/messages", None),
    ],
)
def test_conversation_endpoints_require_authentication(
    client_and_engine: tuple[TestClient, Engine],
    method: str,
    path: str,
    json_body: dict[str, str] | None,
) -> None:
    client, _ = client_and_engine

    response = client.request(
        method,
        path,
        json=json_body,
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Could not validate credentials."
    }
