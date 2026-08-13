from scripts.production_monitor import (
    Sample,
    histogram_p95,
    metric_sum,
    parse_prometheus,
)


def test_parse_prometheus_preserves_metric_labels() -> None:
    samples = parse_prometheus(
        '# HELP demo example\nmetric_total{route="/health",status="200"} 3.0\n'
    )

    assert samples == [
        Sample("metric_total", {"route": "/health", "status": "200"}, 3.0)
    ]


def test_metric_sum_filters_by_label_subset() -> None:
    samples = [
        Sample("requests", {"status": "200", "route": "/health"}, 5.0),
        Sample("requests", {"status": "429", "route": "/auth/login"}, 2.0),
    ]

    assert metric_sum(samples, "requests") == 7.0
    assert metric_sum(samples, "requests", status="429") == 2.0


def test_histogram_p95_aggregates_route_buckets() -> None:
    samples = [
        Sample("campus_library_http_request_duration_seconds_bucket", {"route": "/health", "le": "0.5"}, 90),
        Sample("campus_library_http_request_duration_seconds_bucket", {"route": "/health", "le": "1.0"}, 95),
        Sample("campus_library_http_request_duration_seconds_bucket", {"route": "/health", "le": "+Inf"}, 100),
    ]

    assert histogram_p95(samples) == 1.0


def test_histogram_p95_returns_none_without_observations() -> None:
    assert histogram_p95([]) is None
