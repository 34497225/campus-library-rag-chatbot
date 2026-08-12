"""Authentication-state helpers used by the Streamlit frontend."""

from collections.abc import MutableMapping
from typing import Any


ACCESS_TOKEN_KEY = "access_token"
CURRENT_USER_KEY = "current_user"


def initialize_auth_state(
    state: MutableMapping[str, Any],
) -> None:
    """Create authentication keys without overwriting an active session."""

    # Streamlit 每次互動都會重新執行 app.py。
    # 只有 key 尚未存在時才設定預設值，
    # 否則每次 rerun 都會把剛登入的 token 清除。
    if ACCESS_TOKEN_KEY not in state:
        state[ACCESS_TOKEN_KEY] = None

    if CURRENT_USER_KEY not in state:
        state[CURRENT_USER_KEY] = None


def store_authentication(
    state: MutableMapping[str, Any],
    access_token: str,
    user: dict[str, Any],
) -> None:
    """Store only the token and safe user fields in session state."""

    normalized_token = access_token.strip()

    if not normalized_token:
        raise ValueError("Access token cannot be empty.")

    # 只保留 /auth/me 對外公開的安全欄位。
    # 即使未來後端意外多回傳其他資料，
    # 前端 session 也不會毫無限制地全部保存。
    safe_user = {
        "id": user.get("id"),
        "email": user.get("email"),
        "created_at": user.get("created_at"),
    }

    if not all(
        isinstance(safe_user[key], str)
        for key in ("id", "email", "created_at")
    ):
        raise ValueError(
            "Current user response is missing required fields."
        )

    state[ACCESS_TOKEN_KEY] = normalized_token
    state[CURRENT_USER_KEY] = safe_user


def clear_authentication(
    state: MutableMapping[str, Any],
) -> None:
    """Remove authentication data without affecting RAG conversation state."""

    # 登出只清除登入資料。
    # messages、vector_store 和使用統計是否一併清除，
    # 會在 UI 串接時依隱私需求另外決定。
    state[ACCESS_TOKEN_KEY] = None
    state[CURRENT_USER_KEY] = None


def is_authenticated(
    state: MutableMapping[str, Any],
) -> bool:
    """Return whether session state contains usable authentication data."""

    access_token = state.get(ACCESS_TOKEN_KEY)
    current_user = state.get(CURRENT_USER_KEY)

    return (
        isinstance(access_token, str)
        and bool(access_token.strip())
        and isinstance(current_user, dict)
        and isinstance(current_user.get("email"), str)
    )
