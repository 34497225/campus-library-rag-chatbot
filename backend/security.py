from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from jwt import InvalidTokenError

from backend.config import Settings


_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Convert a plaintext password into an Argon2id hash."""
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Check whether a plaintext password matches an Argon2 hash."""
    try:
        return _password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        return False


def create_access_token(
    subject: str,
    settings: Settings,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token for one user."""

    # 正式 secret 只能從 Settings 取得。
    # 若環境沒有設定或長度不足，require_jwt_secret_key 會立即失敗。
    secret_key = settings.require_jwt_secret_key()

    now = datetime.now(timezone.utc)

    # expires_delta 只用於測試或特殊情況。
    # 一般登入流程會使用環境設定中的有效分鐘數。
    expires_at = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.access_token_expire_minutes)
    )

    # sub 是 token 所代表的使用者 ID。
    # iat 是簽發時間，exp 是到期時間。
    payload = {
        "sub": subject,
        "iat": now,
        "exp": expires_at,
    }

    # 演算法與 secret 都來自集中設定，
    # 避免不同檔案各自保存一套 JWT 參數。
    return jwt.encode(
        payload,
        secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str, settings: Settings) -> str | None:
    """Validate a JWT and return its subject, or None if invalid."""

    # 設定錯誤屬於伺服器問題，因此放在 try 外面。
    # 如果正式環境漏設 secret，應明確報錯，而不是假裝 token 無效。
    secret_key = settings.require_jwt_secret_key()

    try:
        payload = jwt.decode(
            token,
            secret_key,
            # 明確限制可接受的演算法，不能直接相信 token header。
            algorithms=[settings.jwt_algorithm],
        )
    except InvalidTokenError:
        # 過期、簽章錯誤或格式損壞都視為無效 token。
        return None

    subject = payload.get("sub")

    # sub 必須是字串，未來會放 UUID 的字串形式。
    if not isinstance(subject, str):
        return None

    return subject
