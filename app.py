"""Bilingual document-based customer-service demo built with Streamlit and RAG."""

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

import openai
import streamlit as st
from dotenv import load_dotenv
from langchain.callbacks import get_openai_callback
from langchain.chains.question_answering import load_qa_chain
from langchain.chat_models import ChatOpenAI
from langchain.document_loaders import CSVLoader, PyPDFLoader
from langchain.embeddings.base import Embeddings
from langchain.prompts import PromptTemplate
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import FAISS

from frontend_api import (
    BackendAPIError,
    create_conversation,
    create_message,
    delete_conversation,
    fetch_current_user,
    list_conversations,
    list_messages,
    login_user,
    register_user,
    rename_conversation,
)
from frontend_auth import (
    clear_authentication,
    initialize_auth_state,
    is_authenticated,
    store_authentication,
)
from frontend_conversations import (
    activate_conversation,
    build_conversation_title,
    clear_conversation_state,
    initialize_conversation_state,
    normalize_conversation,
    normalize_message,
    replace_conversations,
)


BASE_DIR = Path(__file__).resolve().parent
DEMO_LIBRARY_PATH = BASE_DIR / "knowledge_base" / "demo_library_faq.csv"

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024
MAX_DOCUMENT_CHUNKS = 100
MAX_QUESTIONS_PER_SESSION = 10

load_dotenv()

# Streamlit 前端不直接連資料庫，而是透過 FastAPI URL 使用後端功能。
# 本機預設使用 http://localhost:8000；
# 部署後可透過環境變數切換到 Render URL。
BACKEND_API_URL = os.getenv(
    "BACKEND_API_URL",
    "http://localhost:8000",
).strip()

openai.api_key = os.getenv("OPENAI_API_KEY")

