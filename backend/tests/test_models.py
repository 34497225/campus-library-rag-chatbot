from sqlalchemy import DateTime, String, Uuid

from backend.models import User


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