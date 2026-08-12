"""HTTP client used by the Streamlit frontend to call the FastAPI backend."""

import uuid
from typing import Any

import requests


# 每一個後端請求最多等待 10 秒。
# 設定 timeout 可以避免後端離線時，Streamlit 畫面永久卡住。
REQUEST_TIMEOUT_SECONDS = 10


class BackendAPIError(Exception):
    """Represent a backend or network error that the UI can handle safely."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)

        # 保留 HTTP status code，讓 Streamlit UI 之後能區分：
        # 401：帳密錯誤或 token 失效
        # 409：Email 已註冊
        # 422：輸入格式錯誤
        # None：連線失敗，沒有收到 HTTP response
        self.status_code = status_code


def normalize_base_url(base_url: str) -> str:
    """Normalize the configured backend URL."""

    # 去除使用者不小心輸入的空白與結尾斜線。
    # 例如 http://localhost:8000/ 會變成 http://localhost:8000，
    # 後續再串接 /auth/login 時就不會出現兩個斜線。
    normalized_url = base_url.strip().rstrip("/")

    if not normalized_url:
        raise ValueError("BACKEND_API_URL is not configured.")

    return normalized_url


def extract_error_message(response: requests.Response) -> str:
    """Read FastAPI's detail field without exposing an invalid response."""

    try:
        response_data = response.json()
    except ValueError:
        # 後端或 proxy 不一定總是回 JSON。
        # 此時不把整段 HTML 或內部錯誤頁顯示給使用者。
        return (
            "Backend request failed with status "
            f"{response.status_code}."
        )

    if not isinstance(response_data, dict):
        return (
            "Backend request failed with status "
            f"{response.status_code}."
        )

    detail = response_data.get("detail")

    # FastAPI 的 HTTPException 通常使用字串 detail。
    # 例如：{"detail": "Invalid email or password."}
    if isinstance(detail, str):
        return detail

    # Pydantic validation error 的 detail 通常是一個 list。
    # 我們只取每個項目的 msg，不顯示完整內部資料結構。
    if isinstance(detail, list):
        messages = []

        for item in detail:
            if not isinstance(item, dict):
                continue

            message = item.get("msg")
            if isinstance(message, str):
                messages.append(message)

        if messages:
            return "; ".join(messages)

    return (
        "Backend request failed with status "
        f"{response.status_code}."
    )


