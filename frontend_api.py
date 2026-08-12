"""HTTP client used by the Streamlit frontend to call the FastAPI backend."""

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
        # 網路錯誤不應把底層 exception、網址參數或環境資訊
        # 直接顯示在 Streamlit 畫面。
        raise BackendAPIError(
            "Unable to connect to the backend."
        ) from error

    if not 200 <= response.status_code < 300:
        raise BackendAPIError(
            message=extract_error_message(response),
            status_code=response.status_code,
        )

    try:
        response_data = response.json()
    except ValueError as error:
        raise BackendAPIError(
            "Backend returned an invalid JSON response.",
            status_code=response.status_code,
        ) from error

    # 目前 Auth endpoints 都應回傳 JSON object，而不是 list。
    if not isinstance(response_data, dict):
        raise BackendAPIError(
            "Backend returned an unexpected JSON response.",
            status_code=response.status_code,
        )

    return response_data


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

    normalized_token = access_token.strip()

    if not normalized_token:
        raise ValueError("Access token cannot be empty.")

    return request_json(
        method="GET",
        path="/auth/me",
        base_url=base_url,
        headers={
            "Authorization": f"Bearer {normalized_token}",
        },
    )
