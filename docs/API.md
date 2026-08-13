# Backend API 使用說明

Production base URL：`https://campus-library-chatbot-api.onrender.com`

互動式文件：`GET /docs`。Render Free instance 休眠後，第一次 request 可能需要等待約 50 秒或更久。

## 共通規則

- Request／response 使用 JSON，刪除成功的 `204` 除外。
- 受保護 endpoint 使用 `Authorization: Bearer <access_token>`。
- 每個 response 都包含 `X-Request-ID`，可用來對照伺服器日誌。
- 受限 endpoint 包含 `X-RateLimit-Limit` 與 `X-RateLimit-Remaining`。
- 超過限制時回 `429`，並包含 `Retry-After` 秒數。
- 驗證失敗回 `401`；資料格式錯誤回 `422`。
- 不存在及不屬於登入者的 conversation 都回相同 `404`。

## System

| Method | Path | Auth | 成功 | 用途 |
| --- | --- | --- | --- | --- |
| GET | `/health` | 否 | 200 | Liveness；只代表 HTTP process 可回應 |
| GET | `/ready` | 否 | 200 | Readiness；確認 PostgreSQL 與 Redis 可用 |
| GET | `/docs` | 否 | 200 | Swagger UI |

`/ready` 依賴異常時回：

```json
{"detail":"Service dependencies are unavailable."}
```

## Authentication

Auth endpoint 共用每分鐘 10 次的 IP rate-limit bucket。

### POST `/auth/register`

```json
{
  "email": "demo@example.com",
  "password": "a-strong-demo-password"
}
```

成功回 `201`，只公開安全欄位：

```json
{
  "id": "user-uuid",
  "email": "demo@example.com",
  "created_at": "2026-08-13T00:00:00Z"
}
```

重複 Email 回 `409`。密碼及 `password_hash` 永遠不在 response 中。

### POST `/auth/login`

Request 與 register 相同。成功回 `200`：

```json
{
  "access_token": "signed-jwt",
  "token_type": "bearer"
}
```

錯誤 Email 或密碼都回相同 `401`，避免直接透露帳號是否存在。

### GET `/auth/me`

需要 Bearer token，成功回目前使用者的 `id`、`email`、`created_at`。

## Conversations

所有 Conversation／Message endpoint 都需要 Bearer token，且只操作目前登入者擁有的資料。一般 API limit 為每分鐘 60 次。

| Method | Path | 成功 | Request body |
| --- | --- | --- | --- |
| POST | `/conversations` | 201 | `{"title":"New conversation"}` |
| GET | `/conversations` | 200 | 無 |
| GET | `/conversations/{id}` | 200 | 無 |
| PATCH | `/conversations/{id}` | 200 | `{"title":"Renamed"}` |
| DELETE | `/conversations/{id}` | 204 | 無 |
| POST | `/conversations/{id}/messages` | 201 | `{"content":"User question"}` |
| GET | `/conversations/{id}/messages` | 200 | 無 |
| POST | `/conversations/{id}/messages/assistant` | 201 | `{"content":"RAG answer"}` |

Client 不能傳入 `user_id` 或 `role`。User message endpoint 固定建立 `role="user"`；assistant endpoint 固定建立 `role="assistant"`。

## PowerShell smoke test

下列範例把 token 保留在目前 PowerShell process，不寫入檔案。請使用一次性測試帳號，完成後不要把 token、密碼或輸出貼進公開 issue。

```powershell
$baseUrl = "https://campus-library-chatbot-api.onrender.com"
$email = "demo-$([guid]::NewGuid())@example.com"
$password = "replace-with-a-temporary-password"

$user = Invoke-RestMethod "$baseUrl/auth/register" `
  -Method Post `
  -ContentType "application/json" `
  -Body (@{ email = $email; password = $password } | ConvertTo-Json)

$login = Invoke-RestMethod "$baseUrl/auth/login" `
  -Method Post `
  -ContentType "application/json" `
  -Body (@{ email = $email; password = $password } | ConvertTo-Json)

$headers = @{ Authorization = "Bearer $($login.access_token)" }

Invoke-RestMethod "$baseUrl/auth/me" -Headers $headers

$conversation = Invoke-RestMethod "$baseUrl/conversations" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json" `
  -Body (@{ title = "API smoke test" } | ConvertTo-Json)

Invoke-RestMethod "$baseUrl/conversations/$($conversation.id)/messages" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json" `
  -Body (@{ content = "When is the library open?" } | ConvertTo-Json)
```

公開環境測試後，應使用受控的資料庫管理流程精準刪除測試帳號；刪除 User 時資料庫 cascade 會同步清除該帳號的 Conversations 與 Messages。

## 錯誤處理摘要

| Status | 意義 |
| --- | --- |
| 401 | 缺少、過期或無效 JWT；或帳密錯誤 |
| 404 | Conversation 不存在或不屬於登入者 |
| 409 | Email 已註冊 |
| 422 | Pydantic request validation 失敗 |
| 429 | 超過 Redis rate limit，依 `Retry-After` 稍後重試 |
| 503 | `/ready` 發現 PostgreSQL 或 Redis 無法使用 |
