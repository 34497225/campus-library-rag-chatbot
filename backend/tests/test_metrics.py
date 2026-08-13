import uuid

from fastapi.testclient import TestClient

from backend.database import get_db_session
from backend.main import app


client = TestClient(app)


def test_metrics_endpoint_exposes_prometheus_format() -> None:
    client.get("/health")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "campus_library_http_requests_total" in response.text
    assert "campus_library_http_request_duration_seconds_bucket" in response.text
    assert 'method="GET",route="/health",status="200"' in response.text


def test_metrics_use_route_template_without_concrete_uuid() -> None:
    conversation_id = str(uuid.uuid4())

    # CI 刻意不配置 production DATABASE_URL；此測試只驗證 middleware 的
    # route label，不需要建立真實 DB session，因此以隔離 dependency 取代。
    def fake_db_session():
        yield object()

    app.dependency_overrides[get_db_session] = fake_db_session
    try:
        response = client.get(f"/conversations/{conversation_id}")
    finally:
        app.dependency_overrides.pop(get_db_session, None)

    metrics_response = client.get("/metrics")

    assert response.status_code == 401
    assert '/conversations/{conversation_id}' in metrics_response.text
    assert conversation_id not in metrics_response.text


def test_metrics_endpoint_is_not_listed_in_public_openapi_schema() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/metrics" not in response.json()["paths"]
