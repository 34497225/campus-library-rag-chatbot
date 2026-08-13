# Production Metrics 與告警操作說明

後端公開 `GET /metrics`，輸出 Prometheus text exposition format。此 endpoint 供 scraper 讀取，不列入 Swagger；它不包含 request body、query string、Email、JWT、使用者 ID、實際 Conversation UUID 或任何連線字串。

## 指標

| Metric | Type | Labels | 用途 |
| --- | --- | --- | --- |
| `campus_library_http_requests_total` | Counter | `method`, `route`, `status` | request 數量、5xx／429 比率與流量 |
| `campus_library_http_request_duration_seconds` | Histogram | `method`, `route` | p50／p95／p99 latency |
| `campus_library_http_requests_in_progress` | Gauge | 無 | 單一 process 目前處理中的 request |

`route` 使用 `/conversations/{conversation_id}` 這類 FastAPI route template。未知路徑統一記成 `unmatched`，因此任意 UUID 或惡意 path 不會建立無限 time series。

## 建議 PromQL

以下查詢假設 scraper 每 15～60 秒收集一次。

### 每秒 request 數

```promql
sum(rate(campus_library_http_requests_total[5m]))
```

### 5xx 比率

```promql
sum(rate(campus_library_http_requests_total{status=~"5.."}[5m]))
/
clamp_min(sum(rate(campus_library_http_requests_total[5m])), 0.001)
```

### p95 latency

```promql
histogram_quantile(
  0.95,
  sum by (le) (rate(campus_library_http_request_duration_seconds_bucket[5m]))
)
```

### 429 比率

```promql
sum(rate(campus_library_http_requests_total{status="429"}[5m]))
/
clamp_min(sum(rate(campus_library_http_requests_total[5m])), 0.001)
```

## 建議告警門檻

這些是低流量作品展示環境的起點，不是假裝已存在的 SLA。接上實際 Prometheus／Grafana 或其他監控平台後，應先觀察一至兩週 baseline 再調整。

- Availability：`/ready` 連續 5 分鐘不是 200。
- Error rate：5xx 比率連續 10 分鐘高於 5%，且同期間至少 20 requests。
- Latency：非冷啟動期間 p95 連續 10 分鐘高於 2.5 秒。
- Rate limit：429 比率連續 10 分鐘高於 20%，確認是否遭濫用或限制過嚴。
- No traffic：預期展示時段完全沒有 scrape 或 request，檢查 Render 是否休眠或 scraper 是否失效。

## 事故排查順序

1. 呼叫 `/health`：確認 process 能回應 HTTP。
2. 呼叫 `/ready`：確認 PostgreSQL 與 Redis dependency。
3. 查看 `/metrics`：判斷錯誤率、受影響 route 與 latency 是否異常。
4. 以 response 的 `X-Request-ID` 搜尋 Render JSON log。
5. 檢查最近 GitHub merge、Render deployment 與 Alembic revision。
6. 若涉及資料，先停止破壞性操作並確認 Neon restore point／branch，再進行還原演練。

## 目前限制

- Render Free instance 休眠時不能持續提供 process metrics；外部 scraper 的失敗本身才是 availability signal。
- 目前只有單一 Uvicorn process。若未來改成多 worker，必須依 Prometheus Python client 的 multiprocess 模式重新設計 Gauge 與 registry。
- 本階段提供 metrics 與 runbook，沒有宣稱已購買 Grafana Cloud、PagerDuty、常駐 Render 或正式 on-call SLA。
