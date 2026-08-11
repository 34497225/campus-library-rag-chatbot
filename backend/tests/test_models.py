from sqlalchemy import CheckConstraint, DateTime, String, Text, Uuid

from backend.models import Conversation, Message, User


def test_user_table_name_and_columns() -> None:
    assert User.__tablename__ == "users"
    assert set(User.__table__.columns.keys()) == {
        "id",
        "email",
        "password_hash",
        "created_at",
    }


def test_user_id_column() -> None:
    column = User.__table__.columns["id"]

    assert column.primary_key is True
    assert isinstance(column.type, Uuid)
    assert column.default is not None


def test_user_email_column() -> None:
    column = User.__table__.columns["email"]

    assert isinstance(column.type, String)
    assert column.type.length == 320
    assert column.nullable is False
    assert column.unique is True
    assert column.index is True


def test_user_password_and_created_at_columns() -> None:
    password_column = User.__table__.columns["password_hash"]
    created_at_column = User.__table__.columns["created_at"]

    assert isinstance(password_column.type, String)
    assert password_column.type.length == 255
    assert password_column.nullable is False

    assert isinstance(created_at_column.type, DateTime)
    assert created_at_column.type.timezone is True
    assert created_at_column.nullable is False
    assert created_at_column.server_default is not None


def test_conversation_table_name_and_columns() -> None:
    assert Conversation.__tablename__ == "conversations"
    assert set(Conversation.__table__.columns.keys()) == {
        "id",
        "user_id",
        "title",
        "created_at",
        "updated_at",
    }


def test_conversation_owner_foreign_key() -> None:
    user_id_column = Conversation.__table__.columns["user_id"]
    foreign_key = next(iter(user_id_column.foreign_keys))

    assert isinstance(user_id_column.type, Uuid)
    assert user_id_column.nullable is False
    assert user_id_column.index is True

    # 確認每個對話都必須屬於 users 表中的一位使用者。
    assert foreign_key.target_fullname == "users.id"
    assert foreign_key.ondelete == "CASCADE"


def test_conversation_fields_and_relationships() -> None:
    title_column = Conversation.__table__.columns["title"]
    updated_at_column = Conversation.__table__.columns["updated_at"]

    assert isinstance(title_column.type, String)
    assert title_column.type.length == 200
    assert title_column.nullable is False

    assert isinstance(updated_at_column.type, DateTime)
    assert updated_at_column.type.timezone is True
    assert updated_at_column.server_default is not None
    assert updated_at_column.onupdate is not None

    # back_populates 必須在關聯兩端互相對應。
    assert Conversation.user.property.back_populates == "conversations"
    assert User.conversations.property.back_populates == "user"
    assert "delete-orphan" in User.conversations.property.cascade


def test_message_table_columns_and_conversation_foreign_key() -> None:
    assert Message.__tablename__ == "messages"
    assert set(Message.__table__.columns.keys()) == {
        "id",
        "conversation_id",
        "role",
        "content",
        "created_at",
    }

    conversation_id_column = Message.__table__.columns["conversation_id"]
    foreign_key = next(iter(conversation_id_column.foreign_keys))

    assert foreign_key.target_fullname == "conversations.id"
    assert foreign_key.ondelete == "CASCADE"
    assert conversation_id_column.index is True

    # Message 不重複保存 user_id，擁有者由 Conversation 判斷。
    assert "user_id" not in Message.__table__.columns


def test_message_role_content_constraint_and_relationship() -> None:
    role_column = Message.__table__.columns["role"]
    content_column = Message.__table__.columns["content"]

    assert isinstance(role_column.type, String)
    assert role_column.type.length == 20
    assert role_column.nullable is False

    assert isinstance(content_column.type, Text)
    assert content_column.nullable is False

    check_constraint_names = {
        constraint.name
        for constraint in Message.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "ck_messages_role" in check_constraint_names

    assert Message.conversation.property.back_populates == "messages"
    assert Conversation.messages.property.back_populates == "conversation"
    assert "delete-orphan" in Conversation.messages.property.cascade
