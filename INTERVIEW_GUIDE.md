# 校園圖書館 RAG 智能客服：面試知識與回答指南

最後更新：2026-08-13

## 1. 文件用途

這份文件整理本專案已實作、已測試及可在面試中說明的技術。每個完整開發階段結束後都要更新：

1. 新增本階段使用的技術與設計理由。
2. 補充測試、安全邊界與實際驗證結果。
3. 明確區分「已完成」、「進行中」及「規劃中」，避免履歷或面試中過度宣稱。
4. 不記錄 API key、JWT secret、密碼或資料庫連線字串。

## 2. 一分鐘專案介紹

這是一個以 Python 開發的校園圖書館文件型 RAG 智能客服。前端使用 Streamlit，能載入範例 FAQ 或使用者上傳的 PDF／CSV，將文件切分後透過 OpenAI Embeddings 建立 FAISS 向量索引，再檢索相關片段交給語言模型回答。後端使用 FastAPI、SQLAlchemy、Alembic 與 Neon PostgreSQL，已完成 Argon2 密碼雜湊、JWT 身分驗證，以及具備使用者資料隔離的 Conversation／Message 資料層與 CRUD API。後端已透過 Render Blueprint 部署至 Singapore，GitHub Actions required checks 通過後由 `main` 自動部署。

面試時可以用以下四點快速建立脈絡：

- RAG：回答以文件檢索內容為依據，降低模型憑空回答。
- Backend：以 FastAPI 分離 HTTP、驗證、repository 與 ORM 責任。
- Security：密碼使用 Argon2id、JWT secret 由環境提供、資料查詢綁定 authenticated user。
- Engineering：Alembic 管理 schema、pytest 隔離測試、PR 與 required CI 保護 main。

## 3. 目前完成狀態

| 階段 | 狀態 | 可驗證成果 |
| --- | --- | --- |
| Streamlit RAG 展示版 | 已完成 | PDF／CSV、FAISS、OpenAI、雙語介面、來源與 Markdown 匯出 |
| GitHub CI 與 main 保護 | 已完成 | 前後端 jobs、PR required checks |
| FastAPI／Neon／Alembic 基礎 | 已完成 | `/health`、Users migration、development branch 驗證 |
| Auth foundation | 已完成 | register、login、me、Argon2id、JWT、55 項後端測試時完成 |
| Conversation data foundation | 已完成 | ORM、migration、schemas、owner-filtered repositories、85 項後端測試時完成 |
| Conversation CRUD API | 已完成 | 7 個受 JWT 保護的 CRUD／Message endpoints、20 項 API tests、Neon development smoke test |
| Streamlit 身分驗證 UI | 已完成 | register、login、logout、Bearer `/auth/me`、安全錯誤呈現、31 項前端測試與瀏覽器 E2E |
| Streamlit 持久化對話歷史 | 已完成 | 登入後可建立、切換、改名、刪除及重新載入個人 RAG 對話；前端 47、後端 108 項測試 |
| Render 後端部署 | 已完成 | Singapore Blueprint、Alembic、公開 HTTPS、health／Swagger／Auth／Conversation production smoke test |
| Production 端到端驗收 | 已完成 | Streamlit Cloud → Render → Neon → OpenAI；重新登入還原歷史、跨帳號隔離與錯誤流程通過 |
| Redis／observability | 已完成 | Render Key Value、跨 instance 固定視窗限流、429 headers、request ID、JSON access log、readiness probe |

## 4. 整體架構

```text
使用者
  ↓
Streamlit
  ├─ 文件載入與切分
  ├─ OpenAI Embeddings
  ├─ FAISS similarity search
  └─ OpenAI Chat Model

Streamlit
  ↓ HTTP + Bearer JWT
FastAPI
  ├─ Router／Pydantic schemas
  ├─ Dependency injection／authentication
  ├─ Repository
  └─ SQLAlchemy ORM
       ↓
Neon PostgreSQL

GitHub Pull Request
  ↓
GitHub Actions 前後端 CI
  ↓
protected main
  ↓ checks passed
Render Blueprint（Singapore）
  ↓ Alembic upgrade head → Uvicorn
Neon production
```

### 為什麼前後端分離？

- Streamlit 專注互動介面、文件處理與 RAG 體驗。
- FastAPI 專注帳號、授權、對話資料與可重用 HTTP API。
- 資料庫密碼與 JWT secret 只配置在後端環境。
- 未來可以更換前端，而不必重寫帳號與資料存取邏輯。

## 5. RAG 核心知識

### 5.1 什麼是 RAG？

RAG 是 Retrieval-Augmented Generation，流程不是直接把問題交給模型，而是先從知識文件找出相關內容，再把內容和問題一起交給模型。

```text
文件 → 切分 → Embedding → Vector Store
                           ↑
問題 → Embedding → 相似度搜尋 → 相關片段 → LLM 回答
```

優點：

- 回答可依據指定文件，而不是只依賴模型訓練知識。
- 可以替換文件，不需要重新訓練模型。
- 能顯示來源片段，改善可追溯性。

限制：

- 檢索不到正確片段時，生成品質仍會下降。
- RAG 降低但不能完全消除 hallucination。
- 文件解析、chunk 策略及 embedding 品質都會影響結果。

### 5.2 文件載入

- PDF 使用 `PyPDFLoader`。
- CSV 使用 `CSVLoader` 與 UTF-8 編碼。
- 上傳檔先寫入 temporary file，解析後在 `finally` 刪除。
- 不永久保存使用者上傳文件。
- 文件 metadata 加入 `source_name`，用於顯示證據來源。

面試追問：為什麼需要 temporary file？

> 部分 loader 接受檔案路徑而不是純 bytes，所以先建立暫存檔；使用 `try/finally` 確保成功或失敗都會清理，避免長期保存上傳資料。

