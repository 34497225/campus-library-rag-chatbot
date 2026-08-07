from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.repositories import (
    create_user,
    get_user_by_email,
    get_user_by_id,
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

    # 依照 SQLAlchemy ORM metadata 建立 users 表。
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    # 測試結束後清除 schema 並釋放 engine。
    Base.metadata.drop_all(engine)
    engine.dispose()


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