TEXT = {
    "zh": {
        "title": "校園圖書館智能客服",
        "subtitle": "以 RAG 技術根據文件內容提供問答；範例資料為虛構示範，非真實校規。",
        "about": "系統說明",
        "about_body": "使用 Streamlit、LangChain、FAISS 與 OpenAI 建立的文件問答系統。",
        "mode": "知識來源",
        "demo_mode": "載入範例圖書館 FAQ",
        "upload_mode": "上傳自己的 PDF／CSV",
        "missing_key": "尚未設定 OPENAI_API_KEY。請依照 .env.example 建立 .env 檔案。",
        "loading": "正在讀取文件並建立索引……",
        "loaded": "已載入：{name}",
        "upload": "上傳知識文件",
        "need_upload": "請先上傳一個 PDF 或 CSV 檔案。",
        "question": "請輸入你想詢問的問題",
        "asking": "正在查詢文件……",
        "examples": "範例問題",
        "clear": "清除對話",
        "download": "下載對話紀錄（Markdown）",
        "stats": "本次使用統計",
        "question_count": "問答次數",
        "token_count": "累計 Token",
        "history_note": "系統會參考最近 3 組問答作為對話脈絡。",
        "processing_error": "文件處理失敗：{error}",
        "answer_error": "回答問題時發生錯誤：{error}",
        "language": "Language / 語言",
        "demo_notice": "目前使用虛構的圖書館 FAQ 範例資料，適合專題展示。",
        "no_text": "文件中沒有可供搜尋的文字內容。",
        "file_too_large": "檔案大小不可超過 {limit_mb} MB。",
        "too_many_chunks": "文件切分後超過 {limit} 個區塊，請改用較小的文件。",
        "question_limit": "本次工作階段已達 {limit} 題上限，請清除對話後再繼續。",
        "billing": "OpenAI API 帳戶目前未啟用或沒有可用額度，請檢查 Billing 與 Usage Limits。",
        "invalid_key": "OPENAI_API_KEY 無效，請檢查 .env 中的新金鑰。",
        "rate_limit": "OpenAI API 已達速率或額度限制，請稍後重試並檢查 Usage Limits。",
        "connection": "無法連線至 OpenAI API，請檢查網路、防火牆或代理伺服器設定。",
        "account": "帳號",
        "login_tab": "登入",
        "register_tab": "註冊",
        "email": "Email",
        "password": "密碼",
        "confirm_password": "確認密碼",
        "login": "登入",
        "register": "建立帳號",
        "logout": "登出",
        "logged_in_as": "已登入：{email}",
        "auth_required": "請先登入，才能使用文件問答功能。",
        "login_success": "登入成功。",
        "register_success": "註冊成功，請切換到登入頁籤。",
        "password_mismatch": "兩次輸入的密碼不一致。",
        "session_expired": "登入狀態已失效，請重新登入。",
        "backend_not_configured": "尚未設定後端 API 網址。",
        "backend_unavailable": "目前無法連線到後端服務，請稍後重試。",
        "invalid_credentials": "Email 或密碼錯誤。",
        "email_exists": "這個 Email 已經註冊。",
        "invalid_auth_input": "輸入資料格式不正確，請檢查 Email 與密碼。",
        "invalid_auth_response": "後端回傳的登入資料格式不正確。",
        "auth_request_failed": "帳號請求失敗（HTTP {status}）。",
        "conversation_history": "個人對話紀錄",
        "conversation_select": "切換對話",
        "new_conversation": "新增對話",
        "new_conversation_title": "新對話標題",
        "create_conversation": "建立",
        "rename_conversation": "重新命名",
        "delete_conversation": "刪除目前對話",
        "no_conversations": "尚無已儲存的對話；送出第一個問題時會自動建立。",
        "conversation_api_failed": "對話服務失敗（HTTP {status}）。",
        "conversation_unavailable": "目前無法連線到對話服務，請稍後重試。",
        "conversation_not_found": "這筆對話不存在或無法存取，清單已重新整理。",
        "message_save_failed": "問題尚未儲存，因此本次不會呼叫 RAG。請重試。",
        "answer_save_failed": "回答已顯示，但尚未儲存。可按下方按鈕重試。",
        "retry_answer_save": "重試儲存回答",
        "answer_save_success": "回答已補存完成。",
        "unknown": "{type}: {message}",
    },
    "en": {
        "title": "Campus Library AI Assistant",
        "subtitle": "A RAG-based document Q&A assistant. The demo library data is fictional and not an official policy.",
        "about": "About this project",
        "about_body": "A document Q&A system built with Streamlit, LangChain, FAISS, and OpenAI.",
        "mode": "Knowledge source",
        "demo_mode": "Load demo library FAQ",
        "upload_mode": "Upload your own PDF / CSV",
        "missing_key": "OPENAI_API_KEY is not configured. Create .env from .env.example first.",
        "loading": "Reading the document and building an index…",
        "loaded": "Loaded: {name}",
        "upload": "Upload a knowledge document",
        "need_upload": "Upload one PDF or CSV file first.",
        "question": "Ask a question about the document",
        "asking": "Searching the document…",
        "examples": "Example questions",
        "clear": "Clear conversation",
        "download": "Download conversation (Markdown)",
        "stats": "Session statistics",
        "question_count": "Questions",
        "token_count": "Total tokens",
        "history_note": "The assistant uses the latest three Q&A pairs as conversation context.",
        "processing_error": "Document processing failed: {error}",
        "answer_error": "Answering failed: {error}",
        "language": "Language / 語言",
        "demo_notice": "This mode uses fictional library FAQ data for a project demonstration.",
        "no_text": "The document does not contain searchable text.",
        "file_too_large": "The file size cannot exceed {limit_mb} MB.",
        "too_many_chunks": "The document exceeds the limit of {limit} chunks. Please use a smaller file.",
        "question_limit": "This session has reached the {limit}-question limit. Clear the conversation to continue.",
        "billing": "The OpenAI API account is inactive or has no available credit. Check Billing and Usage Limits.",
        "invalid_key": "OPENAI_API_KEY is invalid. Check the new key in .env.",
        "rate_limit": "The OpenAI API rate or usage limit was reached. Try again later and check Usage Limits.",
        "connection": "Unable to connect to the OpenAI API. Check the network, firewall, or proxy settings.",
        "account": "Account",
        "login_tab": "Log in",
        "register_tab": "Register",
        "email": "Email",
        "password": "Password",
        "confirm_password": "Confirm password",
        "login": "Log in",
        "register": "Create account",
        "logout": "Log out",
        "logged_in_as": "Signed in as: {email}",
        "auth_required": "Log in to use the document Q&A features.",
        "login_success": "Login successful.",
        "register_success": "Registration successful. Switch to the login tab.",
        "password_mismatch": "The passwords do not match.",
        "session_expired": "Your login session is no longer valid. Log in again.",
        "backend_not_configured": "The backend API URL is not configured.",
        "backend_unavailable": "The backend service is currently unavailable. Try again later.",
        "invalid_credentials": "The email or password is incorrect.",
        "email_exists": "This email is already registered.",
        "invalid_auth_input": "The input is invalid. Check the email and password.",
        "invalid_auth_response": "The backend returned invalid login data.",
        "auth_request_failed": "The account request failed (HTTP {status}).",
        "conversation_history": "Personal conversations",
        "conversation_select": "Switch conversation",
        "new_conversation": "New conversation",
        "new_conversation_title": "New conversation title",
        "create_conversation": "Create",
        "rename_conversation": "Rename",
        "delete_conversation": "Delete current conversation",
        "no_conversations": "No saved conversations yet. The first question will create one automatically.",
        "conversation_api_failed": "The conversation service failed (HTTP {status}).",
        "conversation_unavailable": "The conversation service is unavailable. Try again later.",
        "conversation_not_found": "This conversation is missing or inaccessible. The list was refreshed.",
        "message_save_failed": "The question was not saved, so RAG was not called. Try again.",
        "answer_save_failed": "The answer is visible but not saved yet. Use the retry button below.",
        "retry_answer_save": "Retry saving answer",
        "answer_save_success": "The answer was saved successfully.",
        "unknown": "{type}: {message}",
    },
}