### 5.3 Chunking

本專案使用 `RecursiveCharacterTextSplitter`：

- `chunk_size=800`
- `chunk_overlap=120`
- 最多 100 個 chunks

chunk 太大會混入過多不相關內容並增加 token；太小則可能切斷語意。Overlap 保留相鄰片段的上下文，但會增加索引量和成本。

### 5.4 Embeddings 與 FAISS

- Embedding model 預設 `text-embedding-3-small`。
- Embedding 將文字映射成向量，使語意相近文字在向量空間距離較近。
- FAISS 是本機向量索引，適合展示版與單一工作階段快速檢索。
- 每次文件來源改變會重建索引；目前不做跨工作階段持久化。
- 自訂 `DirectOpenAIEmbeddings` adapter，直接呼叫既有 OpenAI Embedding API，避開舊版 LangChain tokenizer 額外下載問題。

面試追問：為什麼不用 PostgreSQL pgvector？

> 第一版展示範圍小且不永久保存上傳文件，FAISS 建立快速、架構較簡單。若需求改成多使用者大量文件與持久化檢索，會評估 pgvector 或 managed vector database。

### 5.5 Retrieval 與 Prompt

- 使用 `similarity_search(question, k=3)` 取三段相關內容。
- chain type 是 `stuff`，將少量檢索片段直接放入 prompt。
- Chat model 預設 `gpt-4o-mini`。
- `temperature=0.2`，偏向穩定、少發散的客服回答。
- `max_tokens=800` 控制回答長度與成本。
- Prompt 要求只根據 context 回答；不足時友善說明，不捏造答案。
- 簡單招呼獨立處理，避免對「你好」回答文件不足。

### 5.6 有限對話脈絡

- `format_history()` 取最後六則訊息，也就是約三組問答。
- 目的是支援「那週末呢？」這類追問，同時避免 prompt 無限增長。
- 完整訊息會保存到 FastAPI／PostgreSQL；每次產生 prompt 時仍只取最近六則，避免持久化歷史讓 token 無限制成長。
- 瀏覽器整頁重新整理後需重新登入，但登入完成會依 active conversation 從 API 還原歷史。

## 6. Streamlit 知識

### 6.1 Session State

保存：

- access token 與 `/auth/me` 回傳的安全使用者欄位
- messages
- conversation list、active／loaded conversation ID
- 尚未成功持久化的 assistant retry payload
- question count
- token count
- active source ID／name
- FAISS vector store

Streamlit 每次互動會重新執行 script，因此需要 `st.session_state` 保存工作階段狀態。

登入成功後，前端先取得 access token，再立刻用 Bearer token 呼叫 `/auth/me`。只有兩個步驟都成功，才把 token 與 `id`、`email`、`created_at` 放入 session state。密碼、password hash 與 JWT secret 永遠不進入前端 state。

目前登入狀態只跨 Streamlit rerun 保存；瀏覽器整頁重新整理會建立新 session 並要求重新登入。這是第一版刻意的安全／複雜度取捨，沒有把 JWT 放進 URL、localStorage 或未設安全旗標的自製 cookie。

### 6.2 文件快取判斷

上傳內容以 SHA-256 產生短 digest，搭配檔名形成 source ID。只有來源改變才重建 vector store，避免每次畫面 rerun 都重算 embeddings。

### 6.3 展示限制

- 檔案最多 5 MB。
- 文件最多 100 chunks。
- 每工作階段最多 10 題。

這些限制用來控制記憶體與 OpenAI API 成本；後端另以 Render Key Value 實作跨程序 Redis 限流，保護 Auth 與 Conversation API。

### 6.4 錯誤分類

介面把錯誤區分為：

- Billing／帳戶未啟用。
- Invalid API key。
- Rate limit。
- Timeout／connection。
- Unknown error。

面試重點：不要把所有外部 API 失敗都說成金鑰錯誤；先辨認失敗層級。

### 6.5 Streamlit 與 FastAPI 的 HTTP 邊界

- `frontend_api.py` 集中處理 backend base URL、timeout、JSON 解析及 HTTP 錯誤。
- base URL 會去除多餘 `/`，避免路徑組合錯誤。
- requests timeout 固定為 10 秒，避免 UI 無限等待。
- 401、409、422、timeout、connection error 會轉成不洩漏內部 response 或 stack trace 的前端錯誤。
- 登入 response 除了 200，還會驗證 `access_token` 非空且 `token_type` 為 `bearer`。
- `frontend_auth.py` 將純 session-state 規則與 Streamlit widget 分離，讓登入狀態能以單元測試驗證。
- `frontend_conversations.py` 將 Conversation／Message response 白名單、active selection、history 載入與登出清理分離成可測試的純 Python helper。
- protected path 中的 UUID 會先解析並正規化，避免任意字串成為 URL path fragment。

### 6.6 為什麼回答完成後不再呼叫 `st.rerun()`？

`st.chat_input` 送出本身已啟動一次 script run。回答完成後再次強制 rerun，固定在底部的輸入元件可能重新錨定捲動位置，造成使用者從底部往上閱讀時被拉回。現在使用 `st.empty()` 預留統計元件並直接更新 metric，不需要整頁再次 rerun；瀏覽器驗收確認由底部向上捲動後位置保持穩定。

### 6.7 個人對話持久化資料流

```text
登入使用者選擇 Conversation
  → GET /conversations/{id}/messages
  → 轉換成 st.session_state.messages
  → 使用者送出問題
  → 先 POST user message
  → RAG 檢索與回答
  → POST assistant message
```

