from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


# 使用專案專屬 registry，讓 /metrics 只公開我們刻意定義的 HTTP 指標。
# Label 僅接受有限集合的 method、route template 與 status，不能放 user ID、
# Email、JWT、query 或實際 UUID path，否則會造成機密風險及高基數 time series。
metrics_registry = CollectorRegistry(auto_describe=True)

http_requests_total = Counter(
    "campus_library_http_requests_total",
    "Total HTTP requests completed by the backend API.",
    ("method", "route", "status"),
    registry=metrics_registry,
)

http_request_duration_seconds = Histogram(
    "campus_library_http_request_duration_seconds",
    "Backend HTTP request latency in seconds.",
    ("method", "route"),
    # 這些 bucket 涵蓋一般 API latency，也能辨識資料庫或 cold-start 慢請求。
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
    registry=metrics_registry,
)

http_requests_in_progress = Gauge(
    "campus_library_http_requests_in_progress",
    "HTTP requests currently being processed by this backend process.",
    registry=metrics_registry,
)


def route_template(scope: dict) -> str:
    """Return a bounded route label instead of the concrete request path."""
    route = scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) and path else "unmatched"


def observe_http_request(
    *,
    method: str,
    route: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    """Record one completed request without storing user-controlled values."""
    normalized_method = method.upper()
    http_requests_total.labels(
        method=normalized_method,
        route=route,
        status=str(status_code),
    ).inc()
    http_request_duration_seconds.labels(
        method=normalized_method,
        route=route,
    ).observe(duration_seconds)
