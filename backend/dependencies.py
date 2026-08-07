import uuid
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.database import get_db_session
from backend.models import User
from backend.repositories import get_user_by_id
from backend.security import decode_access_token


@lru_cache
def get_settings() -> Settings:
    """Load and cache application settings."""

    # 正式執行時從環境變數與 .env 讀取；
    # 測試時可使用 FastAPI dependency override 替換。
    return Settings()


# auto_error=False 讓我們自行統一處理：
# 1. 沒有 Authorization header
# 2. token 格式不正確
# 3. token 過期或簽章錯誤
bearer_scheme = HTTPBearer(auto_error=False)


def create_credentials_exception() -> HTTPException:
    """Create a consistent 401 response for authentication failures."""

    # 所有 token 驗證失敗都使用相同回應，
    # 避免向外洩漏 token 究竟在哪一步失敗。
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """Validate the Bearer token and return its database user."""

    if credentials is None:
        raise create_credentials_exception()

    # decode_access_token 會檢查簽章、演算法與到期時間。
    subject = decode_access_token(
        credentials.credentials,
        settings,
    )

    if subject is None:
        raise create_credentials_exception()

    try:
        # JWT 的 sub 是字串，但 User.id 是 UUID。
        # 無法轉換表示 token 內容不符合本系統格式。
        user_id = uuid.UUID(subject)
    except ValueError as error:
        raise create_credentials_exception() from error

    user = get_user_by_id(
        session,
        user_id,
    )

    # token 可能曾經有效，但使用者之後已被刪除。
    if user is None:
        raise create_credentials_exception()

    return user
