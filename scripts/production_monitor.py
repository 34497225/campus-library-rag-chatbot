"""Probe the public Render API and summarize its Prometheus metrics.

This script intentionally uses only Python's standard library so the scheduled
GitHub Actions monitor has no installation step and no third-party credentials.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://campus-library-chatbot-api.onrender.com"
METRIC_RE = re.compile(
    r'^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(?P<labels>[^}]*)\})?\s+(?P<value>[-+eE0-9.]+)$'
)
LABEL_RE = re.compile(r'(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)="(?P<value>(?:\\.|[^"])*)"')


@dataclass(frozen=True)
class Sample:
    """One parsed Prometheus sample with bounded labels."""

    name: str
    labels: dict[str, str]
    value: float


@dataclass(frozen=True)
class Snapshot:
    """Public, low-cardinality values shown in the Actions dashboard."""

    checked_at_utc: str
    base_url: str
    health: str
    readiness: str
    requests_total: float
    responses_5xx_total: float
    responses_429_total: float
    in_flight: float
    p95_latency_seconds: float | None


def parse_prometheus(text: str) -> list[Sample]:
    """Parse the subset of Prometheus exposition used by this project."""

    samples: list[Sample] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = METRIC_RE.match(line)
        if match is None:
            continue
        labels = {
            item.group("key"): bytes(item.group("value"), "utf-8")
            .decode("unicode_escape")
            for item in LABEL_RE.finditer(match.group("labels") or "")
        }
        samples.append(Sample(match.group("name"), labels, float(match.group("value"))))
    return samples


def histogram_p95(samples: list[Sample]) -> float | None:
    """Aggregate duration buckets and return the first boundary reaching 95%."""

    buckets: dict[float, float] = {}
    for sample in samples:
        if sample.name != "campus_library_http_request_duration_seconds_bucket":
            continue
        boundary_text = sample.labels.get("le")
        if boundary_text is None:
            continue
        boundary = float("inf") if boundary_text == "+Inf" else float(boundary_text)
        buckets[boundary] = buckets.get(boundary, 0.0) + sample.value
    total = buckets.get(float("inf"), 0.0)
    if total <= 0:
        return None
    target = total * 0.95
    for boundary, cumulative in sorted(buckets.items()):
        if cumulative >= target:
            return boundary if boundary != float("inf") else None
    return None


def metric_sum(samples: list[Sample], name: str, **labels: str) -> float:
    """Sum matching samples while allowing a subset of labels."""

    return sum(
        sample.value
        for sample in samples
        if sample.name == name
        and all(sample.labels.get(key) == value for key, value in labels.items())
    )


def fetch_text(url: str, *, attempts: int = 3, timeout: int = 75) -> str:
    """Fetch one endpoint with bounded retries for Render Free cold starts."""

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = Request(url, headers={"User-Agent": "campus-library-production-monitor/1.0"})
            with urlopen(request, timeout=timeout) as response:
                if response.status != 200:
                    raise RuntimeError(f"{url} returned HTTP {response.status}")
                return response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(5 * attempt)
    raise RuntimeError(f"Unable to probe {url}: {last_error}") from last_error


def build_snapshot(base_url: str) -> Snapshot:
    """Probe liveness, dependencies, and aggregate Prometheus metrics."""

    health = json.loads(fetch_text(f"{base_url}/health"))["status"]
    readiness = json.loads(fetch_text(f"{base_url}/ready"))["status"]
    if health != "ok" or readiness != "ready":
        raise RuntimeError(f"Unexpected state: health={health!r}, readiness={readiness!r}")

    samples = parse_prometheus(fetch_text(f"{base_url}/metrics"))
    if not any(sample.name == "campus_library_http_requests_total" for sample in samples):
        raise RuntimeError("Prometheus request counter is missing.")

    request_samples = [
        sample for sample in samples if sample.name == "campus_library_http_requests_total"
    ]
    return Snapshot(
        checked_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        base_url=base_url,
        health=health,
        readiness=readiness,
        requests_total=sum(sample.value for sample in request_samples),
        responses_5xx_total=sum(
            sample.value
            for sample in request_samples
            if sample.labels.get("status", "").startswith("5")
        ),
        responses_429_total=metric_sum(
            samples, "campus_library_http_requests_total", status="429"
        ),
        in_flight=metric_sum(samples, "campus_library_http_requests_in_progress"),
        p95_latency_seconds=histogram_p95(samples),
    )


def render_markdown(snapshot: Snapshot) -> str:
    """Render the external monitoring dashboard shown in the workflow summary."""

    p95 = "no observations" if snapshot.p95_latency_seconds is None else f"≤ {snapshot.p95_latency_seconds:g} s"
    return "\n".join(
        [
            "# Campus Library production dashboard",
            "",
            f"Checked externally at `{snapshot.checked_at_utc}`.",
            "",
            "| Signal | Latest value |",
            "| --- | ---: |",
            f"| Health | `{snapshot.health}` |",
            f"| Readiness | `{snapshot.readiness}` |",
            f"| HTTP requests since deploy | {snapshot.requests_total:g} |",
            f"| HTTP 5xx since deploy | {snapshot.responses_5xx_total:g} |",
            f"| HTTP 429 since deploy | {snapshot.responses_429_total:g} |",
            f"| In-flight requests | {snapshot.in_flight:g} |",
            f"| Approximate p95 latency bucket | {p95} |",
            "",
            "> Counters reset when the free Render instance restarts. The p95 value is a",
            "> Prometheus histogram bucket boundary, not a contractual SLA.",
        ]
    )


def main() -> int:
    """Write JSON evidence and a GitHub Actions dashboard summary."""

    base_url = os.getenv("MONITOR_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    snapshot = build_snapshot(base_url)
    print(json.dumps(asdict(snapshot), ensure_ascii=False, sort_keys=True))

    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        Path(summary_path).write_text(render_markdown(snapshot) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
