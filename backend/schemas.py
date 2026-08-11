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


class ConversationTitleBase(BaseModel):
    """Shared title validation for conversation requests."""

    title: str = Field(min_length=1, max_length=200)

    # Reject undeclared fields such as user_id. Ownership always comes from
    # the authenticated user, never from request JSON.
    model_config = ConfigDict(extra="forbid")

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: object) -> object:
        """Remove accidental surrounding spaces before validation."""

        # 先 strip 才能阻止 "   " 這種看似有長度的空白標題。
        if isinstance(value, str):
            return value.strip()

        return value


class ConversationCreate(ConversationTitleBase):
    """Request body used to create a conversation."""


class ConversationUpdate(ConversationTitleBase):
    """Request body used to rename a conversation."""


class ConversationRead(ConversationTitleBase):
    """Safe conversation information returned by the API."""

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    # 允許直接把 SQLAlchemy Conversation 交給 Pydantic。
    model_config = ConfigDict(from_attributes=True)


class MessageCreate(BaseModel):
    """User-provided message content."""

    # role 不放在 request schema 中。
    # 否則用戶端可以冒充 assistant 寫入訊息。
    content: str = Field(min_length=1, max_length=20_000)

    # In particular, reject a client-supplied role="assistant" instead of
    # silently ignoring it. The server chooses the stored message role.
    model_config = ConfigDict(extra="forbid")

    @field_validator("content", mode="before")
    @classmethod
    def normalize_content(cls, value: object) -> object:
        """Reject messages containing only surrounding whitespace."""

        if isinstance(value, str):
            return value.strip()

        return value


class MessageRead(BaseModel):
    """Persisted message returned by the API."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