- sidebar 支援建立、切換、改名與刪除自己的對話。
- 沒有 active conversation 時，以第一個問題自動產生最多 60 字元標題。
- user message 保存失敗時不呼叫 OpenAI，避免付費產生一個無法追溯的回答。
- RAG 成功但 assistant message 保存失敗時，畫面保留答案並保存 retry payload，讓使用者補寫，而不是誤稱已持久化。
- 對話切換時只載入該 Conversation 的 messages；後端 owner-filtered query 是真正授權邊界。
- token 數沒有寫入 Message table，因此重新載入歷史後 token metric 從 0 開始，避免虛構數字。

## 7. FastAPI 分層

### 7.1 Router

- `auth.py` 負責 `/auth`。
- `conversations.py` 負責 `/conversations`。
- `main.py` 建立 app 並 `include_router()`。
- `tags` 用於 Swagger 分組。
- `response_model` 定義對外輸出契約。
- `/messages/assistant` 使用 dedicated endpoint，由伺服器固定 `role="assistant"`；一般 Message payload 仍不能注入 role。

### 7.2 Dependency Injection

FastAPI `Depends` 注入：

- `get_db_session`：每個 request 的 SQLAlchemy Session。
- `get_settings`：環境設定。
- `get_current_user`：Bearer token 驗證後的 ORM User。

優點：

- endpoint 不自行建立資料庫連線或解析 JWT。
- 測試可以使用 `app.dependency_overrides` 替換依賴。
- 驗證失敗會在 endpoint 商業邏輯執行前中止。

### 7.3 HTTP 狀態碼

- `200 OK`：一般讀取、登入、更新。
- `201 Created`：註冊、建立對話或訊息。
- `204 No Content`：成功刪除且不回傳 body。
- `401 Unauthorized`：缺少或無效身分驗證。
- `404 Not Found`：資源不存在或不屬於目前使用者。
- `409 Conflict`：Email 重複等資源衝突。
- `422 Unprocessable Entity`：JSON 欄位未通過 Pydantic 驗證。

## 8. Pydantic 與 API 契約

### 8.1 Request／Response 分離

- `UserCreate` 接收 email、password。
- `UserRead` 只輸出 id、email、created_at。
- `ConversationCreate`／`ConversationUpdate` 接收 title。
- `ConversationRead` 不輸出 owner ID。
- `MessageCreate` 只接收 content。
- `MessageRead` 輸出由伺服器決定的 role。

分離的原因是避免直接序列化 ORM 的敏感欄位，例如 `password_hash`。

### 8.2 正規化與限制

- Email 去頭尾空白並轉小寫。
- Conversation title 去頭尾空白，長度 1～200。
- Message content 去頭尾空白，長度 1～20,000。
- `extra="forbid"` 拒絕未宣告欄位。
- `from_attributes=True` 允許從 ORM object 建立 response。

安全例子：

- Conversation request 不能注入 `user_id`。
- Message request 不能注入 `role="assistant"`。

## 9. SQLAlchemy ORM 與 Repository

### 9.1 為什麼使用 ORM？

ORM 把資料表映射成 Python objects，統一型別、relationship 與 transaction 操作；複雜或效能敏感查詢仍可以使用 SQLAlchemy expression 明確撰寫 SQL 條件。

### 9.2 Models

User：

- UUID primary key。
- unique／indexed email。
- password hash。
- timezone-aware created time。

Conversation：

- UUID primary key。
- `user_id` foreign key 與 index。
- title、created_at、updated_at。
- 一位 User 對多筆 Conversations。

Message：

- UUID primary key。
- `conversation_id` foreign key 與 index。
- role、content、created_at。
- 一筆 Conversation 對多筆 Messages。

### 9.3 UUID 的取捨

優點：

- 不透露資料筆數或建立順序。
- 多節點可各自產生 ID。

限制：

- 比整數占更多空間。
- 隨機 UUID 的 index locality 較差。
- UUID 不是授權機制；知道 UUID 仍必須通過 owner check。

### 9.4 Repository Pattern

Repository 集中資料存取：

- endpoint 處理 HTTP 語意。
- schema 處理輸入輸出驗證。
- repository 處理查詢、commit、rollback。
- model 描述資料表。

Owner-filtered query 會在同一個 SQL WHERE 中同時限制：

```text
Conversation.id == requested_id
Conversation.user_id == authenticated_user.id
```

不先只依 ID 讀出資料再於 Python 判斷，能降低日後忘記授權檢查的風險。

### 9.5 Transaction

- 寫入成功後 `commit()`。
- 失敗後必須 `rollback()`，否則 Session 仍處於失敗交易狀態。
- `refresh()` 讀回資料庫產生的 timestamp 等欄位。
- `expire_on_commit=False` 讓 commit 後 ORM object 屬性仍可供 response 使用。

### 9.6 Cascade

- 刪除 User 連帶刪除 Conversations 與 Messages。
- 刪除 Conversation 連帶刪除 Messages。
- ORM relationship 使用 `cascade="all, delete-orphan"`。
- Database foreign key 使用 `ON DELETE CASCADE`。
- `passive_deletes=True` 讓資料庫執行 cascade。

雙層設計讓 ORM 操作與直接 SQL 刪除都能維持資料完整性。

## 10. PostgreSQL、Neon 與 Alembic

### 10.1 Neon branch

- production 是預設分支。
- development 用於目前開發與 migration 驗收。
- 測試不連 Neon，而使用隔離 SQLite。

資料庫 branch 和 Git branch 是兩套不同概念：Git branch 管程式碼；Neon branch 管資料庫 schema／data。

### 10.2 Pooled 與 Direct URL

- FastAPI 日常 request 使用 pooled `DATABASE_URL`。
- Alembic migration 使用 direct `DIRECT_DATABASE_URL`。
- `pool_pre_ping=True` 在取用連線時檢查失效連線。

### 10.3 Alembic

已完成 revisions：

- `6e51fbe701b3`：users table。
- `37b4f29eb2f9`：conversations 與 messages tables。

