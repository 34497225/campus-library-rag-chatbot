"""Conversation-state helpers shared by Streamlit and isolated tests."""

from collections.abc import MutableMapping
from typing import Any


CONVERSATIONS_KEY = "conversations"
ACTIVE_CONVERSATION_ID_KEY = "active_conversation_id"
LOADED_CONVERSATION_ID_KEY = "loaded_conversation_id"
PENDING_ASSISTANT_KEY = "pending_assistant_message"


def initialize_conversation_state(
    state: MutableMapping[str, Any],
) -> None:
    """Create persistence keys without overwriting a running session."""

    defaults: dict[str, Any] = {
        CONVERSATIONS_KEY: [],
        ACTIVE_CONVERSATION_ID_KEY: None,
        LOADED_CONVERSATION_ID_KEY: None,
        PENDING_ASSISTANT_KEY: None,
    }

    for key, value in defaults.items():
        if key not in state:
            state[key] = value


def clear_conversation_state(
    state: MutableMapping[str, Any],
) -> None:
    """Remove every account-specific conversation value on logout."""

    state[CONVERSATIONS_KEY] = []
    state[ACTIVE_CONVERSATION_ID_KEY] = None
    state[LOADED_CONVERSATION_ID_KEY] = None
    state[PENDING_ASSISTANT_KEY] = None
    state["messages"] = []
    state["question_count"] = 0
    state["total_tokens"] = 0


def replace_conversations(
    state: MutableMapping[str, Any],
    conversations: list[dict[str, Any]],
) -> None:
    """Store a fresh API list and keep the active item when it still exists."""

    normalized = [normalize_conversation(item) for item in conversations]
    state[CONVERSATIONS_KEY] = normalized

    available_ids = {item["id"] for item in normalized}
    active_id = state.get(ACTIVE_CONVERSATION_ID_KEY)

    if active_id not in available_ids:
        state[ACTIVE_CONVERSATION_ID_KEY] = (
            normalized[0]["id"] if normalized else None
        )
        state[LOADED_CONVERSATION_ID_KEY] = None
        state["messages"] = []


def activate_conversation(
    state: MutableMapping[str, Any],
    conversation_id: str,
    messages: list[dict[str, Any]],
) -> None:
    """Select one conversation and load its safe ordered message history."""

    available_ids = {
        item["id"] for item in state.get(CONVERSATIONS_KEY, [])
    }
    if conversation_id not in available_ids:
        raise ValueError("Conversation is not present in the current list.")

    normalized_messages = [normalize_message(item) for item in messages]
    state[ACTIVE_CONVERSATION_ID_KEY] = conversation_id
    state[LOADED_CONVERSATION_ID_KEY] = conversation_id
    state["messages"] = [
        {
            "id": item["id"],
            "role": item["role"],
            "content": item["content"],
            "created_at": item["created_at"],
        }
        for item in normalized_messages
    ]
    state["question_count"] = sum(
        item["role"] == "user" for item in normalized_messages
    )
    # Token usage is not stored in the Message table, so a reloaded history
    # starts this session-only metric at zero instead of inventing a value.
    state["total_tokens"] = 0


def build_conversation_title(question: str, limit: int = 60) -> str:
    """Turn the first question into a short readable conversation title."""

    normalized = " ".join(question.split())
    if not normalized:
        return "New conversation"

    if len(normalized) <= limit:
        return normalized

    return f"{normalized[: limit - 1].rstrip()}…"


def normalize_conversation(item: dict[str, Any]) -> dict[str, str]:
    """Accept only the public ConversationRead fields needed by the UI."""

    safe = {
        "id": item.get("id"),
        "title": item.get("title"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }
    if not all(isinstance(value, str) and value for value in safe.values()):
        raise ValueError("Conversation response is missing required fields.")

    return safe


def normalize_message(item: dict[str, Any]) -> dict[str, str]:
    """Accept only safe MessageRead data and validate its role contract."""

    safe = {
        "id": item.get("id"),
        "conversation_id": item.get("conversation_id"),
        "role": item.get("role"),
        "content": item.get("content"),
        "created_at": item.get("created_at"),
    }
    if not all(isinstance(value, str) and value for value in safe.values()):
        raise ValueError("Message response is missing required fields.")

    if safe["role"] not in {"user", "assistant"}:
        raise ValueError("Message response used an unsupported role.")

    return safe
