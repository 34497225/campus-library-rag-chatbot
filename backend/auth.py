from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.database import get_db_session
from backend.dependencies import get_current_user, get_settings
from backend.models import User
from backend.repositories import create_user, get_user_by_email
from backend.schemas import (
    TokenResponse,
    UserCreate,
    UserLogin,
    UserRead,
)
from backend.security import (
    create_access_token,
    hash_password,
    verify_password,
)


# prefix 會讓這個 router 裡的路徑都以 /auth 開頭。
# tags 用於 Swagger /docs 的 API 分組。
router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
)

# Email 不存在時仍執行一次 Argon2 驗證，
# 減少「不存在帳號」與「錯誤密碼」之間的回應時間差。
#
# 這不是正式使用者密碼，也不會保存到資料庫。
# 每個應用程序啟動時只建立一次。
_DUMMY_PASSWORD_HASH = hash_password(
    "dummy-password-used-only-for-login-timing"
)


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
    payload: UserCreate,
    session: Annotated[Session, Depends(get_db_session)],
) -> UserRead:
    """Register a user while storing only an Argon2 password hash."""

    # UserCreate 已經將 Email 去除前後空白並轉成小寫。
    normalized_email = str(payload.email)

    # 先查詢可以提供清楚的 409 回應，
    # 避免直接把資料庫 IntegrityError 暴露給前端。
    existing_user = get_user_by_email(
        session,
        normalized_email,
    )

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered.",
        )

    # 明文密碼只在這個請求的記憶體中短暫存在。
    # 傳入 repository 前必須先轉成不可逆的 Argon2 hash。
    password_hash = hash_password(payload.password)

    try:
        user = create_user(
            session=session,
            email=normalized_email,
            password_hash=password_hash,
        )
    except IntegrityError as error:
        # 「先查詢、再新增」之間仍可能有另一個請求搶先註冊。
        # 資料庫唯一索引才是最後一道可靠防線。
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered.",
        ) from error

    # response_model=UserRead 只會輸出 id、email、created_at，
    # 即使 ORM User 含有 password_hash，也不會傳給前端。
    return UserRead.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login_user(
    payload: UserLogin,
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    """Authenticate a user and return a signed access token."""

    normalized_email = str(payload.email)

    user = get_user_by_email(
        session,
        normalized_email,
    )

    # 無論 Email 是否存在，都選擇一個有效的 Argon2 hash
    # 執行密碼驗證，讓兩種失敗路徑的工作量更接近。
    password_hash = (
        user.password_hash
        if user is not None
        else _DUMMY_PASSWORD_HASH
    )

    password_is_valid = verify_password(
        payload.password,
        password_hash,
    )
    if user is None or not password_is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # JWT 的 sub 保存使用者 UUID 字串。
    # 後續 /auth/me 會從 sub 找回目前登入的使用者。
    access_token = create_access_token(
        subject=str(user.id),
        settings=settings,
    )

    return TokenResponse(access_token=access_token)


@router.get(
    "/me",
    response_model=UserRead,
)
def read_current_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserRead:
    """Return the authenticated user's safe profile."""

    # get_current_user 已完成：
    # 1. 讀取 Bearer token
    # 2. 驗證 JWT
    # 3. 將 sub 轉成 UUID
    # 4. 從資料庫取得 User
    #
    # endpoint 只需要決定如何回傳資料。
    return UserRead.model_validate(current_user)