重要命令概念：

- `revision --autogenerate`：比較 ORM metadata 與目前 database schema，產生候選 migration。
- 人工閱讀 migration：autogenerate 不是絕對正確。
- `upgrade head`：套用到最新版。
- `downgrade <revision>`：驗證可逆性。
- `current`：讀取 database 現在的 revision。
- `check`：確認 ORM metadata 沒有尚未產生的 schema 差異。

## 11. 密碼安全與 Argon2id

- 明文密碼不進 repository、不進資料庫、不進 response。
- `argon2-cffi` 產生 Argon2id hash。
- 每次 hash 使用不同 salt，所以相同密碼會有不同結果。
- 登入使用 verify，不把 hash 解密；安全密碼 hash 本來就是不可逆。
- 無效 hash 安全回傳驗證失敗。
- Email 不存在時仍驗證 dummy Argon2 hash，降低帳號存在與否的回應時間差。
- Email unique index 是 race condition 下的最後防線；應用層預查只用來提供友善 409。

面試追問：hash 和 encryption 差別？

> Encryption 可用 key 還原，適合需要取回原文的資料；password 不需要取回，因此使用單向且刻意昂貴的 password hashing algorithm。

## 12. JWT 與身分驗證

### 12.1 Access Token

- PyJWT。
- HS256。
- `sub` 保存 User UUID 字串。
- `iat` 保存簽發時間。
- `exp` 保存過期時間。
- 預設有效時間 60 分鐘，必須大於 0。
- secret 至少 32 bytes，只從環境設定取得。

JWT 是簽章 token，不是加密容器；payload 不應放密碼或其他機密。

### 12.2 Bearer 驗證流程

```text
Authorization header
  → HTTPBearer
  → 驗證簽章、algorithm、exp
  → 讀取 sub
  → UUID parsing
  → 查詢 User
  → current_user
```

缺少、無效、過期 token、非 UUID subject 或已刪除使用者，統一回覆 401，避免洩漏內部失敗細節。

### 12.3 目前刻意不做的功能

- Refresh token。
- Email verification。
- Forgot password。
- OAuth。
- Admin backend。

第一版優先完成可展示的安全主流程，再逐步增加功能。

## 13. Authorization 與資料隔離

Authentication 回答「你是誰」；Authorization 回答「你能操作什麼」。JWT 驗證成功不代表可以讀取任意 conversation。

核心原則：

- owner ID 永遠取自 `current_user.id`。
- 不接受 request body／query parameter 指定 owner。
- list query 必須以 owner ID 過濾。
- read／update／delete 同時比對 resource ID 與 owner ID。
- 不存在和別人的資源使用相同 404，降低 resource enumeration。
- Message create／list 先驗證 parent conversation 的 owner。

### 13.1 Conversation CRUD API

已完成的 endpoints：

| Method | Path | 成功狀態 | 用途 |
| --- | --- | --- | --- |
| POST | `/conversations` | 201 | 建立目前使用者的對話 |
| GET | `/conversations` | 200 | 列出目前使用者的對話 |
| GET | `/conversations/{conversation_id}` | 200 | 讀取一筆自己的對話 |
| PATCH | `/conversations/{conversation_id}` | 200 | 修改自己的對話標題 |
| DELETE | `/conversations/{conversation_id}` | 204 | 刪除自己的對話與 dependent messages |
| POST | `/conversations/{conversation_id}/messages` | 201 | 在自己的對話建立 user message |
| GET | `/conversations/{conversation_id}/messages` | 200 | 列出自己對話中的 messages |

設計重點：

- Endpoint 只負責 HTTP、dependency 與 response schema；SQL 查詢留在 repository。
- 所有 endpoints 使用 `get_current_user`，沒有讓 caller 傳入 owner ID。
- `GET /conversations` 在沒有資料時回 `[]`，不是 404。
- Message list 用 `None` 區分「conversation 不可存取」，用空 list 表示「可存取但尚無訊息」。
- Client 建立 message 時只能傳 content；伺服器固定 role 為 `user`。
- Assistant role 保留給未來受信任的後端 RAG 流程，不讓 client 冒充。
- 刪除成功使用 204 且 response body 為空。
- UUID path parameter 由 FastAPI 驗證；格式錯誤在 endpoint 前回 422。

### 13.2 404 與 403 的取捨

本專案對「不存在」與「存在但屬於別人」都回：

```json
{"detail": "Conversation not found."}
```

若對別人的資料回 403，攻擊者可以判斷某個 UUID 確實存在。統一 404 能減少 resource enumeration 資訊洩漏，但 server logs／observability 仍可在內部區分失敗原因。

### 13.3 Conversation API 階段驗證

- Conversation API tests：20 passed。
- 完整 backend tests：105 passed。
- Frontend tests：5 passed。
- 前後端 `pip check`：無 broken requirements。
- OpenAPI 已列出 `/conversations`、`/{conversation_id}` 與 `/messages` paths。
- Alembic current：`37b4f29eb2f9 (head)`。
- Alembic check：無新的 upgrade operations。
- Neon development smoke test 驗證 register、login、conversation create/list/read/rename/delete、message create/list，以及刪除後 404。
- Smoke test 使用隨機臨時 Email，完成後刪除臨時 User，透過 cascade 一併清理資料。

## 14. 測試策略

### 14.1 測試金字塔在本專案的使用

- 純函式／schema tests：快速驗證邊界。
- repository tests：驗證 SQLAlchemy query、transaction、constraint。
- API integration tests：TestClient 經過 router、dependency、schema、repository。
- 手動 Swagger／Neon 驗收：驗證真實設定與 PostgreSQL 行為。

### 14.2 隔離 SQLite

