import asyncio
from types import SimpleNamespace

import pytest
from fastapi import Request

from backend.config import Settings
from backend.rate_limit import check_rate_limit, limit_for_request


def make_request(path: str, authorization: str = "") -> Request:
    headers = []
    if authorization:
        headers.append((b"authorization", authorization.encode("utf-8")))
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


def test_limit_policy_separates_auth_and_conversation_routes() -> None:
    settings = Settings(
        _env_file=None,
        auth_rate_limit_requests=5,
        api_rate_limit_requests=30,
    )

    assert limit_for_request(make_request("/auth/login"), settings) == 5
    assert limit_for_request(make_request("/conversations"), settings) == 30
    assert limit_for_request(make_request("/health"), settings) is None


def test_rate_limit_returns_remaining_and_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = SimpleNamespace(eval=lambda *_args: None)

    async def fake_eval(*_args: object) -> list[int]:
        return [3, 42]

    fake_redis.eval = fake_eval
    monkeypatch.setattr("backend.rate_limit.get_redis_client", lambda: fake_redis)
    settings = Settings(
        _env_file=None,
        rate_limit_enabled=True,
        redis_url="redis://example.invalid",
        auth_rate_limit_requests=2,
    )

    result = asyncio.run(check_rate_limit(make_request("/auth/login"), settings))

    assert result is not None
    assert result.allowed is False
    assert result.remaining == 0
    assert result.retry_after == 42
