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


BASE_DIR = Path(__file__).resolve().parent
DEMO_LIBRARY_PATH = BASE_DIR / "knowledge_base" / "demo_library_faq.csv"

load_dotenv()
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
        "billing": "OpenAI API 帳戶目前未啟用或沒有可用額度，請檢查 Billing 與 Usage Limits。",
        "invalid_key": "OPENAI_API_KEY 無效，請檢查 .env 中的新金鑰。",
        "rate_limit": "OpenAI API 已達速率或額度限制，請稍後重試並檢查 Usage Limits。",
        "connection": "無法連線至 OpenAI API，請檢查網路、防火牆或代理伺服器設定。",
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
        "billing": "The OpenAI API account is inactive or has no available credit. Check Billing and Usage Limits.",
        "invalid_key": "OPENAI_API_KEY is invalid. Check the new key in .env.",
        "rate_limit": "The OpenAI API rate or usage limit was reached. Try again later and check Usage Limits.",
        "connection": "Unable to connect to the OpenAI API. Check the network, firewall, or proxy settings.",
        "unknown": "{type}: {message}",
    },
}

PROMPT_TEMPLATE = """You are a friendly document-based customer-service assistant.
Reply in the same language as the user's latest question.

If the latest question is only a simple greeting (for example: hi, hello, 你好,
哈囉), greet the user warmly and invite them to ask about the available library
information. Do not say that you do not know for a greeting.

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

    model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    return FAISS.from_documents(chunks, DirectOpenAIEmbeddings(model=model))


def format_history(messages: List[Dict[str, object]]) -> str:
    recent = messages[-6:]
    lines = []
    for message in recent:
        role = "User" if message["role"] == "user" else "Assistant"
        lines.append(f"{role}: {message['content']}")
    return "\n".join(lines) or "(No previous conversation.)"


def answer_question(
    vector_store: FAISS, question: str, messages: List[Dict[str, object]]
) -> Tuple[str, List[Document], int]:
    sources = vector_store.similarity_search(question, k=3)
    prompt = PromptTemplate(
        template=PROMPT_TEMPLATE,
        input_variables=["context", "question", "history"],
    )
    model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    chain = load_qa_chain(
        ChatOpenAI(model_name=model, temperature=0.2, max_tokens=800),
        chain_type="stuff",
        prompt=prompt,
    )
    with get_openai_callback() as callback:
        answer = chain.run(
            input_documents=sources,
            question=question,
            history=format_history(messages),
        )
    return answer, sources, callback.total_tokens


def conversation_markdown(messages: List[Dict[str, object]], source_name: str) -> str:
    lines = ["# Document Customer-Service Conversation", "", f"Knowledge source: {source_name}", ""]
    for message in messages:
        heading = "User" if message["role"] == "user" else "Assistant"
        lines.extend([f"## {heading}", str(message["content"]), ""])
    return "\n".join(lines)


def initialize_state() -> None:
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


def reset_conversation() -> None:
    st.session_state.messages = []
    st.session_state.question_count = 0
    st.session_state.total_tokens = 0


def set_source(source_id: str, source_name: str, documents: List[Document]) -> None:
    if st.session_state.active_source_id != source_id:
        st.session_state.vector_store = build_vector_store(documents)
        st.session_state.active_source_id = source_id
        st.session_state.active_source_name = source_name
        reset_conversation()


def main() -> None:
    st.set_page_config(page_title="Campus Library AI Assistant", page_icon="📚")
    initialize_state()

    with st.sidebar:
        language_label = st.selectbox("Language / 語言", ["繁體中文", "English"])
        language = "zh" if language_label == "繁體中文" else "en"
        st.header(t(language, "about"))
        st.markdown(t(language, "about_body"))
        st.divider()
        st.subheader(t(language, "stats"))
        st.metric(t(language, "question_count"), st.session_state.question_count)
        st.metric(t(language, "token_count"), st.session_state.total_tokens)
        st.caption(t(language, "history_note"))

    st.title(t(language, "title"))
    st.caption(t(language, "subtitle"))

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
            file_digest = hashlib.sha256(uploaded_file.getvalue()).hexdigest()[:12]
            source_id = f"upload:{uploaded_file.name}:{file_digest}"
            with st.spinner(t(language, "loading")):
                set_source(source_id, uploaded_file.name, load_uploaded_file(uploaded_file))
        st.success(t(language, "loaded", name=st.session_state.active_source_name))
    except Exception as error:
        error_text = t(language, "no_text") if str(error) == "no_text" else friendly_error(error, language)
        st.error(t(language, "processing_error", error=error_text))
        return

    examples = {
        "zh": ["圖書館平日的開放時間是什麼？", "如何借閱館藏？", "可以續借已借閱的書嗎？"],
        "en": ["What are the weekday opening hours?", "How do I borrow an item?", "Can I renew a borrowed book?"],
    }
    with st.expander(t(language, "examples"), expanded=True):
        for example in examples[language]:
            st.code(example, language=None)

    columns = st.columns([1, 2])
    if columns[0].button(t(language, "clear")):
        reset_conversation()
        st.rerun()
    if st.session_state.messages:
        columns[1].download_button(
            t(language, "download"),
            data=conversation_markdown(st.session_state.messages, st.session_state.active_source_name),
            file_name="library_customer_service_conversation.md",
            mime="text/markdown",
        )

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if question := st.chat_input(t(language, "question")):
        st.session_state.messages.append({"role": "user", "content": question})
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
            st.session_state.question_count += 1
            st.session_state.total_tokens += used_tokens
            st.rerun()
        except Exception as error:
            st.error(t(language, "answer_error", error=friendly_error(error, language)))


if __name__ == "__main__":
    main()