- `sqlite+pysqlite:///:memory:`。
- `StaticPool` 讓 TestClient 不同 Session 共用同一個記憶體 database。
- `check_same_thread=False` 配合 TestClient 執行模型。
- `Base.metadata.create_all()` 建立測試 schema。
- dependency override 替換正式 database session 與 settings。
- 測試完成清除 overrides、drop tables、dispose engine。
- cascade tests 明確啟用 SQLite foreign keys。

### 14.3 測試不做什麼

- 不連 production Neon。
- 不呼叫真實 OpenAI API。
- 不使用真實 JWT secret。
- 不用 timing threshold 測防枚舉，避免 CI 不穩；改用 mock 驗證 dummy hash 路徑確實執行。

### 14.4 重要測試案例

- Argon2 salt、正確／錯誤密碼、無效 hash。
- JWT wrong secret、expired、invalid、bad subject。
- Email normalization、password／title／message boundary。
- Duplicate email 與 rollback。
- Owner A 無法讀、改、刪 Owner B conversation。
- Owner A 無法在 Owner B conversation 建立或列出 messages。
- Invalid message role 被 database constraint 拒絕。
- Conversation／User deletion cascade。
- API response 不洩漏 password hash、user ID 或可注入 role。
- Conversation list 不混入其他 owner 的資料。
- Read／rename／delete 對 inaccessible 與 missing conversation 使用相同 404。
- 所有 Conversation／Message endpoints 缺少 Bearer token 時回 401。
- Message API 正確區分 owned empty list 與 inaccessible conversation。

## 15. GitHub Actions 與開發流程

CI 在 push main 與 PR main 時執行兩個 jobs：

Frontend job：

- Python 3.11。
- pip cache。
- 安裝 frontend dev requirements。
- `py_compile app.py`。
- `pytest tests -q`。

Backend job：

- Python 3.11。
- pip cache。
- 安裝 backend dev requirements。
- backend syntax check。
- `pytest backend/tests -q`。

Repository workflow：

```text
main 同步
  → feature branch
  → 小型可驗證單元
  → 完整測試
  → staged diff／格式／機密檢查
  → commit／push
  → Pull Request
  → required CI
  → merge
  → 合併後重新測試與清理分支
```

main 禁止直接 push、force push 與刪除，降低未驗證變更進入穩定分支的風險。

## 16. Security Checklist

- `.env` 在 `.gitignore`。
- API key、database URL、JWT secret 不提交。
- `.env.example` 只保存 placeholder。
- Password 使用 Argon2id，不保存明文。
- JWT algorithm 固定 HS256，不從 token header 任意接受。
- JWT secret 長度驗證。
- Pydantic request 禁止 owner／role injection。
- Response schema 過濾敏感欄位。
- Owner-filtered SQL query。
- 統一 authentication error 與 inaccessible resource 行為。
- 測試及 CI 不接 production services。
- 提交前檢查 staged file list、完整 diff、格式與 secret patterns。

## 17. 設計取捨與誠實限制

### 同步 SQLAlchemy，而不是 async

目前流量與專題範圍不需要增加 async database 複雜度。同步 Session 容易理解、測試及維護。若高併發 request 大量等待 I/O，再評估 async engine/session。

### FAISS，而不是持久化 vector database

展示版文件量小、不永久保存上傳資料。代價是重啟或切換文件要重建索引，不能跨使用者共享大型知識庫。

### Access token only

第一版流程簡單；token 過期後需重新登入。正式產品會再評估 refresh token rotation、revocation 與裝置管理。

### SQLite tests + PostgreSQL manual verification

SQLite 提供快速隔離測試，但型別、constraint、timezone 與 SQL 行為可能和 PostgreSQL 不完全相同，因此 migration 必須在 Neon development 做 upgrade／downgrade／schema 驗證。

### Session question limit 與分散式限流的分工

Streamlit session limit 控制單次使用者體驗與 LLM 成本；Redis rate limiting 則讓所有 Uvicorn instance 共用計數，無法藉由重開前端 session 規避。Auth 端點依來源 IP 的雜湊識別，受保護 API 優先依 Bearer token 的雜湊識別，Redis key 不保存原始 IP 或 token。

## 18. 常見面試問題與回答方向

### Q1：這個專案最困難的部分是什麼？

可以回答資料擁有權不是只在 UI 隱藏，而是從 JWT current user 一路帶到 repository SQL WHERE，並用兩位使用者的 API／repository tests 證明隔離。這同時涉及 authentication、authorization、ORM query 與測試設計。

### Q2：你如何降低 hallucination？

使用文件檢索、k=3 context、低 temperature、限定 prompt 只能依 context 回答、不足時使用 fallback，並顯示來源。也要誠實說無法完全消除，檢索品質仍是關鍵。

### Q3：為什麼使用 Alembic，不直接 create_all？

`create_all` 適合測試或全新資料庫，不能可靠記錄 production schema 的逐步演進。Alembic revision 可版本化、review、upgrade／downgrade並由 `alembic_version` 確認狀態。

### Q4：如何避免帳號枚舉？

登入錯誤使用一致訊息；不存在 email 仍執行 dummy Argon2 verify；private resource 不存在與不屬於使用者都回 404。

### Q5：JWT 的風險是什麼？

JWT 被竊取後在過期前可被使用，所以必須 HTTPS、短效期、妥善保存、不可放敏感 payload。正式系統還需 refresh rotation、revocation 或 session/device strategy。

### Q6：為什麼資料庫 constraint 和 Pydantic 都要驗證？

Pydantic 提供快速友善的 API 錯誤；database constraint 是所有寫入路徑的最後防線，包含 script、migration 或未來其他服務。

### Q7：你如何處理 transaction failure？

Repository 在 commit 發生 SQLAlchemyError 時 rollback 再 re-raise；測試會故意觸發 duplicate email 或 invalid role，並確認 Session 後續仍可使用且沒有半完成資料。