PROMPT_TEMPLATE = """You are a friendly document-based customer-service assistant.
The required response language is {response_language}. You MUST write the whole
answer in that language, even when the document context contains other languages.
The latest input below is a substantive question, not a greeting. Answer that
question directly and do not replace the answer with a generic welcome message.

For every other question, answer only from the supplied document context. If the
context is insufficient, do not invent an answer and use a polite fallback in
the user's language: explain that the available information does not cover the
question, then invite the user to rephrase the question or ask about the
library services in the document. Never reply with only "I don't know".

Recent conversation (may be empty):
{history}

Document context:
---------
{context}
---------
Latest question: {question}
"""


def t(language: str, key: str, **values: str) -> str:
    return TEXT[language][key].format(**values)


def validate_file_size(file_size_bytes: int) -> None:
    if file_size_bytes > MAX_FILE_SIZE_BYTES:
        raise ValueError("file_too_large")


def validate_chunk_count(chunk_count: int) -> None:
    if chunk_count > MAX_DOCUMENT_CHUNKS:
        raise ValueError("too_many_chunks")


def has_reached_question_limit(question_count: int) -> bool:
    return question_count >= MAX_QUESTIONS_PER_SESSION


class DirectOpenAIEmbeddings(Embeddings):
    """Small adapter that avoids the legacy LangChain tokenizer download."""

    def __init__(self, model: str):
        self.model = model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        response = openai.Embedding.create(
            model=self.model,
            input=[text.replace("\n", " ") for text in texts],
            request_timeout=30,
        )
        ordered_data = sorted(response["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in ordered_data]

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]


def friendly_error(error: Exception, language: str) -> str:
    message = str(error).lower()
    if "billing" in message or "account is not active" in message:
        return t(language, "billing")
    if "incorrect api key" in message or "invalid api key" in message:
        return t(language, "invalid_key")
    if "rate limit" in message:
        return t(language, "rate_limit")
    if "timeout" in message or "connection" in message:
        return t(language, "connection")
    return t(language, "unknown", type=type(error).__name__, message=str(error))


def label_documents(documents: List[Document], source_name: str) -> List[Document]:
    for document in documents:
        document.metadata["source_name"] = source_name
    return documents


def load_csv(path: Path, source_name: str) -> List[Document]:
    documents = CSVLoader(
        file_path=str(path), encoding="utf-8", csv_args={"delimiter": ","}
    ).load()
    return label_documents(documents, source_name)


def load_uploaded_file(uploaded_file) -> List[Document]:
    suffix = Path(uploaded_file.name).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(uploaded_file.getvalue())
        temp_path = Path(temp_file.name)

    try:
        if suffix == ".pdf":
            documents = PyPDFLoader(str(temp_path)).load()
        elif suffix == ".csv":
            documents = load_csv(temp_path, uploaded_file.name)
        else:
            raise ValueError("Only PDF and CSV files are supported.")
        return label_documents(documents, uploaded_file.name)
    finally:
        temp_path.unlink(missing_ok=True)


def build_vector_store(documents: List[Document]) -> FAISS:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800, chunk_overlap=120, length_function=len
    )
    chunks = splitter.split_documents(documents)
    if not chunks or not any(chunk.page_content.strip() for chunk in chunks):
        raise ValueError("no_text")
    validate_chunk_count(len(chunks))

    model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    return FAISS.from_documents(chunks, DirectOpenAIEmbeddings(model=model))


def format_history(messages: List[Dict[str, object]]) -> str:
    recent = messages[-6:]
    lines = []
    for message in recent:
        role = "User" if message["role"] == "user" else "Assistant"
        lines.append(f"{role}: {message['content']}")
    return "\n".join(lines) or "(No previous conversation.)"


