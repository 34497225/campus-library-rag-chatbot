import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models import User


def get_user_by_email(
    session: Session,
    email: str,
) -> User | None:
    """Return one user matching the normalized Email, if one exists."""

    # select(User) 表示查詢完整的 User ORM 物件。
    statement = select(User).where(User.email == email)

    # scalar_one_or_none() 可能回傳：
    # 1. 一個 User
    # 2. None
    #
    # 因為 users.email 有唯一索引，理論上不應出現多筆。
    return session.execute(statement).scalar_one_or_none()


def get_user_by_id(
    session: Session,
    user_id: uuid.UUID,
) -> User | None:
    """Return one user by primary key, if one exists."""

    # Session.get() 專門依照 primary key 查詢，
    # 比自己建立 where(User.id == user_id) 更直接。
    return session.get(User, user_id)


def create_user(
    session: Session,
    email: str,
    password_hash: str,
) -> User:
    """Create, persist, and return a new user."""

    # 只接受 password_hash，不接受 password。
    # 這能降低呼叫端意外把明文密碼存入資料庫的風險。
    user = User(
        email=email,
        password_hash=password_hash,
    )

    try:
        session.add(user)
        session.commit()
    except SQLAlchemyError:
        # commit 失敗後，Session 會停留在失敗交易狀態。
        # 必須 rollback，之後才能安全地繼續查詢或回傳錯誤。
        session.rollback()
        raise

    # refresh 重新從資料庫載入 server_default 欄位，
    # 例如資料庫產生的 created_at。
    session.refresh(user)

    return user
