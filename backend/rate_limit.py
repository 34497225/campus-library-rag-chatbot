import hashlib
import time
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Request
from redis.asyncio import Redis

from backend.config import Settings


# Lua script 將 INCR 與首次設定過期時間放在同一個 Redis 原子操作中，
# 避免多個 Uvicorn worker 同時收到請求時產生競態條件。
_FIXED_WINDOW_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int


@lru_cache
def get_redis_client() -> Redis:
    settings = Settings()
    return Redis.from_url(
        settings.require_redis_url(),
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


def _client_identity(request: Request) -> str:
    """Create a non-reversible identifier without logging tokens or IPs."""
    authorization = request.headers.get("authorization", "")
    forwarded_for = request.headers.get("x-forwarded-for", "")
    peer = forwarded_for.split(",", 1)[0].strip()
    if not peer and request.client:
        peer = request.client.host

    source = authorization if authorization.startswith("Bearer ") else peer
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:24]


def limit_for_request(request: Request, settings: Settings) -> int | None:
    """Return the applicable limit, or None for public read-only endpoints."""
    if request.url.path in {"/auth/register", "/auth/login"}:
        return settings.auth_rate_limit_requests
    if request.url.path.startswith("/conversations"):
        return settings.api_rate_limit_requests
    return None


async def check_rate_limit(
    request: Request,
    settings: Settings,
) -> RateLimitResult | None:
    limit = limit_for_request(request, settings)
    if not settings.rate_limit_enabled or limit is None:
        return None

    window = settings.rate_limit_window_seconds
    window_id = int(time.time()) // window
    identity = _client_identity(request)
    # Conversation UUID 不應形成獨立 bucket，否則攻擊者可換 conversation
    # 來繞過限制；同一身分的所有 conversation routes 共用計數。
    bucket = "auth" if request.url.path.startswith("/auth/") else "conversations"
    key = f"rate-limit:{bucket}:{identity}:{window_id}"

    current, ttl = await get_redis_client().eval(
        _FIXED_WINDOW_SCRIPT,
        1,
        key,
        window,
    )
    current_count = int(current)
    retry_after = max(int(ttl), 1)

    return RateLimitResult(
        allowed=current_count <= limit,
        limit=limit,
        remaining=max(limit - current_count, 0),
        retry_after=retry_after,
    )
