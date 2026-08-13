# v1.0 作品集驗收紀錄

驗收日期：2026-08-13（Asia/Taipei）

## 公開入口

- Streamlit：<https://campus-library-rag-chatbot.streamlit.app/>
- FastAPI：<https://campus-library-chatbot-api.onrender.com>
- Swagger：<https://campus-library-chatbot-api.onrender.com/docs>
- 外部監控：[Production Monitor](https://github.com/34497225/campus-library-rag-chatbot/actions/workflows/production-monitor.yml)

## Production E2E 結果

以下流程已透過公開 Streamlit UI 實際執行，而不只是 mock 或 API 單元測試：

1. 一次性帳號註冊成功。
2. Email／密碼登入成功，Streamlit 取得並驗證 Render JWT session。
3. 載入虛構圖書館 FAQ，詢問「圖書館平日的開放時間是什麼？」。
4. OpenAI RAG 回答包含「週一至週五 08:30 至 21:00」，符合測試資料。
5. 登出再登入後，Conversation 標題與 user／assistant 訊息仍可還原，證明資料已持久化至 Neon，而非只存在 Streamlit session。
6. 透過 UI 刪除測試對話，再依精確 Email 刪除一次性 production 帳號。
7. cleanup 後確認 test user 為 0、orphan conversations 為 0、orphan messages 為 0。

驗收文件不保存測試密碼、Bearer JWT、OpenAI key、Neon／Redis URL 或任何 production secret。

## 自動化品質門檻

- 前端、RAG evaluation 與 monitor：58 tests。
- 後端：119 tests。
- 合計：177 tests。
- 兩套 Python 環境均執行 `pip check`。
- PR 必須通過 GitHub required CI 後才能合併至 `main`。
- 外部 monitor 每 15 分鐘檢查 `/health`、`/ready`、`/metrics`，失敗時建立或沿用 GitHub Issue alert。

## 品質與限制

- 16 個雙語 RAG cases：Top-3 retrieval 100%，grounded／fallback answer 94%。
- Render Free 閒置後可能冷啟動，不能宣稱 latency SLA。
- FAISS 是 Streamlit session-local，適合作品展示但不是多租戶持久向量平台。
- v1.0 不包含 Email 驗證、忘記密碼、refresh token、完整 tracing 或付費 pager。