### Q8：測試為什麼使用 dependency override？

Endpoint 不需要為測試寫特殊分支。FastAPI override 可以替換 database session 與 settings，使 TestClient 走完整 HTTP pipeline 但不接觸 Neon 或真實 secrets。

### Q9：如果要擴充到正式服務，下一步是什麼？

Streamlit JWT、個人對話持久化、Render backend、Redis rate limiting 與基礎 observability 已完成。接下來可整理公開作品文件，再視需求加入 refresh token、集中式 metrics／tracing 與更完整 backup 策略。

### Q10：你如何證明不是只把套件拼在一起？

說明實際處理的邊界：舊 LangChain tokenizer 問題用 adapter 解決；密碼 timing path 用 mock 測行為；owner isolation 放進 SQL WHERE；Alembic 在 Neon development 做往返驗證；前端 HTTP failure 用 mock 隔離；捲動問題則定位為重複 rerun，改用 placeholder 局部更新；CI 與 branch protection 把驗證納入合併流程。

### Q11：為什麼前端登入後還要呼叫 `/auth/me`？

login 只證明帳密驗證成功並取得 token；`/auth/me` 會用相同 Bearer token 走後端真正的 JWT dependency，確認 token 能用並取得安全的使用者輸出。前端只有兩步都成功才建立 authenticated session，避免保存不完整或格式錯誤的 login response。

### Q12：為什麼不用瀏覽器 localStorage 長期保存 JWT？

第一版把 JWT 限制在 Streamlit server-side session state，瀏覽器整頁重新整理後重新登入。localStorage 容易被同源 XSS 讀取；自製 cookie 若沒有 HttpOnly、Secure、SameSite 與 CSRF 設計也可能更危險。正式版若要求長期登入，會優先設計後端管理的安全 cookie、短效 access token、refresh rotation 與撤銷機制。

### Q13：如何處理「問題已存，但 AI 回答沒存」的不一致？

先保存 user message，成功後才呼叫 RAG；這確保每次付費回答都有可追溯問題。若 RAG 本身失敗，資料庫保留問題並顯示錯誤；若回答成功但第二次 API 寫入失敗，前端保留畫面答案及 pending retry payload，讓使用者補存。正式系統可把 RAG 搬到後端，以 job/outbox/idempotency key 進一步做到可靠重試。

### Q14：assistant endpoint 是否代表使用者不能偽造 AI 回答？

目前 request 不能直接注入 `role`，角色由 dedicated endpoint 固定；owner isolation 也能防止寫入別人的對話。不過只靠使用者 JWT 不能證明內容真的由模型產生，因此這是個人歷史資料的 MVP integrity 取捨。若回答要作為稽核證據，應由後端執行 RAG，或加入服務對服務驗證與不可由瀏覽器取得的憑證。

## 19. 可使用的 STAR 故事

### 故事一：OpenAI／LangChain 執行失敗分層診斷

- Situation：介面可以顯示，但建立 embeddings 時失敗。
- Task：判斷是 UI、程式、網路、key 或帳戶問題。
- Action：分離驗證 UI、文件流程、直接 API authentication 與 embeddings 呼叫；處理 legacy tokenizer 下載問題後，繼續追蹤到帳戶 billing 狀態。
- Result：避免反覆更換 key 或盲目改程式，定位真正失敗層級。

### 故事二：建立資料擁有權防線

- Situation：加入多使用者 Conversation／Message 後，UUID 本身不能保證隱私。
- Task：保證使用者只能操作自己的資料。
- Action：owner ID 只取自 JWT current user；repository 同時以 resource ID 與 owner ID 查詢；跨使用者和不存在資源同樣回覆；加入兩使用者隔離測試。
- Result：授權規則由 UI、API、repository 到 tests 都一致。

### 故事三：安全 migration

- Situation：新增 conversations／messages 會改動遠端 PostgreSQL schema。
- Task：確保 migration 正確、可逆且未誤用 production。
- Action：在 Neon development 產生並人工閱讀 migration，驗證 upgrade、downgrade、upgrade、current、check、foreign keys、indexes、check constraint 與 cascade。
- Result：schema 與 ORM metadata 一致，且有可重現的 migration 紀錄。

### 故事四：修正 Streamlit 捲動卡頓

- Situation：使用者在對話頁面底部往上捲動時，畫面會卡頓或被拉回。
- Task：找出是瀏覽器、CSS 還是 Streamlit execution model 導致。
- Action：追蹤回答完成後的控制流程，發現 `st.chat_input` 已觸發一次 run，程式卻又呼叫 `st.rerun()`；移除第二次整頁 rerun，改用 `st.empty()` placeholder 更新問題數和 token metric。
- Result：31 項前端測試通過，瀏覽器實測由底部向上捲動後位置保持穩定，也減少不必要的整頁重算。

### 故事五：讓 RAG 對話跨工作階段保存

- Situation：原本問答只存在 Streamlit session，使用者無法管理或重新載入歷史。
- Task：串接既有 Conversation／Message API，同時維持多帳號 owner isolation 並處理兩段式寫入失敗。
- Action：建立可測試的 API/state adapters；先存 user message 再呼叫 RAG；用 dedicated endpoint 保存 assistant；加入 retry payload；以兩個真實帳號驗證重載、切換、改名、刪除與隔離。
- Result：真實 RAG 問答可在重新登入後還原，第二帳號看到空清單；前端 47、後端 108 項自動測試通過。

## 20. Streamlit 身分驗證 UI 階段紀錄