def response_language_for(question: str) -> str:
    """Choose a stable response language from the user's latest question.

    The demo supports Traditional Chinese and English. Passing an explicit
    language into the prompt prevents bilingual source rows from influencing
    the model's output language.
    """

    has_cjk = any("\u4e00" <= char <= "\u9fff" for char in question)
    return "Traditional Chinese" if has_cjk else "English"


def greeting_response(question: str) -> str | None:
    """Return a deterministic greeting only for an exact greeting phrase."""

    normalized = question.strip().casefold().rstrip("!！.。?？")
    if normalized in {"hi", "hello", "hey"}:
        return "Hello! Ask me anything about the available library information."
    if normalized in {"你好", "您好", "哈囉", "嗨"}:
        return "您好！歡迎詢問文件中提供的圖書館資訊。"
    return None


def answer_question(
    vector_store: FAISS, question: str, messages: List[Dict[str, object]]
) -> Tuple[str, List[Document], int]:
    greeting = greeting_response(question)
    if greeting is not None:
        return greeting, [], 0

    sources = vector_store.similarity_search(question, k=3)
    prompt = PromptTemplate(
        template=PROMPT_TEMPLATE,
        input_variables=["context", "question", "history", "response_language"],
    )
    model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    chain = load_qa_chain(
        # Temperature zero makes factual customer-service answers and the
        # version-controlled evaluation more repeatable.
        ChatOpenAI(model_name=model, temperature=0, max_tokens=800),
        chain_type="stuff",
        prompt=prompt,
    )
    with get_openai_callback() as callback:
        answer = chain.run(
            input_documents=sources,
            question=question,
            history=format_history(messages),
            response_language=response_language_for(question),
        )
    return answer, sources, callback.total_tokens


def conversation_markdown(messages: List[Dict[str, object]], source_name: str) -> str:
    lines = ["# Document Customer-Service Conversation", "", f"Knowledge source: {source_name}", ""]
    for message in messages:
        heading = "User" if message["role"] == "user" else "Assistant"
        lines.extend([f"## {heading}", str(message["content"]), ""])
    return "\n".join(lines)


