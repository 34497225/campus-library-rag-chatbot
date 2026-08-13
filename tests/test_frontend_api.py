"""Tests for the Streamlit frontend's FastAPI HTTP client."""

from typing import Any

import pytest
import requests

from frontend_api import (
    REQUEST_TIMEOUT_SECONDS,
    BackendAPIError,
    create_conversation,
    create_message,
    delete_conversation,
    fetch_current_user,
    list_conversations,
    list_messages,
    login_user,
    normalize_base_url,
    normalize_resource_id,
    register_user,
    rename_conversation,
    request_json,
)


class FakeResponse:
    """Provide the small part of requests.Response used by our client."""

    def __init__(
        self,
        status_code: int,
        json_data: object = None,
        *,
        json_error: bool = False,
    ) -> None:
        self.status_code = status_code
        self.json_data = json_data
        self.json_error = json_error

    def json(self) -> object:
        """Return fake JSON or simulate an invalid JSON response."""

        if self.json_error:
            raise ValueError("Response body is not valid JSON.")

        return self.json_data


def test_normalize_base_url_removes_spaces_and_trailing_slashes() -> None:
    """A configured URL should be safe to combine with endpoint paths."""

    result = normalize_base_url("  http://localhost:8000///  ")

    assert result == "http://localhost:8000"


def test_normalize_base_url_rejects_empty_value() -> None:
    """The client should fail clearly when no backend URL is configured."""

    with pytest.raises(
        ValueError,
        match="BACKEND_API_URL is not configured",
    ):
        normalize_base_url("   ")


def test_request_timeout_allows_render_free_tier_cold_start() -> None:
    """The frontend should wait long enough for a sleeping Render service."""

    # Render 免費服務冷啟動可能超過 50 秒；75 秒仍有明確上限，
    # 兼顧正式環境可用性與避免請求永久卡住。
    assert REQUEST_TIMEOUT_SECONDS == 75


def test_register_user_sends_expected_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registration should send email and password to /auth/register."""

    captured_request: dict[str, Any] = {}

    def fake_request(**kwargs: Any) -> FakeResponse:
        # 保存 request 參數，讓測試能檢查 method、URL、body 與 timeout。
        captured_request.update(kwargs)

        return FakeResponse(
            status_code=201,
            json_data={
                "id": "user-id",
                "email": "student@example.com",
                "created_at": "2026-08-12T12:00:00Z",
            },
        )

    # 只在這個測試期間，把真正的 requests.request 換成 fake_request。
    monkeypatch.setattr(requests, "request", fake_request)

    result = register_user(
        base_url="http://localhost:8000/",
        email="student@example.com",
        password="safe-password",
    )

    assert result["email"] == "student@example.com"
    assert captured_request["method"] == "POST"
    assert captured_request["url"] == (
        "http://localhost:8000/auth/register"
    )
    assert captured_request["json"] == {
        "email": "student@example.com",
        "password": "safe-password",
    }
    assert captured_request["headers"] is None
    assert captured_request["timeout"] == REQUEST_TIMEOUT_SECONDS


def test_login_user_returns_valid_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid login response should return its access token."""

    def fake_request(**_kwargs: Any) -> FakeResponse:
        return FakeResponse(
            status_code=200,
            json_data={
                "access_token": "signed-jwt-token",
                "token_type": "bearer",
            },
        )

    monkeypatch.setattr(requests, "request", fake_request)

    result = login_user(
        base_url="http://localhost:8000",
        email="student@example.com",
        password="safe-password",
    )

    assert result == {
        "access_token": "signed-jwt-token",
        "token_type": "bearer",
    }


