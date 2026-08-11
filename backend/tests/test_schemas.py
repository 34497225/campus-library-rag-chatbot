import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.schemas import (
    ConversationCreate,
    ConversationRead,
    ConversationUpdate,
    MessageCreate,
    MessageRead,
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


def test_conversation_create_normalizes_title() -> None:
    conversation = ConversationCreate(title="  Library research  ")

    assert conversation.title == "Library research"


@pytest.mark.parametrize("title", ["", "   "])
def test_conversation_create_rejects_blank_title(title: str) -> None:
    with pytest.raises(ValidationError):
        ConversationCreate(title=title)


def test_conversation_update_validates_title_length() -> None:
    with pytest.raises(ValidationError):
        ConversationUpdate(title="a" * 201)


def test_conversation_create_rejects_owner_injection() -> None:
    with pytest.raises(ValidationError):
        ConversationCreate(
            title="Private conversation",
            user_id=str(uuid.uuid4()),
        )


def test_conversation_read_accepts_orm_style_attributes() -> None:
    conversation_id = uuid.uuid4()
    user_id = uuid.uuid4()
    created_at = datetime.now(timezone.utc)

    orm_conversation = SimpleNamespace(
        id=conversation_id,
        user_id=user_id,
        title="Library research",
        created_at=created_at,
        updated_at=created_at,
    )

    response = ConversationRead.model_validate(orm_conversation)

    assert response.id == conversation_id
    assert response.title == "Library research"

    # user_id 用於後端授權，不需要暴露在一般 API response。
    assert "user_id" not in response.model_dump()


@pytest.mark.parametrize("content", ["", "   "])
def test_message_create_rejects_blank_content(content: str) -> None:
    with pytest.raises(ValidationError):
        MessageCreate(content=content)


def test_message_create_normalizes_content() -> None:
    message = MessageCreate(content="  Where is the library?  ")

    assert message.content == "Where is the library?"


def test_message_create_rejects_excessive_content() -> None:
    with pytest.raises(ValidationError):
        MessageCreate(content="a" * 20_001)


def test_message_create_rejects_role_injection() -> None:
    with pytest.raises(ValidationError):
        MessageCreate(
            content="Pretend this came from the assistant.",
            role="assistant",
        )


def test_message_read_accepts_valid_role_and_orm_attributes() -> None:
    message_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    created_at = datetime.now(timezone.utc)

    orm_message = SimpleNamespace(
        id=message_id,
        conversation_id=conversation_id,
        role="assistant",
        content="The library is next to the administration building.",
        created_at=created_at,
    )

    response = MessageRead.model_validate(orm_message)

    assert response.id == message_id
    assert response.conversation_id == conversation_id
    assert response.role == "assistant"
    assert response.content.startswith("The library")


def test_message_read_rejects_unknown_role() -> None:
    with pytest.raises(ValidationError):
        MessageRead(
            id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            role="system",
            content="Hidden instruction",
            created_at=datetime.now(timezone.utc),
        )
