from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import backend.database as database
from backend.config import Settings


@pytest.fixture(autouse=True)
def clear_database_caches() -> Generator[None, None, None]:
    original_get_engine = database.get_engine
    original_get_session_factory = database.get_session_factory

    original_get_engine.cache_clear()
    original_get_session_factory.cache_clear()

    yield

    original_get_engine.cache_clear()
    original_get_session_factory.cache_clear()


def test_get_engine_requires_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        database,
        "Settings",
        lambda: Settings(_env_file=None),
    )

    with pytest.raises(
        RuntimeError,
        match="DATABASE_URL is not configured",
    ):
        database.get_engine()


def test_get_engine_uses_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_database_url = (
        "postgresql+psycopg://user:password@host/database"
    )
    fake_settings = Settings(
        database_url=fake_database_url,
        _env_file=None,
    )
    fake_engine = MagicMock(spec=Engine)
    create_engine_mock = MagicMock(return_value=fake_engine)

    monkeypatch.setattr(
        database,
        "Settings",
        lambda: fake_settings,
    )
    monkeypatch.setattr(
        database,
        "create_engine",
        create_engine_mock,
    )

    engine = database.get_engine()

    assert engine is fake_engine
    create_engine_mock.assert_called_once_with(
        fake_database_url,
        pool_pre_ping=True,
    )


def test_get_session_factory_uses_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_engine = MagicMock(spec=Engine)
    fake_session_factory = MagicMock()
    sessionmaker_mock = MagicMock(
        return_value=fake_session_factory
    )

    monkeypatch.setattr(
        database,
        "get_engine",
        lambda: fake_engine,
    )
    monkeypatch.setattr(
        database,
        "sessionmaker",
        sessionmaker_mock,
    )

    session_factory = database.get_session_factory()

    assert session_factory is fake_session_factory
    sessionmaker_mock.assert_called_once_with(
        bind=fake_engine,
        autoflush=False,
        expire_on_commit=False,
    )


def test_get_db_session_closes_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = MagicMock(spec=Session)
    fake_session_factory = MagicMock(
        return_value=fake_session
    )

    monkeypatch.setattr(
        database,
        "get_session_factory",
        lambda: fake_session_factory,
    )

    session_generator = database.get_db_session()
    session = next(session_generator)

    assert session is fake_session

    with pytest.raises(StopIteration):
        next(session_generator)

    fake_session.close.assert_called_once_with()