def test_fetch_current_user_sends_bearer_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The /auth/me request should authenticate with a bearer token."""

    captured_request: dict[str, Any] = {}

    def fake_request(**kwargs: Any) -> FakeResponse:
        captured_request.update(kwargs)

        return FakeResponse(
            status_code=200,
            json_data={
                "id": "user-id",
                "email": "student@example.com",
                "created_at": "2026-08-12T12:00:00Z",
            },
        )

    monkeypatch.setattr(requests, "request", fake_request)

    result = fetch_current_user(
        base_url="http://localhost:8000",
        access_token="  signed-jwt-token  ",
    )

    assert result["email"] == "student@example.com"
    assert captured_request["method"] == "GET"
    assert captured_request["url"] == "http://localhost:8000/auth/me"
    assert captured_request["headers"] == {
        "Authorization": "Bearer signed-jwt-token",
    }


def test_request_json_preserves_backend_string_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A FastAPI HTTPException detail should become BackendAPIError."""

    def fake_request(**_kwargs: Any) -> FakeResponse:
        return FakeResponse(
            status_code=401,
            json_data={
                "detail": "Invalid email or password.",
            },
        )

    monkeypatch.setattr(requests, "request", fake_request)

    with pytest.raises(BackendAPIError) as error_info:
        login_user(
            base_url="http://localhost:8000",
            email="student@example.com",
            password="wrong-password",
        )

    assert error_info.value.status_code == 401
    assert str(error_info.value) == "Invalid email or password."


def test_request_json_combines_validation_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FastAPI's validation list should become a readable message."""

    def fake_request(**_kwargs: Any) -> FakeResponse:
        return FakeResponse(
            status_code=422,
            json_data={
                "detail": [
                    {
                        "loc": ["body", "email"],
                        "msg": "value is not a valid email address",
                        "type": "value_error",
                    },
                    {
                        "loc": ["body", "password"],
                        "msg": "String should have at least 8 characters",
                        "type": "string_too_short",
                    },
                ],
            },
        )

    monkeypatch.setattr(requests, "request", fake_request)

    with pytest.raises(BackendAPIError) as error_info:
        register_user(
            base_url="http://localhost:8000",
            email="not-an-email",
            password="short",
        )

    assert error_info.value.status_code == 422
    assert str(error_info.value) == (
        "value is not a valid email address; "
        "String should have at least 8 characters"
    )


def test_request_json_hides_non_json_error_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An HTML or invalid error page should not be exposed to the UI."""

    def fake_request(**_kwargs: Any) -> FakeResponse:
        return FakeResponse(
            status_code=500,
            json_error=True,
        )

    monkeypatch.setattr(requests, "request", fake_request)

    with pytest.raises(BackendAPIError) as error_info:
        request_json(
            method="GET",
            path="/health",
            base_url="http://localhost:8000",
        )

    assert error_info.value.status_code == 500
    assert str(error_info.value) == (
        "Backend request failed with status 500."
    )


def test_request_json_converts_network_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Connection failures should become a safe frontend exception."""

    def fake_request(**_kwargs: Any) -> FakeResponse:
        raise requests.ConnectionError(
            "Detailed local connection information"
        )

    monkeypatch.setattr(requests, "request", fake_request)

    with pytest.raises(
        BackendAPIError,
        match="Unable to connect to the backend",
    ) as error_info:
        request_json(
            method="GET",
            path="/health",
            base_url="http://localhost:8000",
        )

    # 沒收到 HTTP response，因此沒有 status code。
    assert error_info.value.status_code is None


def test_request_json_rejects_invalid_success_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful status with invalid JSON is still a bad response."""

    def fake_request(**_kwargs: Any) -> FakeResponse:
        return FakeResponse(
            status_code=200,
            json_error=True,
        )

    monkeypatch.setattr(requests, "request", fake_request)

    with pytest.raises(
        BackendAPIError,
        match="Backend returned an invalid JSON response",
    ) as error_info:
        request_json(
            method="GET",
            path="/auth/me",
            base_url="http://localhost:8000",
        )

    assert error_info.value.status_code == 200


def test_request_json_rejects_json_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auth endpoints should return a JSON object, not a list."""

    def fake_request(**_kwargs: Any) -> FakeResponse:
        return FakeResponse(
            status_code=200,
            json_data=[],
        )

    monkeypatch.setattr(requests, "request", fake_request)

    with pytest.raises(
        BackendAPIError,
        match="Backend returned an unexpected JSON response",
    ):
        request_json(
            method="GET",
            path="/auth/me",
            base_url="http://localhost:8000",
        )


