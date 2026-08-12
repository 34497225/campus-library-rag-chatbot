"""Tests for Streamlit authentication-state helpers."""

from typing import Any

import pytest

from frontend_auth import (
    ACCESS_TOKEN_KEY,
    CURRENT_USER_KEY,
    clear_authentication,
    initialize_auth_state,
    is_authenticated,
    store_authentication,
)


def safe_user() -> dict[str, str]:
    """Return a response shaped like FastAPI's UserRead schema."""

    return {
        "id": "2f9ea08d-8ab1-4dd4-9c8f-65779a458b87",
        "email": "student@example.com",
        "created_at": "2026-08-12T12:00:00Z",
    }


def test_initialize_auth_state_creates_empty_defaults() -> None:
    state: dict[str, Any] = {}

    initialize_auth_state(state)

    assert state == {
        ACCESS_TOKEN_KEY: None,
        CURRENT_USER_KEY: None,
    }


def test_initialize_auth_state_preserves_existing_login() -> None:
    state: dict[str, Any] = {
        ACCESS_TOKEN_KEY: "existing-token",
        CURRENT_USER_KEY: safe_user(),
    }

    # 模擬 Streamlit rerun，再次初始化不應登出使用者。
    initialize_auth_state(state)

    assert state[ACCESS_TOKEN_KEY] == "existing-token"
    assert state[CURRENT_USER_KEY] == safe_user()


def test_store_authentication_keeps_only_safe_fields() -> None:
    state: dict[str, Any] = {}
    user_response = {
        **safe_user(),
        "unexpected_internal_field": "must-not-be-stored",
    }

    store_authentication(
        state=state,
        access_token="  signed-jwt-token  ",
        user=user_response,
    )

    assert state[ACCESS_TOKEN_KEY] == "signed-jwt-token"
    assert state[CURRENT_USER_KEY] == safe_user()
    assert "unexpected_internal_field" not in state[CURRENT_USER_KEY]


def test_store_authentication_rejects_empty_token() -> None:
    state: dict[str, Any] = {}

    with pytest.raises(
        ValueError,
        match="Access token cannot be empty",
    ):
        store_authentication(
            state=state,
            access_token="   ",
            user=safe_user(),
        )


def test_store_authentication_rejects_incomplete_user() -> None:
    state: dict[str, Any] = {}

    with pytest.raises(
        ValueError,
        match="Current user response is missing required fields",
    ):
        store_authentication(
            state=state,
            access_token="signed-jwt-token",
            user={
                "email": "student@example.com",
            },
        )


def test_clear_authentication_preserves_unrelated_state() -> None:
    state: dict[str, Any] = {
        ACCESS_TOKEN_KEY: "signed-jwt-token",
        CURRENT_USER_KEY: safe_user(),
        "messages": [{"role": "user", "content": "Hello"}],
    }

    clear_authentication(state)

    assert state[ACCESS_TOKEN_KEY] is None
    assert state[CURRENT_USER_KEY] is None

    # 登出函式目前不應偷偷修改其他 state。
    assert state["messages"] == [
        {
            "role": "user",
            "content": "Hello",
        }
    ]


@pytest.mark.parametrize(
    "state",
    [
        {},
        {
            ACCESS_TOKEN_KEY: None,
            CURRENT_USER_KEY: None,
        },
        {
            ACCESS_TOKEN_KEY: "signed-jwt-token",
            CURRENT_USER_KEY: None,
        },
        {
            ACCESS_TOKEN_KEY: "",
            CURRENT_USER_KEY: safe_user(),
        },
    ],
)
def test_is_authenticated_rejects_incomplete_state(
    state: dict[str, Any],
) -> None:
    assert not is_authenticated(state)


def test_is_authenticated_accepts_complete_state() -> None:
    state: dict[str, Any] = {
        ACCESS_TOKEN_KEY: "signed-jwt-token",
        CURRENT_USER_KEY: safe_user(),
    }

    assert is_authenticated(state)