def request_json(
    method: str,
    path: str,
    base_url: str,
    *,
    json_body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Send one backend request and require a JSON object response."""

    response = _send_request(
        method=method,
        path=path,
        base_url=base_url,
        json_body=json_body,
        headers=headers,
    )

    try:
        response_data = response.json()
    except ValueError as error:
        raise BackendAPIError(
            "Backend returned an invalid JSON response.",
            status_code=response.status_code,
        ) from error

    # Auth 與單筆 Conversation／Message endpoints 都應回 JSON object。
    if not isinstance(response_data, dict):
        raise BackendAPIError(
            "Backend returned an unexpected JSON response.",
            status_code=response.status_code,
        )

    return response_data


def request_json_list(
    method: str,
    path: str,
    base_url: str,
    *,
    headers: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Send one backend request and require a list of JSON objects."""

    response = _send_request(
        method=method,
        path=path,
        base_url=base_url,
        headers=headers,
    )

    try:
        response_data = response.json()
    except ValueError as error:
        raise BackendAPIError(
            "Backend returned an invalid JSON response.",
            status_code=response.status_code,
        ) from error

    if not isinstance(response_data, list) or not all(
        isinstance(item, dict) for item in response_data
    ):
        raise BackendAPIError(
            "Backend returned an unexpected JSON response.",
            status_code=response.status_code,
        )

    return response_data


def request_no_content(
    method: str,
    path: str,
    base_url: str,
    *,
    headers: dict[str, str] | None = None,
) -> None:
    """Send a request whose successful contract is HTTP 204 with no body."""

    response = _send_request(
        method=method,
        path=path,
        base_url=base_url,
        headers=headers,
    )
    if response.status_code != 204:
        raise BackendAPIError(
            "Backend returned an unexpected success status.",
            status_code=response.status_code,
        )


def _send_request(
    method: str,
    path: str,
    base_url: str,
    *,
    json_body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> requests.Response:
    """Share safe network and non-2xx handling across response shapes."""

    request_url = f"{normalize_base_url(base_url)}{path}"
    try:
        response = requests.request(
            method=method,
            url=request_url,
            json=json_body,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as error:
        raise BackendAPIError(
            "Unable to connect to the backend."
        ) from error

    if not 200 <= response.status_code < 300:
        raise BackendAPIError(
            message=extract_error_message(response),
            status_code=response.status_code,
        )

    return response


def bearer_headers(access_token: str) -> dict[str, str]:
    """Build the shared Authorization header for protected endpoints."""

    normalized_token = access_token.strip()
    if not normalized_token:
        raise ValueError("Access token cannot be empty.")

    return {"Authorization": f"Bearer {normalized_token}"}


def normalize_resource_id(resource_id: str) -> str:
    """Require a UUID before placing a resource identifier in a URL path."""

    try:
        return str(uuid.UUID(resource_id))
    except (ValueError, AttributeError) as error:
        raise ValueError("Resource ID must be a valid UUID.") from error


def register_user(
    base_url: str,
    email: str,
    password: str,
) -> dict[str, Any]:
    """Register a user and return the safe user response."""

    return request_json(
        method="POST",
        path="/auth/register",
        base_url=base_url,
        json_body={
            "email": email,
            "password": password,
        },
    )


def login_user(
    base_url: str,
    email: str,
    password: str,
) -> dict[str, Any]:
    """Log in and return the backend's bearer-token response."""

    response_data = request_json(
        method="POST",
        path="/auth/login",
        base_url=base_url,
        json_body={
            "email": email,
            "password": password,
        },
    )

    # 即使 HTTP 是 200，也要確認 response 確實符合登入契約。
    # 避免把缺少 token 的異常 response 當成登入成功。
    access_token = response_data.get("access_token")
    token_type = response_data.get("token_type")

    if not isinstance(access_token, str) or not access_token:
        raise BackendAPIError(
            "Backend login response did not include an access token."
        )

    if token_type != "bearer":
        raise BackendAPIError(
            "Backend login response used an unsupported token type."
        )

    return response_data


def fetch_current_user(
    base_url: str,
    access_token: str,
) -> dict[str, Any]:
    """Use a bearer token to retrieve the authenticated user."""

    return request_json(
        method="GET",
        path="/auth/me",
        base_url=base_url,
        headers=bearer_headers(access_token),
    )


def create_conversation(
    base_url: str,
    access_token: str,
    title: str,
) -> dict[str, Any]:
    """Create one conversation owned by the authenticated user."""

    return request_json(
        method="POST",
        path="/conversations",
        base_url=base_url,
        json_body={"title": title},
        headers=bearer_headers(access_token),
    )


def list_conversations(
    base_url: str,
    access_token: str,
) -> list[dict[str, Any]]:
    """List only the authenticated user's conversations."""

    return request_json_list(
        method="GET",
        path="/conversations",
        base_url=base_url,
        headers=bearer_headers(access_token),
    )


def rename_conversation(
    base_url: str,
    access_token: str,
    conversation_id: str,
    title: str,
) -> dict[str, Any]:
    """Rename an owned conversation."""

    safe_id = normalize_resource_id(conversation_id)
    return request_json(
        method="PATCH",
        path=f"/conversations/{safe_id}",
        base_url=base_url,
        json_body={"title": title},
        headers=bearer_headers(access_token),
    )


def delete_conversation(
    base_url: str,
    access_token: str,
    conversation_id: str,
) -> None:
    """Delete an owned conversation and its dependent messages."""

    safe_id = normalize_resource_id(conversation_id)
    request_no_content(
        method="DELETE",
        path=f"/conversations/{safe_id}",
        base_url=base_url,
        headers=bearer_headers(access_token),
    )


def list_messages(
    base_url: str,
    access_token: str,
    conversation_id: str,
) -> list[dict[str, Any]]:
    """Load ordered messages from one owned conversation."""

    safe_id = normalize_resource_id(conversation_id)
    return request_json_list(
        method="GET",
        path=f"/conversations/{safe_id}/messages",
        base_url=base_url,
        headers=bearer_headers(access_token),
    )


def create_message(
    base_url: str,
    access_token: str,
    conversation_id: str,
    content: str,
    *,
    assistant: bool = False,
) -> dict[str, Any]:
    """Persist a user question or a server-generated assistant answer."""

    safe_id = normalize_resource_id(conversation_id)
    suffix = "/assistant" if assistant else ""
    return request_json(
        method="POST",
        path=f"/conversations/{safe_id}/messages{suffix}",
        base_url=base_url,
        json_body={"content": content},
        headers=bearer_headers(access_token),
    )
