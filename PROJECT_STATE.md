# 文件智能客服專案狀態

最後更新：2026-08-04

## 使用方式

這份檔案是專案的持續狀態紀錄。每個大階段開始前：

1. 先讀取本檔案。
2. 用 `git status -sb`、`git branch --show-current` 與相關測試重新核對現況。
3. 先向使用者整理「已完成、目前目標、本階段範圍、完成標準」。
4. 每次只教一個可驗證的小步驟，並解釋目的、指令與預期結果。
5. 每個可驗證段落完成後，由 Codex 自動更新本檔案；使用者不需要手動維護。
6. 每個大階段開始前，由 Codex 自動讀取本檔案，再以 Git 狀態與測試結果核對。

本檔案不能取代 Git、測試結果或雲端服務紀錄；若內容與實際狀態不同，以即時檢查結果為準並修正本檔案。

## 專案目標

建立可用於專題展示與履歷的校園圖書館文件型 RAG 智能客服：

- Streamlit 提供中英文介面與文件問答。
- LangChain、FAISS 與 OpenAI API 負責 RAG。
- FastAPI 提供帳號、JWT 驗證與個人對話 API。
- Neon PostgreSQL 永久保存帳號與對話。
- Streamlit Cloud 部署前端。
- Render 部署 FastAPI。
- GitHub Actions 執行前後端 CI。
- Redis 限流留在主要功能完成後再做。

## 已完成

### Streamlit 與 RAG

- 範例圖書館 FAQ 與 PDF／CSV 上傳。
- 繁體中文／英文介面。
- FAISS 檢索與 OpenAI 回答。
- 最近三組問答脈絡、清除對話、Markdown 匯出與使用統計。
- 友善招呼與無答案提示。
- 每個工作階段 10 題、檔案 5 MB、100 個區塊等公開展示限制。
- 使用 `gpt-4o-mini` 與 `text-embedding-3-small`。
- Streamlit Cloud 公開網站已可使用。
- GitHub 自動部署能力已連接，但端到端 CD 驗收留待下一次真正的前端功能變更。

### Git、GitHub 與安全

- GitHub 公開 Repository 已建立。
- `.env`、虛擬環境、個人文件與舊資料不進 Git。
- `main` 必須透過 Pull Request 更新。
- 禁止刪除 `main` 與 force push。
- Ruleset 必須通過 `CI / test` 與 `CI / backend-test`。
- 已實際驗證直接推送 `main` 會被拒絕。

### CI

- 前端 job `test`：安裝根目錄依賴、檢查 `app.py`、執行 `tests/`。
- 後端 job `backend-test`：安裝後端依賴、檢查後端語法、執行 `backend/tests/`。
- 本機前端測試目前為 5 passed。
- 本機後端測試目前為 8 passed，另有 FastAPI TestClient 的非阻斷棄用警告。
- 後端測試包含 Health 1 個、Config 3 個與 Database Mock 4 個。
- PR 與合併後的 `main` CI 都已通過。

### FastAPI 基礎

- `backend/main.py` 已建立 FastAPI application。
- `GET /health` 回傳 HTTP 200 與 `{\"status\": \"ok\"}`。
- Swagger `/docs` 與 Uvicorn 本機啟動已驗證。
- 前端 `.venv` 與後端 `.venv-backend` 分離，避免 Pydantic 1／2 衝突。
- FastAPI 基礎 PR #4 已合併，完成分支清理。

## 目前狀態

- 預期目前分支：`feature/add-database-foundation`。
- 分支起點：合併 PR #4 的 `main` commit `6cd9f4a`。
- 目前大階段：資料庫基礎。
- 已查詢並 dry-run 驗證以下版本可由 pip 解析：
  - `SQLAlchemy==2.0.51`
  - `psycopg[binary]==3.3.4`
  - `alembic==1.18.5`
  - `pydantic-settings==2.14.2`
