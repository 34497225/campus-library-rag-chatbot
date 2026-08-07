from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # FastAPI 日常查詢使用連線池網址。
    database_url: str | None = None

    # Alembic migration 使用直接連線網址。
    direct_database_url: str | None = None

    # 正式 JWT secret 必須由環境變數提供，不能寫死在程式碼。
    # 保留 None，讓不需要 JWT 的測試仍可載入 Settings。
    jwt_secret_key: str | None = None

    # 第一版只允許 HS256，避免環境變數意外指定未知演算法。
    jwt_algorithm: Literal["HS256"] = "HS256"

    # Token 有效時間必須是正整數。
    # 設為 0 或負數會讓剛簽發的 token 立即過期。
    access_token_expire_minutes: int = Field(
        default=60,
        gt=0,
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    def require_database_url(self) -> str:
        """Return the pooled database URL or fail with a clear message."""
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is not configured.")

        return self.database_url

    def require_direct_database_url(self) -> str:
        """Return the direct migration URL or fail with a clear message."""
        if not self.direct_database_url:
            raise RuntimeError("DIRECT_DATABASE_URL is not configured.")

        return self.direct_database_url

    def require_jwt_secret_key(self) -> str:
        """Return a sufficiently long JWT secret or fail safely."""
        if not self.jwt_secret_key:
            raise RuntimeError("JWT_SECRET_KEY is not configured.")

        # HS256 的 HMAC secret 至少使用 32 bytes，
        # 避免和單元測試中剛修正的短密鑰警告一樣不安全。
        if len(self.jwt_secret_key.encode("utf-8")) < 32:
            raise RuntimeError("JWT_SECRET_KEY must be at least 32 bytes.")

        return self.jwt_secret_key