- 階段名稱：Streamlit 身分驗證 UI
- 完成日期：2026-08-12
- 功能與使用者價值：使用者可在 Streamlit 註冊、登入、登出；未登入時無法使用 RAG 功能。
- 新增技術：Python `requests`、Bearer JWT client、Streamlit forms／tabs／session state、HTTP adapter、mocked HTTP tests。
- 資料流：表單 → `frontend_api.py` → FastAPI `/auth/*` → JWT → `/auth/me` → `frontend_auth.py` → `st.session_state`。
- 安全設計：前端不保存密碼或 hash；只白名單保存安全 user fields；錯誤訊息不顯示後端內部內容；登出同時清除 authentication 與使用者 RAG workspace。
- 測試與驗證數字：31 項前端測試、105 項後端測試；`pip check` 無破損依賴；瀏覽器完成 register、login、JWT `/auth/me`、功能解鎖、向上捲動穩定與 logout E2E。
- 遇到的問題與解法：回答完成後重複 `st.rerun()` 讓底部 chat input 重設捲動；改用 placeholder 原地更新 sidebar metrics。
- 設計取捨：JWT 僅保存在 Streamlit session；整頁重新整理後重新登入，暫不使用 localStorage、自製 cookie 或 refresh token。
- 面試可說重點：前後端 HTTP 契約、安全 token state、錯誤分層、mocked HTTP boundary、Streamlit rerun model 與真實瀏覽器驗收。
- 仍未完成：RAG 對話持久化串接、Render backend、部署後 E2E、Redis rate limiting。

## 21. Streamlit RAG 個人對話持久化階段紀錄

- 階段名稱：Streamlit RAG 個人對話持久化
- 完成日期：2026-08-12
- 功能與使用者價值：登入者可建立、切換、改名、刪除自己的對話；RAG 問題與回答可在重新登入後還原。
- 新增技術：Conversation／Message HTTP client、JSON list／204 response contracts、UUID path validation、Streamlit conversation state helper、assistant retry state。
- 資料流：sidebar selection → owner-filtered Conversation API → Message history → `st.session_state` → user message → RAG → assistant message。
- 安全設計：所有呼叫沿用 Bearer JWT；401 清除帳號與 workspace；404 不區分不存在與別人資源；登出清除 conversation IDs、history 與 pending answer；request 不能注入 role。
- 測試與驗證數字：47 項前端測試、108 項後端測試；真實瀏覽器與 Neon development 完成 RAG 問答、重載、切換、改名、刪除及兩帳號隔離，兩個臨時帳號已刪除。
- 遇到的問題與解法：持久化歷史在 main body 載入後，sidebar metric 初值仍是 0；沿用 `st.empty()` placeholder 在載入後更新，而不新增整頁 rerun。
- 設計取捨：Message table 不保存 token usage；重載後 token metric 歸零。assistant endpoint 適合個人歷史 MVP，但不是模型來源的不可否認證明。
- 面試可說重點：跨層資料流、owner isolation、partial failure、retry、response contract validation、真實雙帳號 E2E。
- 仍未完成：Render backend、Streamlit Cloud 部署後 E2E、Redis rate limiting、observability 與 refresh token。

## 22. Render 後端部署階段紀錄

- 階段名稱：Render 後端部署。
- 完成日期：2026-08-12。
- 功能與使用者價值：FastAPI 透過公開 HTTPS 提供 Auth 與個人 Conversation API，前端不再依賴本機 Uvicorn。
- 新增技術：Render Blueprint、Infrastructure as Code、Singapore region、health check、main checks-passed auto deploy、Neon pooled／direct URLs、production smoke test。
- 資料流：GitHub protected main → required CI → Render build → Alembic `upgrade head` → Uvicorn → Neon production。
- 安全設計：資料庫 URL 與 JWT secret 只存在 Render environment；JWT secret 使用平台秘密管理；測試 token 暴露後立即輪替 secret、重新部署並刪除臨時帳號。
- 測試與驗證數字：公開 `/health`、`/docs` 為 200；register 201、login／`/auth/me` 200；Conversation／Message CRUD 成功；刪除後 resource 404、帳號登入 401。
- 遇到的問題與解法：Neon URL 若保留 `postgresql://`，SQLAlchemy 會嘗試載入 `psycopg2`；改用 `postgresql+psycopg://` 明確選擇已安裝的 psycopg 3 driver。Blueprint region 另以小型 PR 固定為 `singapore`。
- 設計取捨：Free instance 會休眠並有 cold start；migration 與 Uvicorn 串在同一啟動命令適合單 instance 展示版，多 instance 應使用獨立 release job。
- 面試可說重點：IaC、CI 與 CD 的邊界、driver dialect、pooled／direct connection 分工、migration ordering、secret rotation、production smoke test 與測試資料清理。
- 仍未完成：Streamlit Cloud 正式前後端 E2E、Redis rate limiting、observability、refresh token 與備份策略。

### Render 部署常見追問

**為什麼 `DATABASE_URL` 與 `DIRECT_DATABASE_URL` 分開？**

一般 API 查詢使用 Neon pooled connection，較適合短連線與併發；Alembic migration 需要穩定的 session-level connection，因此使用 direct URL。兩者用途不同，但都不提交 Git。

**為什麼啟動順序是 migration 再 Uvicorn？**

新程式可能依賴新欄位或資料表。先成功升級 schema，再讓服務接受流量，可避免程式版本與 schema 不一致。`&&` 也確保 migration 失敗時不會啟動一個結構不相容的服務。

**如何處理部署後機密暴露？**

不只刪除畫面或測試資料，而是把憑證視為已失陷：輪替 JWT secret、觸發重新部署使舊 token 失效、刪除臨時帳號／對話，最後重新驗證 health 與拒絕登入。

## 23. Production 端到端驗收與冷啟動處理

