from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"] == "application/json"


def test_readiness_check_with_available_dependencies(monkeypatch) -> None:
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, _statement):
            return None

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    monkeypatch.setattr("backend.main.get_engine", lambda: FakeEngine())
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
