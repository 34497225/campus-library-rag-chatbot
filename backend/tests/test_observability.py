import json
import logging

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.rate_limit import RateLimitResult


client = TestClient(app)


def test_response_has_request_id_and_structured_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="backend.access"):
        response = client.get("/health")

    request_id = response.headers["x-request-id"]
    assert len(request_id) == 36
    records = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "backend.access" and record.message.startswith("{")
    ]
    event = records[-1]
    assert event["event"] == "http_request"
    assert event["request_id"] == request_id
    assert event["path"] == "/health"
    assert event["status_code"] == 200
    assert "duration_ms" in event
    assert "authorization" not in event


def test_health_is_not_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")

    response = client.get("/health")

    assert response.status_code == 200
    assert "x-ratelimit-limit" not in response.headers


def test_rate_limited_response_has_retry_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def deny_request(*_args: object) -> RateLimitResult:
        return RateLimitResult(
            allowed=False,
            limit=10,
            remaining=0,
            retry_after=17,
        )

    monkeypatch.setattr("backend.observability.check_rate_limit", deny_request)

    response = client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "not-a-real-password"},
    )

    assert response.status_code == 429
    assert response.json() == {
        "detail": "Too many requests. Please try again later."
    }
    assert response.headers["retry-after"] == "17"
    assert response.headers["x-ratelimit-limit"] == "10"
    assert response.headers["x-ratelimit-remaining"] == "0"
    assert "x-request-id" in response.headers