def initialize_state() -> None:
    # 登入狀態和 RAG 狀態分別由各自的 helper 初始化。
    # 函式只會補上不存在的 key，不會在 Streamlit rerun 時清除登入。
    initialize_auth_state(st.session_state)
    initialize_conversation_state(st.session_state)

    defaults = {
        "messages": [],
        "question_count": 0,
        "total_tokens": 0,
        "active_source_id": None,
        "active_source_name": None,
        "vector_store": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def validate_authentication_session() -> bool:
    """Validate stored login data against FastAPI's /auth/me endpoint."""

    if not is_authenticated(st.session_state):
        return False

    access_token = st.session_state.access_token

    try:
        # 不只相信前端 session 中已有 current_user，
        # 而是向後端確認 token 仍有效、使用者仍存在。
        current_user = fetch_current_user(
            base_url=BACKEND_API_URL,
            access_token=access_token,
        )
    except BackendAPIError as error:
        if error.status_code == 401:
            # 401 代表 token 過期、無效或使用者已不存在。
            # 清除失效憑證，讓畫面回到登入狀態。
            clear_authentication(st.session_state)
            return False

        # 後端斷線或 5xx 不代表 JWT 一定無效，
        # 因此保留 session，交給 UI 顯示服務暫時不可用。
        raise

    # 重新保存後端回傳的安全使用者資料，
    # 同時沿用 helper 的欄位白名單。
    store_authentication(
        state=st.session_state,
        access_token=access_token,
        user=current_user,
    )

    return True


def authentication_error_message(
    error: BackendAPIError,
    language: str,
) -> str:
    """Convert backend authentication failures into safe UI messages."""

    if error.status_code is None:
        return t(language, "backend_unavailable")

    if error.status_code == 401:
        return t(language, "invalid_credentials")

    if error.status_code == 409:
        return t(language, "email_exists")

    if error.status_code == 422:
        return t(language, "invalid_auth_input")

    return t(
        language,
        "auth_request_failed",
        status=str(error.status_code),
    )


def reset_conversation() -> None:
    st.session_state.messages = []
    st.session_state.question_count = 0
    st.session_state.total_tokens = 0


def reset_user_workspace() -> None:
    """Clear user-specific RAG data when the user logs out."""

    clear_conversation_state(st.session_state)

    # 同一個瀏覽器工作階段可能換另一個帳號登入。
    # 登出時清除文件索引與來源，避免下一位使用者沿用前一位的資料。
    st.session_state.active_source_id = None
    st.session_state.active_source_name = None
    st.session_state.vector_store = None


def render_authentication(language: str) -> bool:
    """Render account controls and return whether the user is authenticated."""

    st.subheader(t(language, "account"))

    if not BACKEND_API_URL:
        st.error(t(language, "backend_not_configured"))
        return False

    if is_authenticated(st.session_state):
        try:
            session_is_valid = validate_authentication_session()
        except BackendAPIError as error:
            # 網路或後端服務失敗時保留 token，
            # 但暫停需要後端身分驗證的功能。
            st.error(authentication_error_message(error, language))
            return False

        if session_is_valid:
            current_user = st.session_state.current_user

            st.success(
                t(
                    language,
                    "logged_in_as",
                    email=current_user["email"],
                )
            )

            if st.button(t(language, "logout")):
                clear_authentication(st.session_state)
                reset_user_workspace()
                st.rerun()

            return True

        # validate_authentication_session 已在 401 時清除失效 token。
        st.warning(t(language, "session_expired"))

    login_tab, register_tab = st.tabs(
        [
            t(language, "login_tab"),
            t(language, "register_tab"),
        ]
    )

    with login_tab:
        with st.form("login_form"):
            login_email = st.text_input(
                t(language, "email"),
                key="login_email",
            )
            login_password = st.text_input(
                t(language, "password"),
                type="password",
                key="login_password",
            )
            login_submitted = st.form_submit_button(
                t(language, "login")
            )

        if login_submitted:
            try:
                # 第一步取得 JWT。
                token_response = login_user(
                    base_url=BACKEND_API_URL,
                    email=login_email,
                    password=login_password,
                )

                # 第二步立即使用 JWT 呼叫 /auth/me。
                # 只有 token 真正可用時，才保存登入狀態。
                current_user = fetch_current_user(
                    base_url=BACKEND_API_URL,
                    access_token=token_response["access_token"],
                )

                store_authentication(
                    state=st.session_state,
                    access_token=token_response["access_token"],
                    user=current_user,
                )
            except BackendAPIError as error:
                st.error(
                    authentication_error_message(error, language)
                )
            except ValueError:
                st.error(t(language, "invalid_auth_response"))
            else:
                st.success(t(language, "login_success"))
                st.rerun()

    with register_tab:
        with st.form("register_form"):
            register_email = st.text_input(
                t(language, "email"),
                key="register_email",
            )
            register_password = st.text_input(
                t(language, "password"),
                type="password",
                key="register_password",
            )
            confirm_password = st.text_input(
                t(language, "confirm_password"),
                type="password",
                key="register_confirm_password",
            )
            register_submitted = st.form_submit_button(
                t(language, "register")
            )

        if register_submitted:
            if register_password != confirm_password:
                # 確認密碼只屬於前端防呆，
                # 不需要也不應送到 FastAPI。
                st.error(t(language, "password_mismatch"))
            else:
                try:
                    register_user(
                        base_url=BACKEND_API_URL,
                        email=register_email,
                        password=register_password,
                    )
                except BackendAPIError as error:
                    st.error(
                        authentication_error_message(error, language)
                    )
                else:
                    # 註冊不自動登入，讓登入與註冊責任保持清楚。
                    st.success(t(language, "register_success"))

    return False


def set_source(source_id: str, source_name: str, documents: List[Document]) -> None:
    if st.session_state.active_source_id != source_id:
        st.session_state.vector_store = build_vector_store(documents)
        st.session_state.active_source_id = source_id
        st.session_state.active_source_name = source_name


def conversation_error_message(
    error: BackendAPIError,
    language: str,
) -> str:
    """Convert persistence failures into safe bilingual UI text."""

    if error.status_code is None:
        return t(language, "conversation_unavailable")
    if error.status_code == 404:
        return t(language, "conversation_not_found")

    return t(
        language,
        "conversation_api_failed",
        status=str(error.status_code),
    )


def handle_conversation_error(
    error: BackendAPIError,
    language: str,
) -> None:
    """Apply shared 401 privacy cleanup and display a safe error."""

    if error.status_code == 401:
        clear_authentication(st.session_state)
        reset_user_workspace()
        st.warning(t(language, "session_expired"))
        st.rerun()

    st.error(conversation_error_message(error, language))


def refresh_conversation_list(language: str) -> bool:
    """Refresh the owner-filtered conversation list from FastAPI."""

    try:
        conversations = list_conversations(
            base_url=BACKEND_API_URL,
            access_token=st.session_state.access_token,
        )
        replace_conversations(st.session_state, conversations)
    except (BackendAPIError, ValueError) as error:
        if isinstance(error, BackendAPIError):
            handle_conversation_error(error, language)
        else:
            st.error(t(language, "invalid_auth_response"))
        return False

    return True


def load_active_conversation(language: str) -> bool:
    """Load messages only when the selected conversation changes."""

    conversation_id = st.session_state.active_conversation_id
    if conversation_id is None:
        reset_conversation()
        return True

    if st.session_state.loaded_conversation_id == conversation_id:
        return True

    try:
        messages = list_messages(
            base_url=BACKEND_API_URL,
            access_token=st.session_state.access_token,
            conversation_id=conversation_id,
        )
        activate_conversation(
            st.session_state,
            conversation_id,
            messages,
        )
    except BackendAPIError as error:
        handle_conversation_error(error, language)
        if error.status_code == 404:
            refresh_conversation_list(language)
        return False
    except ValueError:
        st.error(t(language, "invalid_auth_response"))
        return False

    return True


def render_conversation_controls(language: str) -> None:
    """Render owner-scoped create, switch, rename, and delete controls."""

    st.subheader(t(language, "conversation_history"))
    conversations = st.session_state.conversations

    if conversations:
        conversation_ids = [item["id"] for item in conversations]
        titles = {item["id"]: item["title"] for item in conversations}
        current_id = st.session_state.active_conversation_id
        current_index = (
            conversation_ids.index(current_id)
            if current_id in conversation_ids
            else 0
        )
        selected_id = st.selectbox(
            t(language, "conversation_select"),
            conversation_ids,
            index=current_index,
            format_func=lambda item_id: titles[item_id],
        )
        if selected_id != current_id:
            st.session_state.active_conversation_id = selected_id
            st.session_state.loaded_conversation_id = None
            st.session_state.pending_assistant_message = None
            st.rerun()

        with st.form("rename_conversation_form"):
            renamed_title = st.text_input(
                t(language, "rename_conversation"),
                value=titles[selected_id],
            )
            rename_submitted = st.form_submit_button(
                t(language, "rename_conversation")
            )
        if rename_submitted:
            try:
                rename_conversation(
                    base_url=BACKEND_API_URL,
                    access_token=st.session_state.access_token,
                    conversation_id=selected_id,
                    title=renamed_title,
                )
            except BackendAPIError as error:
                handle_conversation_error(error, language)
            else:
                refresh_conversation_list(language)
                st.rerun()

        if st.button(t(language, "delete_conversation")):
            try:
                delete_conversation(
                    base_url=BACKEND_API_URL,
                    access_token=st.session_state.access_token,
                    conversation_id=selected_id,
                )
            except BackendAPIError as error:
                handle_conversation_error(error, language)
            else:
                st.session_state.active_conversation_id = None
                st.session_state.loaded_conversation_id = None
                st.session_state.pending_assistant_message = None
                refresh_conversation_list(language)
                st.rerun()
    else:
        st.caption(t(language, "no_conversations"))

    with st.form("new_conversation_form", clear_on_submit=True):
        new_title = st.text_input(t(language, "new_conversation_title"))
        create_submitted = st.form_submit_button(
            t(language, "create_conversation")
        )
    if create_submitted:
        try:
            created = create_conversation(
                base_url=BACKEND_API_URL,
                access_token=st.session_state.access_token,
                title=new_title,
            )
        except BackendAPIError as error:
            handle_conversation_error(error, language)
        else:
            try:
                safe_created = normalize_conversation(created)
            except ValueError:
                st.error(t(language, "invalid_auth_response"))
                return
            refresh_conversation_list(language)
            st.session_state.active_conversation_id = safe_created["id"]
            st.session_state.loaded_conversation_id = None
            st.rerun()


def ensure_active_conversation(question: str) -> str:
    """Return the active ID, auto-creating a titled conversation if needed."""

    active_id = st.session_state.active_conversation_id
    if isinstance(active_id, str):
        return active_id

    created = create_conversation(
        base_url=BACKEND_API_URL,
        access_token=st.session_state.access_token,
        title=build_conversation_title(question),
    )
    safe_created = normalize_conversation(created)
    replace_conversations(
        st.session_state,
        [safe_created, *st.session_state.conversations],
    )
    st.session_state.active_conversation_id = safe_created["id"]
    st.session_state.loaded_conversation_id = safe_created["id"]
    return safe_created["id"]


def retry_pending_assistant_message(language: str) -> None:
    """Offer recovery when RAG succeeded but its answer was not persisted."""

    pending = st.session_state.pending_assistant_message
    if not isinstance(pending, dict):
        return
    if pending.get("conversation_id") != st.session_state.active_conversation_id:
        return

    st.warning(t(language, "answer_save_failed"))
    if st.button(t(language, "retry_answer_save")):
        try:
            create_message(
                base_url=BACKEND_API_URL,
                access_token=st.session_state.access_token,
                conversation_id=pending["conversation_id"],
                content=pending["content"],
                assistant=True,
            )
        except BackendAPIError as error:
            handle_conversation_error(error, language)
        else:
            st.session_state.pending_assistant_message = None
            st.success(t(language, "answer_save_success"))


def main() -> None:
    st.set_page_config(page_title="Campus Library AI Assistant", page_icon="📚")
    initialize_state()

    with st.sidebar:
        language_label = st.selectbox("Language / 語言", ["繁體中文", "English"])
        language = "zh" if language_label == "繁體中文" else "en"
        st.header(t(language, "about"))
        st.markdown(t(language, "about_body"))
        st.divider()

        authenticated = render_authentication(language)

        if authenticated:
            st.divider()
            if refresh_conversation_list(language):
                render_conversation_controls(language)
            st.divider()
            st.subheader(t(language, "stats"))
            # 用 placeholder 更新既有元件，不需要為了刷新統計而整頁重跑。
            question_count_metric = st.empty()
            token_count_metric = st.empty()
            question_count_metric.metric(
                t(language, "question_count"),
                st.session_state.question_count,
            )
            token_count_metric.metric(
                t(language, "token_count"),
                st.session_state.total_tokens,
            )
            st.caption(t(language, "history_note"))
    st.title(t(language, "title"))
    st.caption(t(language, "subtitle"))

    # 未登入時仍顯示系統介紹與帳號表單，
    # 但不載入文件、不建立 embeddings，也不顯示聊天功能。
    if not authenticated:
        st.info(t(language, "auth_required"))
        return

    # 對話清單在 sidebar 載入後，再依目前選取的 ID 取得訊息。
    # 這能讓 rerun 保留選取項目，又不必每次互動都重抓同一份 history。
    if not load_active_conversation(language):
        return

    # load_active_conversation 可能剛把持久化 history 載入 session，
    # 因此再更新一次既有 placeholder，讓 sidebar 立即顯示正確題數。
    question_count_metric.metric(
        t(language, "question_count"),
        st.session_state.question_count,
    )
    token_count_metric.metric(
        t(language, "token_count"),
        st.session_state.total_tokens,
    )

    if not os.getenv("OPENAI_API_KEY"):
        st.error(t(language, "missing_key"))
        st.stop()

    mode_options = [t(language, "demo_mode"), t(language, "upload_mode")]
    selected_mode = st.radio(t(language, "mode"), mode_options, horizontal=True)

    try:
        if selected_mode == t(language, "demo_mode"):
            st.info(t(language, "demo_notice"))
            with st.spinner(t(language, "loading")):
                set_source("demo-library", "demo_library_faq.csv", load_csv(DEMO_LIBRARY_PATH, "demo_library_faq.csv"))
        else:
            uploaded_file = st.file_uploader(t(language, "upload"), type=["pdf", "csv"])
            if uploaded_file is None:
                st.info(t(language, "need_upload"))
                return
            validate_file_size(uploaded_file.size)
            file_digest = hashlib.sha256(uploaded_file.getvalue()).hexdigest()[:12]
            source_id = f"upload:{uploaded_file.name}:{file_digest}"
            with st.spinner(t(language, "loading")):
                set_source(source_id, uploaded_file.name, load_uploaded_file(uploaded_file))
        st.success(t(language, "loaded", name=st.session_state.active_source_name))
    except Exception as error:
        if str(error) == "no_text":
            error_text = t(language, "no_text")
        elif str(error) == "file_too_large":
            error_text = t(
                language,
                "file_too_large",
                limit_mb=MAX_FILE_SIZE_BYTES // 1024 // 1024,
            )
        elif str(error) == "too_many_chunks":
            error_text = t(
                language,
                "too_many_chunks",
                limit=MAX_DOCUMENT_CHUNKS,
            )
        else:
            error_text = friendly_error(error, language)
        st.error(t(language, "processing_error", error=error_text))
        return

    examples = {
        "zh": ["圖書館平日的開放時間是什麼？", "如何借閱館藏？", "可以續借已借閱的書嗎？"],
        "en": ["What are the weekday opening hours?", "How do I borrow an item?", "Can I renew a borrowed book?"],
    }
    with st.expander(t(language, "examples"), expanded=True):
        for example in examples[language]:
            st.code(example, language=None)

    if st.session_state.messages:
        st.download_button(
            t(language, "download"),
            data=conversation_markdown(st.session_state.messages, st.session_state.active_source_name),
            file_name="library_customer_service_conversation.md",
            mime="text/markdown",
        )

    retry_pending_assistant_message(language)

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question_limit_reached = has_reached_question_limit(
        st.session_state.question_count
    )
    if question_limit_reached:
        st.warning(
            t(
                language,
                "question_limit",
                limit=MAX_QUESTIONS_PER_SESSION,
            )
        )
    question = st.chat_input(
        t(language, "question"),
        disabled=question_limit_reached,
    )
    if question:
        try:
            # 先確保有一筆 owned Conversation，再保存 user message。
            # 如果這一步失敗，就不呼叫 OpenAI，避免產生無法追溯的回答。
            conversation_id = ensure_active_conversation(question)
            saved_user_message = create_message(
                base_url=BACKEND_API_URL,
                access_token=st.session_state.access_token,
                conversation_id=conversation_id,
                content=question,
            )
            safe_user_message = normalize_message(saved_user_message)
        except BackendAPIError as error:
            handle_conversation_error(error, language)
            st.error(t(language, "message_save_failed"))
            return
        except ValueError:
            st.error(t(language, "invalid_auth_response"))
            return

        st.session_state.messages.append(
            {
                "id": safe_user_message["id"],
                "role": "user",
                "content": safe_user_message["content"],
                "created_at": safe_user_message["created_at"],
            }
        )
        with st.chat_message("user"):
            st.markdown(question)

        try:
            with st.chat_message("assistant"):
                with st.spinner(t(language, "asking")):
                    answer, _sources, used_tokens = answer_question(
                        st.session_state.vector_store, question, st.session_state.messages[:-1]
                    )
                st.markdown(answer)
            st.session_state.messages.append(
                {"role": "assistant", "content": answer}
            )

            try:
                # assistant role 不是由 request JSON 提供，而是由後端的
                # dedicated endpoint 固定，避免一般 message payload 注入角色。
                saved_answer = create_message(
                    base_url=BACKEND_API_URL,
                    access_token=st.session_state.access_token,
                    conversation_id=conversation_id,
                    content=answer,
                    assistant=True,
                )
                safe_answer = normalize_message(saved_answer)
                st.session_state.messages[-1] = {
                    "id": safe_answer["id"],
                    "role": "assistant",
                    "content": safe_answer["content"],
                    "created_at": safe_answer["created_at"],
                }
                st.session_state.pending_assistant_message = None
            except BackendAPIError as error:
                if error.status_code == 401:
                    handle_conversation_error(error, language)
                # RAG 已成功且使用者已看到答案時，不把畫面上的回答刪掉。
                # 保存 retry payload，讓暫時性網路錯誤可在下次 rerun 補寫。
                st.session_state.pending_assistant_message = {
                    "conversation_id": conversation_id,
                    "content": answer,
                }
                st.warning(t(language, "answer_save_failed"))
            except ValueError:
                # RAG 已成功且使用者已看到答案時，不把畫面上的回答刪掉。
                # 保存 retry payload，讓暫時性網路錯誤可在下次 rerun 補寫。
                st.session_state.pending_assistant_message = {
                    "conversation_id": conversation_id,
                    "content": answer,
                }
                st.warning(t(language, "answer_save_failed"))

            st.session_state.question_count += 1
            st.session_state.total_tokens += used_tokens
            # 直接更新側邊欄中的原有統計元件，避免用 st.rerun() 重新建立
            # 整個頁面並干擾使用者正在閱讀的捲動位置。
            question_count_metric.metric(
                t(language, "question_count"),
                st.session_state.question_count,
            )
            token_count_metric.metric(
                t(language, "token_count"),
                st.session_state.total_tokens,
            )
            # chat_input 送出時已經啟動這次腳本執行。回答完成後若再次
            # st.rerun()，固定在頁面底部的輸入框會重新錨定捲動位置，
            # 讓使用者往上閱讀對話時感覺被拉回或卡頓。
        except Exception as error:
            st.error(t(language, "answer_error", error=friendly_error(error, language)))


if __name__ == "__main__":
    main()