- 階段名稱：Streamlit Cloud production E2E。
- 完成日期：2026-08-13。
- 功能與使用者價值：公開 Streamlit 可註冊、登入、完成 RAG 問答，登出再登入後仍能還原個人歷史。
- 新增技術：production E2E、Render cold-start handling、跨帳號 isolation smoke test、部署 secrets 分層。
- 資料流：Streamlit Cloud → Render HTTPS API → JWT／owner authorization → Neon PostgreSQL → OpenAI → Conversation／Message persistence。
- 安全設計：兩個臨時帳號驗證 owner isolation；錯誤登入回 401；Render 保存 database／JWT secrets，Streamlit Cloud 保存 backend URL／OpenAI secret，Git 不保存值。
- 測試與驗證數字：前端 48 passed、後端 108 passed；正式站通過 register、login、`/auth/me`、RAG、重新登入還原、跨帳號空清單與 invalid-login 401。
- 遇到的問題與解法：Render Free 閒置會休眠，第一次 request 可能超過原本 10 秒；將 backend timeout 調整為 75 秒並補 timeout tests，仍避免無限等待。
- 設計取捨：75 秒適合免費展示環境；有 SLA 的正式系統應改用常駐 instance、監控 latency 並為 migration 使用獨立 release job。
- 面試可說重點：health check 不等於 E2E、冷啟動與商業邏輯錯誤的分層診斷、BOLA／IDOR 隔離驗收、production test data cleanup。
- 仍未完成：Redis rate limiting、observability、refresh token 與備份演練。

### Production E2E 驗收範圍

```text
公開 Streamlit
  → 註冊／登入／Bearer JWT
  → 建立 Conversation
  → 保存 user message
  → 文件檢索與 LLM 回答
  → 保存 assistant message
  → 登出／重新登入並還原歷史
```

`/health` 只證明程序能接受 request，不能證明 migration、JWT、資料庫、owner-scoped CRUD、OpenAI 與持久化都正確，因此部署完成必須再走完整流程。跨帳號測試建立 A、B 兩個臨時帳號；A 建立 conversation 後，B 的 list 必須仍為空，用來捕捉 BOLA／IDOR 類授權錯誤。

面試追問：為什麼不把 timeout 設成無限？

> 有限 timeout 是故障邊界；無限等待會讓 Streamlit request 和使用者介面永久卡住。75 秒涵蓋 Render Free 的冷啟動，但真的 production 會用常駐 instance 與 latency monitoring 解決根因。

面試追問：如何管理跨平台 secrets？

> Render 持有 Neon URL 與 JWT secret；Streamlit Cloud 持有 OpenAI key 與公開 backend base URL。程式只讀環境變數，Git 只放欄位範例；提交前掃描 staged diff，若 token 曾曝光則直接輪替而不是只刪畫面。

## 24. Redis 限流與基礎可觀測性

- 階段名稱：Redis rate limiting 與 basic observability。
- 完成日期：2026-08-13。
- 功能與使用者價值：登入、註冊與對話 API 在所有後端 instance 間共用限流計數；每個 response 都有 request ID，部署日誌可依 JSON 欄位追查延遲與錯誤。
- 新增技術：Render Key Value、redis-py asyncio、Redis Lua atomic script、fixed-window rate limit、ASGI middleware、structured JSON logging、liveness／readiness probes。
- 資料流：HTTP request → request ID → Redis atomic `INCR + EXPIRE` → 允許或 429 → FastAPI route → response headers → JSON access log。
- 安全設計：Redis key 只保存 SHA-256 截斷識別值，不保存原始 IP／JWT；日誌不含 query、body、Authorization 或連線字串；Key Value 禁止外部網路，只用 Render Singapore private network。
- 測試與驗證數字：後端 115 passed；另以 production smoke test 驗證 health、ready、request ID、rate-limit headers 與超限 429。
- 遇到的問題與解法：本機 shell 一度使用系統 Python 而缺少 backend dependencies；改以 `.venv-backend` 的明確直譯器執行，避免「終端提示已啟用」與實際 subprocess 環境不一致。
- 設計取捨：固定視窗簡單、低成本且 Lua 操作原子化，但視窗邊界可能允許短暫 burst；更嚴格需求可改 sliding window 或 token bucket。Redis 暫時失效採 fail-open 維持 API 可用性，同時寫 error log 且 `/ready` 回報失敗。
- 面試可說重點：distributed state、atomicity、429 semantics、privacy-preserving identifiers、liveness vs readiness、fail-open vs fail-closed、structured logging 與 correlation ID。
- 仍未完成：公開 README／架構圖／Demo 素材整理、refresh token、metrics／distributed tracing 與備份演練。

### 為什麼用 Lua，而不是分開呼叫 `INCR` 與 `EXPIRE`？

兩次網路呼叫之間若程序中斷，key 可能沒有 TTL，形成永久計數。Lua script 在 Redis 內以單一原子操作執行，並在第一次計數時設定 expiration，讓多 worker 併發時仍維持一致。

### 為什麼 `/health` 與 `/ready` 分開？

`/health` 是 liveness，只回答程序是否能處理 HTTP，Render 可用它避免依賴短暫抖動造成重啟循環；`/ready` 驗證 PostgreSQL 與 Redis，適合部署驗收與告警。依賴失效時程序仍活著，但不代表完整服務已準備好。

### 429 response 要帶哪些資訊？

API 回 `429 Too Many Requests`、不暴露內部 key 的固定錯誤訊息、`Retry-After`，並提供 `X-RateLimit-Limit` 與 `X-RateLimit-Remaining`。客戶端因此知道何時安全重試，監控也能辨識容量限制而不是誤判成 5xx。

## 25. 每階段更新模板

階段完成後，在本文件更新：

```text
階段名稱：
完成日期：
功能與使用者價值：
新增技術：
資料流：
安全設計：
測試與驗證數字：
遇到的問題與解法：
設計取捨：
面試可說重點：
仍未完成：
```

同時更新第 3 節狀態表、相關技術章節、常見面試問題與 STAR 故事。
