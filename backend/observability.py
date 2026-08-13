import json
import logging
import time
import uuid

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from backend.config import Settings
from backend.metrics import (
    http_requests_in_progress,
    observe_http_request,
    route_template,
)
from backend.rate_limit import check_rate_limit


# 使用 Uvicorn 已配置輸出至標準錯誤的 logger，確保 Render 能收集 JSON。
# 只傳入 JSON 字串，不沿用 Uvicorn access logger 的格式化參數。
access_logger = logging.getLogger("uvicorn.error")
access_logger.setLevel(logging.INFO)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Add request correlation, structured access logs, and rate limits."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = str(uuid.uuid4())
        started = time.perf_counter()
        response: Response | None = None
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        http_requests_in_progress.inc()

        try:
            settings = Settings()
            result = await check_rate_limit(request, settings)
            if result and not result.allowed:
                response = JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Too many requests. Please try again later."},
                )
                response.headers["Retry-After"] = str(result.retry_after)
            else:
                response = await call_next(request)

            if result:
                response.headers["X-RateLimit-Limit"] = str(result.limit)
                response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        except RedisError:
            # Redis 暫時失效時讓 API 繼續服務，但留下不含機密的錯誤事件；
            # /ready 會回報依賴異常，讓監控系統能夠告警。
            access_logger.exception("rate_limit_backend_unavailable")
            response = await call_next(request)
        finally:
            duration_seconds = time.perf_counter() - started
            if response is not None:
                status_code = response.status_code

            # call_next 完成後 FastAPI 才會把 matched route 放入 scope；使用
            # `/conversations/{conversation_id}` 這類 template，避免 UUID 形成高基數。
            matched_route = route_template(request.scope)
            observe_http_request(
                method=request.method,
                route=matched_route,
                status_code=status_code,
                duration_seconds=duration_seconds,
            )
            http_requests_in_progress.dec()
            access_logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "route": matched_route,
                        "status_code": status_code,
                        "duration_ms": round(duration_seconds * 1000, 2),
                    },
                    separators=(",", ":"),
                )
            )

        if response is None:
            raise RuntimeError("Request completed without a response.")
        response.headers["X-Request-ID"] = request_id
        return response
