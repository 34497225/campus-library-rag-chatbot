import uuid
from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)


class EmailBase(BaseModel):
    """Shared Email validation and normalization for auth requests."""

    # EmailStr 會檢查 Email 格式。
    # max_length=320 則配合 users.email 資料庫欄位長度。
    email: EmailStr = Field(max_length=320)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        """Trim surrounding spaces and normalize Email casing."""

        # mode="before" 代表先整理字串，再交給 EmailStr 驗證格式。
        if isinstance(value, str):
            return value.strip().lower()

        return value


class UserCreate(EmailBase):
    """Request body used when a user registers."""

    # 註冊密碼至少 8 個字元。
    # 上限 128 可避免過大的輸入消耗不必要的雜湊資源。
    password: str = Field(min_length=8, max_length=128)


class UserLogin(EmailBase):
    """Request body used when a user logs in."""

    # 登入時只檢查密碼非空及合理上限。
    # 不再次要求至少 8 字元，否則舊帳號或錯誤短密碼會先得到 422，
    # 而不是由登入流程統一回覆「帳號或密碼錯誤」。
    password: str = Field(min_length=1, max_length=128)


class UserRead(EmailBase):
    """Safe user information returned by the API."""

    id: uuid.UUID
    created_at: datetime

    # 允許 Pydantic 直接從 SQLAlchemy User ORM 物件讀取屬性。
    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """Response returned after a successful login."""

    access_token: str

    # 第一版固定使用 HTTP Bearer authentication。
    token_type: Literal["bearer"] = "bearer"