@pytest.mark.parametrize(
    "response_data",
    [
        {
            "token_type": "bearer",
        },
        {
            "access_token": "",
            "token_type": "bearer",
        },
        {
            "access_token": "signed-jwt-token",
            "token_type": "basic",
        },
    ],
)
def test_login_user_rejects_invalid_token_contract(
    monkeypatch: pytest.MonkeyPatch,
    response_data: dict[str, str],
) -> None:
    """Login should reject responses that cannot authenticate later calls."""

    def fake_request(**_kwargs: Any) -> FakeResponse:
        return FakeResponse(
            status_code=200,
            json_data=response_data,
        )

    monkeypatch.setattr(requests, "request", fake_request)

    with pytest.raises(BackendAPIError):
        login_user(
            base_url="http://localhost:8000",
            email="student@example.com",
            password="safe-password",
        )


def test_fetch_current_user_rejects_empty_token() -> None:
    """An empty token should be rejected before making a request."""

    with pytest.raises(
        ValueError,
        match="Access token cannot be empty",
    ):
        fetch_current_user(
            base_url="http://localhost:8000",
            access_token="   ",
        )


def test_conversation_client_sends_bearer_crud_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Conversation helpers should target owner-scoped backend paths."""

    captured: list[dict[str, Any]] = []
    conversation_id = "12345678-1234-5678-1234-567812345678"

    def fake_request(**kwargs: Any) -> FakeResponse:
        captured.append(kwargs)
        if kwargs["method"] == "DELETE":
            return FakeResponse(status_code=204)
        if kwargs["method"] == "GET":
            return FakeResponse(status_code=200, json_data=[])
        return FakeResponse(
            status_code=201 if kwargs["method"] == "POST" else 200,
            json_data={"id": conversation_id},
        )

    monkeypatch.setattr(requests, "request", fake_request)

    create_conversation("http://localhost:8000", "token", "New chat")
    list_conversations("http://localhost:8000", "token")
    rename_conversation(
        "http://localhost:8000", "token", conversation_id, "Renamed"
    )
    delete_conversation(
        "http://localhost:8000", "token", conversation_id
    )

    assert [request["method"] for request in captured] == [
        "POST",
        "GET",
        "PATCH",
        "DELETE",
    ]
    assert all(
        request["headers"] == {"Authorization": "Bearer token"}
        for request in captured
    )
    assert captured[0]["json"] == {"title": "New chat"}
    assert captured[2]["json"] == {"title": "Renamed"}


def test_message_client_uses_distinct_user_and_assistant_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The frontend must never send a role field in message JSON."""

    captured: list[dict[str, Any]] = []
    conversation_id = "12345678-1234-5678-1234-567812345678"

    def fake_request(**kwargs: Any) -> FakeResponse:
        captured.append(kwargs)
        if kwargs["method"] == "GET":
            return FakeResponse(status_code=200, json_data=[])
        return FakeResponse(
            status_code=201,
            json_data={"id": "message-id"},
        )

    monkeypatch.setattr(requests, "request", fake_request)

    list_messages("http://localhost:8000", "token", conversation_id)
    create_message(
        "http://localhost:8000",
        "token",
        conversation_id,
        "Question",
    )
    create_message(
        "http://localhost:8000",
        "token",
        conversation_id,
        "Answer",
        assistant=True,
    )

    assert captured[0]["url"].endswith(
        f"/conversations/{conversation_id}/messages"
    )
    assert captured[1]["json"] == {"content": "Question"}
    assert captured[2]["url"].endswith("/messages/assistant")
    assert captured[2]["json"] == {"content": "Answer"}


@pytest.mark.parametrize("invalid_id", ["", "../auth/me", "not-a-uuid"])
def test_normalize_resource_id_rejects_unsafe_path_values(
    invalid_id: str,
) -> None:
    """Backend IDs cannot become arbitrary URL path fragments."""

    with pytest.raises(ValueError, match="valid UUID"):
        normalize_resource_id(invalid_id)


def test_list_client_rejects_non_object_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed list response must not enter Streamlit session state."""

    def fake_request(**_kwargs: Any) -> FakeResponse:
        return FakeResponse(status_code=200, json_data=["bad-item"])

    monkeypatch.setattr(requests, "request", fake_request)

    with pytest.raises(BackendAPIError, match="unexpected JSON"):
        list_conversations("http://localhost:8000", "token")
