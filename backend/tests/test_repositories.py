from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.models import Conversation, Message, User
from backend.repositories import (
    create_conversation,
    create_message_for_owner,
    create_user,
    delete_conversation_for_owner,
    get_conversation_for_owner,
    get_user_by_email,
    get_user_by_id,
    list_conversations_for_owner,
    list_messages_for_owner,
    rename_conversation_for_owner,
)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Create a temporary SQLite database for each test."""

    # :memory: 代表資料庫只存在記憶體，不會建立實體檔案。
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite does not enforce foreign keys unless this PRAGMA is enabled for
    # the connection. Production PostgreSQL enforces them by default.
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")

    # 依照 SQLAlchemy ORM metadata 建立所有測試資料表。
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    # 測試結束後清除 schema 並釋放 engine。
    Base.metadata.drop_all(engine)
    engine.dispose()


def create_test_user(
    session: Session,
    email: str,
) -> User:
    """Create a user for isolated repository tests."""

    return create_user(
        session=session,
        email=email,
        password_hash="$argon2id$fake-hash-for-repository-test",
    )


def test_create_user_persists_hashed_password(
    db_session: Session,
) -> None:
    password_hash = "$argon2id$fake-hash-for-database-test"

    user = create_user(
        session=db_session,
        email="student@example.com",
        password_hash=password_hash,
    )

    assert user.id is not None
    assert user.email == "student@example.com"
    assert user.password_hash == password_hash
    assert user.created_at is not None


def test_get_user_by_email_returns_existing_user(
    db_session: Session,
) -> None:
    created_user = create_user(
        session=db_session,
        email="student@example.com",
        password_hash="$argon2id$fake-hash",
    )

    found_user = get_user_by_email(
        db_session,
        "student@example.com",
    )

    assert found_user is not None
    assert found_user.id == created_user.id


def test_get_user_by_id_returns_existing_user(
    db_session: Session,
) -> None:
    created_user = create_user(
        session=db_session,
        email="student@example.com",
        password_hash="$argon2id$fake-hash",
    )

    found_user = get_user_by_id(
        db_session,
        created_user.id,
    )

    assert found_user is not None
    assert found_user.email == "student@example.com"


def test_queries_return_none_for_missing_user(
    db_session: Session,
) -> None:
    # 沒有符合資料時，repository 應回傳 None，
    # 不應把 NoResultFound 例外交給 API。
    assert get_user_by_email(
        db_session,
        "missing@example.com",
    ) is None


def test_create_user_rolls_back_duplicate_email(
    db_session: Session,
) -> None:
    create_user(
        session=db_session,
        email="student@example.com",
        password_hash="$argon2id$first-fake-hash",
    )

    # 第二次插入相同 Email 應觸發資料庫唯一限制。
    with pytest.raises(IntegrityError):
        create_user(
            session=db_session,
            email="student@example.com",
            password_hash="$argon2id$second-fake-hash",
        )

    # create_user() 已 rollback，所以失敗後 Session 仍能查詢。
    existing_user = get_user_by_email(
        db_session,
        "student@example.com",
    )

    assert existing_user is not None
    assert existing_user.password_hash == "$argon2id$first-fake-hash"


def test_create_conversation_assigns_owner(
    db_session: Session,
) -> None:
    owner = create_test_user(
        db_session,
        "owner@example.com",
    )

    conversation = create_conversation(
        session=db_session,
        owner_id=owner.id,
        title="Library research",
    )

    assert conversation.id is not None
    assert conversation.user_id == owner.id
    assert conversation.title == "Library research"
    assert conversation.created_at is not None
    assert conversation.updated_at is not None


def test_list_conversations_returns_only_owned_records(
    db_session: Session,
) -> None:
    owner_a = create_test_user(
        db_session,
        "owner-a@example.com",
    )
    owner_b = create_test_user(
        db_session,
        "owner-b@example.com",
    )

    conversation_a = create_conversation(
        db_session,
        owner_a.id,
        "Owner A conversation",
    )
    create_conversation(
        db_session,
        owner_b.id,
        "Owner B conversation",
    )

    result = list_conversations_for_owner(
        db_session,
        owner_a.id,
    )

    assert [conversation.id for conversation in result] == [
        conversation_a.id
    ]


def test_get_conversation_rejects_different_owner(
    db_session: Session,
) -> None:
    owner_a = create_test_user(
        db_session,
        "owner-a@example.com",
    )
    owner_b = create_test_user(
        db_session,
        "owner-b@example.com",
    )
    conversation = create_conversation(
        db_session,
        owner_a.id,
        "Private conversation",
    )

    result = get_conversation_for_owner(
        session=db_session,
        conversation_id=conversation.id,
        owner_id=owner_b.id,
    )

    assert result is None


def test_rename_conversation_rejects_different_owner(
    db_session: Session,
) -> None:
    owner_a = create_test_user(
        db_session,
        "owner-a@example.com",
    )
    owner_b = create_test_user(
        db_session,
        "owner-b@example.com",
    )
    conversation = create_conversation(
        db_session,
        owner_a.id,
        "Original title",
    )

    result = rename_conversation_for_owner(
        session=db_session,
        conversation_id=conversation.id,
        owner_id=owner_b.id,
        title="Unauthorized title",
    )

    assert result is None

    # 重新用真正擁有者查詢，確認標題沒有被竄改。
    unchanged = get_conversation_for_owner(
        db_session,
        conversation.id,
        owner_a.id,
    )
    assert unchanged is not None
    assert unchanged.title == "Original title"


def test_delete_conversation_rejects_different_owner(
    db_session: Session,
) -> None:
    owner_a = create_test_user(
        db_session,
        "owner-a@example.com",
    )
    owner_b = create_test_user(
        db_session,
        "owner-b@example.com",
    )
    conversation = create_conversation(
        db_session,
        owner_a.id,
        "Must remain private",
    )

    deleted = delete_conversation_for_owner(
        session=db_session,
        conversation_id=conversation.id,
        owner_id=owner_b.id,
    )

    assert deleted is False

    # 未授權刪除失敗後，真正擁有者仍能讀到資料。
    remaining = get_conversation_for_owner(
        db_session,
        conversation.id,
        owner_a.id,
    )
    assert remaining is not None


def test_owner_can_rename_and_delete_conversation(
    db_session: Session,
) -> None:
    owner = create_test_user(
        db_session,
        "owner@example.com",
    )
    conversation = create_conversation(
        db_session,
        owner.id,
        "Original title",
    )

    renamed = rename_conversation_for_owner(
        session=db_session,
        conversation_id=conversation.id,
        owner_id=owner.id,
        title="Updated title",
    )

    assert renamed is not None
    assert renamed.title == "Updated title"

    deleted = delete_conversation_for_owner(
        session=db_session,
        conversation_id=conversation.id,
        owner_id=owner.id,
    )

    assert deleted is True
    assert get_conversation_for_owner(
        db_session,
        conversation.id,
        owner.id,
    ) is None


def test_owner_can_create_and_list_messages(
    db_session: Session,
) -> None:
    owner = create_test_user(db_session, "owner@example.com")
    conversation = create_conversation(
        db_session,
        owner.id,
        "Library hours",
    )

    user_message = create_message_for_owner(
        session=db_session,
        conversation_id=conversation.id,
        owner_id=owner.id,
        role="user",
        content="When does the library close?",
    )
    assistant_message = create_message_for_owner(
        session=db_session,
        conversation_id=conversation.id,
        owner_id=owner.id,
        role="assistant",
        content="The library closes at 9 PM.",
    )

    messages = list_messages_for_owner(
        session=db_session,
        conversation_id=conversation.id,
        owner_id=owner.id,
    )

    assert user_message is not None
    assert assistant_message is not None
    assert messages is not None
    assert {message.id for message in messages} == {
        user_message.id,
        assistant_message.id,
    }
    assert {message.role for message in messages} == {"user", "assistant"}


def test_owned_conversation_without_messages_returns_empty_list(
    db_session: Session,
) -> None:
    owner = create_test_user(db_session, "owner@example.com")
    conversation = create_conversation(
        db_session,
        owner.id,
        "Empty conversation",
    )

    messages = list_messages_for_owner(
        db_session,
        conversation.id,
        owner.id,
    )

    assert messages == []


def test_different_owner_cannot_create_or_list_messages(
    db_session: Session,
) -> None:
    owner_a = create_test_user(db_session, "owner-a@example.com")
    owner_b = create_test_user(db_session, "owner-b@example.com")
    conversation = create_conversation(
        db_session,
        owner_a.id,
        "Owner A private conversation",
    )

    created = create_message_for_owner(
        session=db_session,
        conversation_id=conversation.id,
        owner_id=owner_b.id,
        role="user",
        content="Unauthorized message",
    )
    visible = list_messages_for_owner(
        session=db_session,
        conversation_id=conversation.id,
        owner_id=owner_b.id,
    )

    assert created is None
    assert visible is None
    assert db_session.execute(select(Message)).scalars().all() == []


def test_invalid_message_role_rolls_back_transaction(
    db_session: Session,
) -> None:
    owner = create_test_user(db_session, "owner@example.com")
    conversation = create_conversation(
        db_session,
        owner.id,
        "Role constraint test",
    )

    # Literal is a development-time type hint; the database constraint is the
    # final runtime defense if an internal caller still passes an invalid role.
    with pytest.raises(IntegrityError):
        create_message_for_owner(
            session=db_session,
            conversation_id=conversation.id,
            owner_id=owner.id,
            role="system",  # type: ignore[arg-type]
            content="This row must never be stored.",
        )

    messages = list_messages_for_owner(
        db_session,
        conversation.id,
        owner.id,
    )
    assert messages == []


def test_deleting_conversation_cascades_to_messages(
    db_session: Session,
) -> None:
    owner = create_test_user(db_session, "owner@example.com")
    conversation = create_conversation(
        db_session,
        owner.id,
        "Conversation to delete",
    )
    message = create_message_for_owner(
        db_session,
        conversation.id,
        owner.id,
        "user",
        "This message should be deleted with its conversation.",
    )
    assert message is not None
    message_id = message.id

    deleted = delete_conversation_for_owner(
        db_session,
        conversation.id,
        owner.id,
    )

    assert deleted is True
    assert db_session.get(Message, message_id) is None


def test_deleting_user_cascades_to_conversations_and_messages(
    db_session: Session,
) -> None:
    owner = create_test_user(db_session, "owner@example.com")
    conversation = create_conversation(
        db_session,
        owner.id,
        "User-owned conversation",
    )
    message = create_message_for_owner(
        db_session,
        conversation.id,
        owner.id,
        "assistant",
        "This message should be deleted with its owner.",
    )
    assert message is not None
    conversation_id = conversation.id
    message_id = message.id

    db_session.delete(owner)
    db_session.commit()

    assert db_session.get(Conversation, conversation_id) is None
    assert db_session.get(Message, message_id) is None
