# 文件智能客服專案狀態

最後更新：2026-08-05

## 1. 本檔案的用途

這份檔案記錄專案目前的真實進度、重要技術決策與下一步工作，避免長期開發後失去方向。

每個大階段開始前，Codex 必須：

1. 先讀取本檔案。
2. 用 Git 狀態、目前分支及測試結果重新核對現況。
3. 先向使用者說明「已完成、目前目標、本階段範圍、完成標準」。
4. 每次只教一個可驗證的小步驟，並詳細說明目的、指令內容與預期結果。
5. 一個段落或大階段完成後，由 Codex 更新本檔案；使用者不需要手動維護。

本檔案不能取代 Git、測試或雲端服務紀錄。若內容與即時檢查不一致，以實際結果為準並修正本檔案。

禁止把 API Key、資料庫連線字串、密碼或 JWT Secret 寫入本檔案。

## 2. 專案目標與架構

目標是建立可用於專題展示與履歷的校園圖書館文件型 RAG 智能客服。

```text
使用者
  ↓
Streamlit Cloud（雙語介面與 RAG）
  ├─ LangChain + FAISS + OpenAI API
  └─ FastAPI API（Render）
       └─ Neon PostgreSQL

GitHub
  ├─ GitHub Actions：前後端 CI
  ├─ Streamlit Cloud：前端自動部署
  └─ Render：後端自動部署（後續階段）
```

第一版不使用 Docker；Redis 限流等功能等主要流程完成後再加入。

## 3. 目前快照

- 目前分支：`feature/add-database-foundation`
- 分支起點：合併 FastAPI PR #4 的 `main` commit `6cd9f4a`
- 本階段已推送的基礎 commit：`a46e3a8`
- 目前大階段：Neon PostgreSQL 與 Alembic 資料庫基礎
- 使用中的 Neon 分支：`development`
- 目前 Alembic revision：`6e51fbe701b3 (head)`
- `users` migration 已完成升級、降級及重新升級驗證

目前尚未提交的預期檔案：

```text
PROJECT_STATE.md
backend/config.py
backend/tests/test_config.py
backend/alembic.ini
backend/alembic/
backend/models.py
backend/tests/test_models.py
```

下一個小步驟：暫存本階段檔案，檢查 staged diff 與機密掃描結果，確認無誤後建立資料庫基礎的第二個 commit。

## 4. 已完成里程碑

### 4.1 Streamlit 與 RAG

- 範例圖書館 FAQ，以及 PDF／CSV 上傳問答。
- 繁體中文／英文介面。
- LangChain、FAISS 與 OpenAI 文件檢索問答。
- 最近三組問答脈絡、清除對話、Markdown 匯出與使用統計。
- 自然招呼與友善的無答案提示。
- 公開展示限制：每個工作階段 10 題、檔案 5 MB、最多 100 個區塊。
- 模型使用 `gpt-4o-mini` 與 `text-embedding-3-small`。
- Streamlit Cloud 公開網站已可使用。
- Streamlit 已連接 GitHub 自動部署；完整前端 CD 驗收留待下一次真正的前端功能變更。

### 4.2 Git、GitHub 與安全

- GitHub 公開 Repository 已建立。
- `.env`、虛擬環境、個人文件與舊資料不進 Git。
- `main` 必須透過 Pull Request 更新。
- 禁止刪除 `main` 與 force push。
- 已實際驗證直接推送 `main` 會被拒絕。
- Required checks 包含 `CI / test` 與 `CI / backend-test`。

### 4.3 CI

- 前端 job `test`：安裝根目錄依賴、檢查 `app.py`、執行 `tests/`。
- 後端 job `backend-test`：安裝後端依賴、檢查後端語法、執行 `backend/tests/`。
- 前端本機測試：5 passed。
- 後端本機測試：13 passed。
- FastAPI TestClient 目前有一個不阻斷測試的棄用警告。
- PR 與合併後的 `main` CI 均已成功驗證。

### 4.4 FastAPI 基礎

- `backend/main.py` 已建立 FastAPI application。
- `GET /health` 回傳 HTTP 200 與 `{"status": "ok"}`。
- Swagger `/docs` 與 Uvicorn 本機啟動已驗證。
- 前端 `.venv` 與後端 `.venv-backend` 分離，避免 Pydantic 1／2 相依衝突。
- FastAPI 基礎已透過 PR #4 合併並完成分支清理。

### 4.5 資料庫基礎（目前階段已完成部分）

#### 套件與設定

- 已固定並安裝：
  - `SQLAlchemy==2.0.51`
  - `psycopg[binary]==3.3.4`
  - `alembic==1.18.5`
  - `pydantic-settings==2.14.2`
- `pip check` 已通過。
- `backend/config.py` 集中讀取資料庫環境變數。
- `backend/database.py` 提供 SQLAlchemy Base、engine、session factory 與 FastAPI session dependency。
- Engine 採延遲建立並使用 `pool_pre_ping=True`。
- Session dependency 會在使用完畢後關閉連線。
- 設定與資料庫行為測試已建立，不連正式 Neon。

#### Neon

