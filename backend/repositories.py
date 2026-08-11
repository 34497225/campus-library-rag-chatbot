import uuid
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models import Conversation, Message, User

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


def create_conversation(
    session: Session,
    owner_id: uuid.UUID,
    title: str,
) -> Conversation:
    """Create and return a conversation owned by one user."""

    conversation = Conversation(
        user_id=owner_id,
        title=title,
    )

    try:
        session.add(conversation)
        session.commit()
    except SQLAlchemyError:
        # 資料庫操作失敗後必須 rollback，
        # 否則這個 Session 不能安全地繼續使用。
        session.rollback()
        raise

    session.refresh(conversation)

    return conversation


def list_conversations_for_owner(
    session: Session,
    owner_id: uuid.UUID,
) -> list[Conversation]:
    """Return only conversations belonging to the specified owner."""

    statement = (
        select(Conversation)
        .where(Conversation.user_id == owner_id)
        .order_by(
            Conversation.updated_at.desc(),
            Conversation.id.desc(),
        )
    )

    # scalars() 將每一列轉成 Conversation ORM 物件。
    return list(session.execute(statement).scalars().all())


def get_conversation_for_owner(
    session: Session,
    conversation_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> Conversation | None:
    """Return a conversation only when it belongs to the owner."""

    # 不先用 Session.get() 只依主鍵查詢。
    # 把 conversation_id 與 owner_id 放在同一個 SQL WHERE，
    # 可以降低未來忘記做授權判斷的風險。
    statement = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == owner_id,
    )

    return session.execute(statement).scalar_one_or_none()


def rename_conversation_for_owner(
    session: Session,
    conversation_id: uuid.UUID,
    owner_id: uuid.UUID,
    title: str,
) -> Conversation | None:
    """Rename an owned conversation, or return None when inaccessible."""

    conversation = get_conversation_for_owner(
        session=session,
        conversation_id=conversation_id,
        owner_id=owner_id,
    )

    # 不存在與不屬於目前使用者都回傳 None。
    # API 之後可統一轉成 404，避免洩漏別人的資料是否存在。
    if conversation is None:
        return None

    conversation.title = title

    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise

    session.refresh(conversation)

    return conversation


def delete_conversation_for_owner(
    session: Session,
    conversation_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> bool:
    """Delete an owned conversation and report whether it was found."""

    conversation = get_conversation_for_owner(
        session=session,
        conversation_id=conversation_id,
        owner_id=owner_id,
    )

    if conversation is None:
        return False

    try:
        session.delete(conversation)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise

    return True


def create_message_for_owner(
    session: Session,
    conversation_id: uuid.UUID,
    owner_id: uuid.UUID,
    role: Literal["user", "assistant"],
    content: str,
) -> Message | None:
    """Create a message only when the caller owns its conversation."""

    # Ownership is checked before constructing the Message. This prevents a
    # caller from adding content to another user's conversation even if they
    # know that conversation's UUID.
    conversation = get_conversation_for_owner(
        session=session,
        conversation_id=conversation_id,
        owner_id=owner_id,
    )
    if conversation is None:
        return None

    message = Message(
        conversation_id=conversation.id,
        role=role,
        content=content,
    )

    # A new message makes its parent conversation active again. Updating this
    # timestamp lets list_conversations_for_owner() sort by recent activity.
    conversation.updated_at = datetime.now(timezone.utc)

    try:
        session.add(message)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise

    session.refresh(message)

    return message


def list_messages_for_owner(
    session: Session,
    conversation_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> list[Message] | None:
    """Return ordered messages only when the caller owns the conversation."""

    conversation = get_conversation_for_owner(
        session=session,
        conversation_id=conversation_id,
        owner_id=owner_id,
    )
    if conversation is None:
        # None distinguishes an inaccessible conversation from an owned
        # conversation that exists but contains no messages (an empty list).
        return None

    statement = (
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(
            Message.created_at.asc(),
            Message.id.asc(),
        )
    )

    return list(session.execute(statement).scalars().all())
