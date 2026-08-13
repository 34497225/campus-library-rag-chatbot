# 五分鐘作品 Demo 腳本

目標：用一條完整使用者旅程展示 RAG、後端、安全、資料持久化與工程品質，而不是逐頁朗讀功能清單。

## Demo 前準備

- 確認 Streamlit Cloud 與 Render `/ready` 可開啟。
- 準備一次性測試 Email；不要使用真實密碼。
- 使用內建虛構 FAQ，避免在面試現場上傳敏感文件。
- 預先開啟 GitHub Actions、Swagger 與 repository README 分頁。
- Render Free instance 可能冷啟動，正式展示前先呼叫一次 `/health`。

## 0:00–0:40｜問題與價值

說法：

> 一般聊天模型可能憑空回答，而且不同使用者的對話不能混在一起。這個專案讓模型先檢索指定文件，再回答並標示來源；使用者登入後，個人對話會安全保存並可重新載入。

畫面：展示登入頁與雙語切換。

## 0:40–1:30｜登入與安全邊界

1. 以一次性 Email 註冊並登入。
2. 指出前端只保存 server-side session JWT。
3. 說明密碼在後端轉成 Argon2id hash，API response 不會輸出 hash。
4. 開啟 Swagger 的 `/auth/me`，說明 Bearer JWT 與 `sub` UUID。

面試重點：認證回答「你是誰」；owner-filtered query 負責「你能看哪些資料」。

## 1:30–2:40｜RAG 問答

1. 載入範例圖書館 FAQ。
2. 詢問：「圖書館平日幾點開放？」
3. 追問：「那週末呢？」
4. 展示來源片段與最近對話脈絡。

說明資料流：文件切分 → embedding → FAISS Top-k → 問題、片段與有限歷史 → Chat Model → 回答。

## 2:40–3:35｜個人對話持久化

1. 建立第二個對話並改名。
2. 在兩個對話間切換。
3. 登出並重新登入，展示歷史仍存在。
4. 刪除一個對話。

說明：Conversation／Message 保存於 PostgreSQL；每次 repository query 都帶 authenticated owner ID，其他帳號即使知道 UUID 也只能得到一致 404。

## 3:35–4:20｜可靠性與可觀測性

1. 開啟 `/ready`，展示 PostgreSQL 與 Redis 都正常才回 ready。
2. 指出 response 的 `X-Request-ID`。
3. 在 Render Logs 展示同一 request ID 的 JSON event。
4. 說明 auth 每分鐘 10 次、一般 API 每分鐘 60 次，Redis Lua 保證計數與 TTL 原子完成。

## 4:20–5:00｜工程流程與收尾

1. 展示 GitHub Actions 的前端與後端 required checks。
2. 指出 `main` 只能經 PR 合併，Render 只在 checks 通過後部署。
3. 報告驗證數字：前端 48 tests、後端 116 tests。
4. 主動說明限制：RAG 尚在 Streamlit process、FAISS 是 session-local、Render Free 會休眠。

收尾說法：

> 這個作品不只串接模型，也把身分驗證、資料授權、migration、測試、限流、部署和 production 驗收串成完整交付流程。下一步會把 RAG 移到後端 worker，加入持久化向量庫與完整 tracing。

## 常見追問

### 為什麼不用模型直接回答？

RAG 能把回答限制在指定文件脈絡，並提供可檢查的來源；模型仍可能犯錯，因此介面保留「以正式規定為準」提示。

### 為什麼使用 FAISS 而不是 pgvector？

FAISS 適合第一版 session-local 文件展示，部署簡單、搜尋快。若要跨 session 保存大量文件、多人共用知識庫或做 metadata filtering，會改用 pgvector 或託管向量資料庫。

### JWT 和 session 有什麼差別？

JWT 是 API 身分憑證；Streamlit session state 是目前 UI session 的 server-side 狀態容器。這一版不把 JWT 放在 URL 或 localStorage，瀏覽器整頁重載可能需要重新登入。

### Redis 壞掉怎麼辦？

一般 request 採 fail-open，避免 Redis 問題讓整個 API 中斷；`/ready` 會回 503，讓監控與平台知道依賴異常。高風險 API 則可改成 fail-closed。

### 如何證明不是只在本機能跑？

展示 Streamlit Cloud、Render HTTPS、Neon production 資料持久化、Redis 429、Render JSON logs，以及每次 PR／main 的 GitHub Actions 紀錄。