- Neon 專案：`campus-library-rag-chatbot`
- 方案：Free
- 區域：AWS Asia Pacific 1（Singapore）
- PostgreSQL：18
- 保留預設 `production`，並建立永久 `development` 分支。
- 開發資料庫：`neondb`
- 開發角色：`neondb_owner`
- Pooled URL 已放入本機 `.env` 的 `DATABASE_URL`。
- Direct URL 已放入本機 `.env` 的 `DIRECT_DATABASE_URL`。
- 兩個 URL 都改為 `postgresql+psycopg://`。
- 已確認 pooled URL 包含 `-pooler`，direct URL 不包含 `-pooler`。
- `.env` 已由 `.gitignore` 排除。
- Pooled 與 direct 連線均已實際連線成功。

#### Alembic 與 users 資料表

- Alembic 已初始化於 `backend/alembic/`。
- `backend/alembic.ini` 的 `sqlalchemy.url` 保持空白，不保存機密。
- `backend/alembic/env.py` 從設定模組取得 direct connection，並載入 `Base.metadata`。
- `User` ORM model 已建立，包含：
  - UUID `id`
  - 唯一且有索引的 `email`
  - `password_hash`
  - 含時區的 `created_at`
- Migration：`6e51fbe701b3_create_users_table.py`
- 已先用 `--sql` 預覽 migration SQL。
- 已成功執行 `upgrade head` 建立 `users` 與 `alembic_version`。
- 已確認欄位型別、NOT NULL 條件與唯一 Email 索引正確。
- 初始 `users` 筆數為 0。
- 已成功執行 `downgrade base`，確認 `users` 被移除。
- 已重新執行 `upgrade head`，目前回到 `6e51fbe701b3 (head)`。

## 5. 目前階段剩餘工作

### 本機驗證結果

- [x] Alembic schema check 通過，ORM 與資料庫結構沒有差異。
- [x] Pooled connection 可看到 `users` 與 `alembic_version`。
- [x] 全部後端測試通過：13 passed；另有一個不阻斷的 TestClient 棄用警告。
- [x] `pip check` 通過，沒有損壞的套件相依關係。
- [x] 前端語法檢查通過，前端測試為 5 passed。
- [x] `git diff --check` 沒有空白錯誤；只有 Windows LF／CRLF 行尾提醒。
- [x] 已檢查完整變更檔案與 migration 內容。
- [x] 機密掃描沒有結果，`.env` 與 Neon 連線字串未出現在待提交檔案中。
- [x] 本狀態檔已統整本機驗證結果。

### 尚待完成

- [ ] 暫存檔案，檢查 staged diff，建立 commit 並 push 後建立 Pull Request。
- [ ] 等待 `CI / test` 與 `CI / backend-test` 通過後合併。
- [ ] 同步本機 `main`、重新測試、清理功能分支，並更新本狀態檔的階段完成紀錄。

## 6. 本階段完成標準

只有下列條件全部成立，資料庫基礎階段才算完成：

- 本機與 GitHub Actions 的前後端測試全部通過。
- 真實資料庫連線字串及其他機密沒有進入 Git。
- FastAPI `/health` 仍可正常使用。
- Neon `development` 資料庫可透過 pooled 與 direct URL 連線。
- Alembic 可以 upgrade、downgrade，再 upgrade 回 head。
- ORM metadata 與 Neon schema 完全同步。
- `users` 資料表由 migration 建立，而非手動建立。
- Pull Request 合併後完成本機同步與分支清理。

## 7. 目前架構決策

- 正式資料庫使用 Neon PostgreSQL，不使用 MySQL 或 SQLite 作為正式資料庫。
- 第一版採同步 SQLAlchemy Session 與 Psycopg，先降低學習複雜度。
- `DATABASE_URL` 使用 Neon pooled connection，供 FastAPI 日常查詢。
- `DIRECT_DATABASE_URL` 使用 Neon direct connection，供 Alembic migration。
- 上傳的 PDF／CSV 不永久保存。
- 第一版不做 refresh token、信箱驗證、忘記密碼、第三方登入或 Docker。
- 管理員後台不是目前優先項目；先完成安全的 API 與資料模型。
- 不在 CI 連正式 Neon；單元測試使用 mock 或獨立測試環境。

## 8. 後續大階段

資料庫基礎合併後，依序進行：

1. Email 正規化與 Argon2 密碼雜湊。
2. `POST /auth/register`。
3. `POST /auth/login`。
4. JWT access token 與 `GET /auth/me`。
5. 使用者擁有者驗證與授權測試。
6. `conversations`、`messages` 模型與 migrations。
7. 個人對話 CRUD API。
8. Streamlit 登入、註冊與歷史對話介面。
9. Streamlit 與 FastAPI 串接；JWT 僅放在 `st.session_state`。
10. FastAPI 部署 Render，完成後端 CD。
11. 用真正的登入介面變更驗收 Streamlit Cloud 前端 CD。
12. 主要功能完成後再加入 Redis 限流。
13. 整理 README、架構圖、Demo、API 文件與履歷描述。

## 9. 每階段固定檢查流程

### 開始前

- 讀取本檔案。
- 檢查目前分支與 Git 狀態。
- 確認使用正確的虛擬環境。
- 重新執行上一階段的關鍵測試。

### 修改後

- 語法檢查。
- 單元測試。
- `pip check`。
- `git diff --check`。

### 暫存與提交前

- 查看變更檔案清單。
- 閱讀完整 diff。
- 執行機密掃描。
- 更新本檔案。

### 合併後

- 確認 `main` CI 成功。
- 同步本機 `main`。
- 再次測試。
- 清理本機與遠端功能分支。
- 更新本檔案，記錄完成結果與下一個階段。
