import json
import logging
import time
import uuid

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from backend.config import Settings
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
        response: Response

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

        response.headers["X-Request-ID"] = request_id
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        access_logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
                separators=(",", ":"),
            )
        )
        return response