- 上述四個固定版本已寫入 `backend/requirements.txt` 並安裝至 `.venv-backend`。
- `pip check` 已通過，實際匯入版本與鎖定版本一致。
- `backend/config.py` 已建立，集中管理 `DATABASE_URL` 與 `DIRECT_DATABASE_URL`。
- 設定模組允許應用程式在未設定資料庫網址時匯入；實際需要連線時才產生清楚錯誤。
- `backend/database.py` 已建立 SQLAlchemy Base、延遲建立的 Engine、Session Factory 與 FastAPI Session Dependency。
- Engine 啟用 `pool_pre_ping=True`，Session 使用完畢後會在 `finally` 中關閉。
- Config 測試 3 個與 Database Mock 測試 4 個均已通過，全程沒有連接真正的 Neon。
- 本機後端測試總計為 8 passed。
- 下一個小步驟是建立 Neon PostgreSQL 專案與開發資料庫，目前仍未使用真實資料庫連線。

## 目前架構決策

- 正式資料庫使用 Neon PostgreSQL，不使用 MySQL 或 SQLite 作為正式資料庫。
- 第一版採同步 SQLAlchemy Session 與 Psycopg，先降低學習複雜度。
- `DATABASE_URL` 使用 Neon pooled connection，供 FastAPI 日常查詢。
- `DIRECT_DATABASE_URL` 使用 Neon direct connection，供 Alembic migration。
- 上傳的 PDF／CSV 不永久保存。
- 第一版不做 refresh token、信箱驗證、忘記密碼、第三方登入或 Docker。
- 管理員後台不是目前優先項目；先完成安全的 API 與資料模型。

## 下一個大階段：資料庫基礎

### 目標

讓 FastAPI 能以集中設定、安全且可測試的方式連接 PostgreSQL，但先不建立完整登入功能。

### 預定步驟

1. 把四個已選版本加入 `backend/requirements.txt`，安裝並執行 `pip check`。（已完成）
2. 建立集中管理環境變數的設定模組。（已完成）
3. 驗證缺少 `DATABASE_URL` 時會產生清楚錯誤，而且匯入 `/health` 不會被無關設定阻斷。（已完成）
4. 建立 SQLAlchemy Base、engine、session factory 與 FastAPI session dependency。（已完成）
5. 為設定與 session 行為建立不連正式 Neon 的 Mock 測試。（已完成）
6. 建立 Neon 專案與開發用 PostgreSQL 資料庫。（下一步）
7. 將真實連線字串只放在本機 `.env`，並再次執行機密掃描。
8. 使用真實開發資料庫測試連線，但不連接或修改正式資料。
9. 初始化 Alembic，分離 pooled 與 direct connection。
10. 建立 `users` 模型與第一個 migration。
11. 在開發資料庫套用 migration，檢查資料表後再走 PR／CI／合併流程。

### 完成標準

- 本機和 CI 測試全部通過。
- 正式機密沒有進入 Git。
- FastAPI `/health` 仍正常。
- Neon 開發資料庫可連線。
- Alembic 可以升級與回退 schema。
- `users` 資料表由 migration 建立，而不是手動建立。

## 後續階段

1. 使用者模型、Email 正規化與 Argon2 密碼雜湊。
2. `POST /auth/register`、`POST /auth/login`、`GET /auth/me`。
3. JWT access token 與擁有者驗證。
4. conversations 與 messages 模型、migration、CRUD API。
5. Streamlit 登入／註冊／歷史對話介面。
6. Streamlit 與 FastAPI 串接，JWT 僅放 `st.session_state`。
7. FastAPI 部署 Render，完成後端 CD。
8. 以真正的登入介面變更驗收 Streamlit Cloud 前端 CD。
9. Redis 登入防暴力破解與使用者提問限流。
10. README、架構圖、Demo、API 文件與履歷描述整理。

## 每階段固定檢查清單

- 開始前：分支、Git 狀態、依賴環境與上一階段測試。
- 修改前：說明目的、影響範圍與可回復方式。
- 修改後：語法、單元測試、`pip check`、`git diff --check`。
- 暫存前：檔案清單、完整 diff 與機密掃描。
- 合併前：本機測試、PR CI、Required checks。
- 合併後：`main` CI、同步本機、再次測試、清理分支、更新本檔案。
