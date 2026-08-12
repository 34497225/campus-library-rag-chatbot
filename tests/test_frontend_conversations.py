"""Tests for account-scoped Streamlit conversation state."""

import pytest

from frontend_conversations import (
    activate_conversation,
    build_conversation_title,
    clear_conversation_state,
    initialize_conversation_state,
    normalize_message,
    replace_conversations,
)


def conversation(item_id: str, title: str) -> dict[str, str]:
    """Build one complete fake ConversationRead response."""

    return {
        "id": item_id,
        "title": title,
        "created_at": "2026-08-12T10:00:00Z",
        "updated_at": "2026-08-12T10:05:00Z",
    }


def message(item_id: str, role: str, content: str) -> dict[str, str]:
    """Build one complete fake MessageRead response."""

    return {
        "id": item_id,
        "conversation_id": "conversation-1",
        "role": role,
        "content": content,
        "created_at": "2026-08-12T10:01:00Z",
    }


def test_initialize_conversation_state_preserves_existing_selection() -> None:
    state = {"active_conversation_id": "conversation-1"}

    initialize_conversation_state(state)

    assert state["active_conversation_id"] == "conversation-1"
    assert state["conversations"] == []
    assert state["pending_assistant_message"] is None


def test_replace_conversations_selects_first_and_preserves_valid_active() -> None:
    state: dict[str, object] = {
        "active_conversation_id": None,
        "loaded_conversation_id": None,
        "messages": [],
    }
    items = [conversation("first", "First"), conversation("second", "Second")]

    replace_conversations(state, items)
    assert state["active_conversation_id"] == "first"

    state["active_conversation_id"] = "second"
    replace_conversations(state, items)
    assert state["active_conversation_id"] == "second"


def test_replace_conversations_clears_removed_active_history() -> None:
    state: dict[str, object] = {
        "active_conversation_id": "removed",
        "loaded_conversation_id": "removed",
        "messages": [{"role": "user", "content": "private"}],
    }

    replace_conversations(state, [conversation("remaining", "Remaining")])

    assert state["active_conversation_id"] == "remaining"
    assert state["loaded_conversation_id"] is None
    assert state["messages"] == []


def test_activate_conversation_loads_safe_history_and_counts_questions() -> None:
    state: dict[str, object] = {
        "conversations": [conversation("conversation-1", "History")],
        "total_tokens": 999,
    }

    activate_conversation(
        state,
        "conversation-1",
        [
            message("message-1", "user", "Question"),
            message("message-2", "assistant", "Answer"),
        ],
    )

    assert state["loaded_conversation_id"] == "conversation-1"
    assert state["question_count"] == 1
    assert state["total_tokens"] == 0
    assert state["messages"] == [
        {
            "id": "message-1",
            "role": "user",
            "content": "Question",
            "created_at": "2026-08-12T10:01:00Z",
        },
        {
            "id": "message-2",
            "role": "assistant",
            "content": "Answer",
            "created_at": "2026-08-12T10:01:00Z",
        },
    ]


def test_activate_conversation_rejects_unlisted_id() -> None:
    with pytest.raises(ValueError, match="not present"):
        activate_conversation(
            {"conversations": []},
            "other-users-conversation",
            [],
        )


@pytest.mark.parametrize("role", ["system", "tool", ""])
def test_normalize_message_rejects_unsupported_role(role: str) -> None:
    with pytest.raises(ValueError):
        normalize_message(message("message-1", role, "Content"))


def test_build_conversation_title_normalizes_and_truncates() -> None:
    assert build_conversation_title("  library   hours  ") == "library hours"
    assert build_conversation_title("abcdefgh", limit=6) == "abcde…"
    assert build_conversation_title("   ") == "New conversation"


def test_clear_conversation_state_removes_account_specific_data() -> None:
    state: dict[str, object] = {
        "conversations": [conversation("one", "Private")],
        "active_conversation_id": "one",
        "loaded_conversation_id": "one",
        "pending_assistant_message": {"content": "Private answer"},
        "messages": [{"role": "user", "content": "Private question"}],
        "question_count": 1,
        "total_tokens": 20,
        "language": "zh",
    }

    clear_conversation_state(state)

    assert state["conversations"] == []
    assert state["active_conversation_id"] is None
    assert state["messages"] == []
    assert state["pending_assistant_message"] is None
    assert state["language"] == "zh"
