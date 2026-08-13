from fastapi import FastAPI, HTTPException, status
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from backend.auth import router as auth_router

from backend.conversations import router as conversations_router
from backend.config import Settings
from backend.database import get_engine
from backend.metrics import metrics_registry
from backend.observability import ObservabilityMiddleware
from backend.rate_limit import get_redis_client


app = FastAPI(
    title="Campus Library Chatbot API",
    description="Backend API for authentication and conversation management.",
    version="0.1.0",
)

app.add_middleware(ObservabilityMiddleware)

app.include_router(auth_router)
app.include_router(conversations_router)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["system"])
async def readiness_check() -> dict[str, str]:
    """Verify dependencies without exposing connection details."""
    settings = Settings()

    def check_database() -> None:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))

    try:
        await run_in_threadpool(check_database)
        if settings.rate_limit_enabled:
            await get_redis_client().ping()
    except (OSError, RedisError, RuntimeError, SQLAlchemyError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service dependencies are unavailable.",
        ) from None

    return {"status": "ready"}


@app.get("/metrics", include_in_schema=False)
def prometheus_metrics() -> Response:
    """Expose low-cardinality process metrics for a Prometheus scraper."""
    return Response(
        content=generate_latest(metrics_registry),
        media_type=CONTENT_TYPE_LATEST,
    )
