import json
from pathlib import Path

import pytest

from app import (
    fallback_response,
    greeting_response,
    normalize_fallback_answer,
    response_language_for,
)
from rag_evaluation import (
    load_cases,
    percentile,
    render_markdown,
    score_case,
)


def test_load_cases_rejects_duplicate_ids(tmp_path: Path) -> None:
    dataset = tmp_path / "cases.json"
    dataset.write_text(
        json.dumps(
            [
                {"id": "same", "question": "one"},
                {"id": "same", "question": "two"},
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate"):
        load_cases(dataset)


def test_score_case_requires_every_keyword_group() -> None:
    case = load_cases(Path("evaluation/rag_cases.json"))[0]

    retrieval, answer = score_case(
        case,
        "The source contains 08:30 and 21:00.",
        "Open from 08:30 until 21:00.",
    )

    assert retrieval is True
    assert answer is True


def test_percentile_uses_nearest_rank() -> None:
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.95) == 4.0
    assert percentile([], 0.95) == 0.0


def test_response_language_is_explicit_for_supported_languages() -> None:
    assert response_language_for("這本書可以借嗎？") == "Traditional Chinese"
    assert response_language_for("Can I borrow this book?") == "English"


def test_response_language_uses_interface_language_for_numbers_and_symbols() -> None:
    assert response_language_for("123", "Traditional Chinese") == "Traditional Chinese"
    assert response_language_for("123", "English") == "English"
    assert response_language_for("?!", "Traditional Chinese") == "Traditional Chinese"


def test_fallback_response_hands_off_to_library_staff() -> None:
    assert "圖書館櫃台" in fallback_response("Traditional Chinese")
    assert "service desk" in fallback_response("English")


def test_old_model_fallback_is_normalized_to_service_desk_handoff() -> None:
    old_answer = "抱歉，目前的資訊並未涵蓋這個問題。您可以重新表達問題。"

    answer = normalize_fallback_answer(old_answer, "Traditional Chinese")

    assert answer == fallback_response("Traditional Chinese")
    assert "圖書館櫃台" in answer


def test_normal_answer_is_not_changed_by_fallback_normalization() -> None:
    answer = "圖書館平日開放時間為 08:30 至 21:00。"

    assert normalize_fallback_answer(answer, "Traditional Chinese") == answer


def test_greeting_detection_does_not_match_substantive_english_questions() -> None:
    assert greeting_response("Hello!") is not None
    assert greeting_response("Where can I check out a library item?") is None
    assert greeting_response("How can I place a hold?") is None


def test_report_does_not_include_raw_answers() -> None:
    report = {
        "dataset_cases": 1,
        "retrieval_cases": 1,
        "retrieval_hit_rate": 1.0,
        "answer_pass_rate": 1.0,
        "index_seconds": 0.1,
        "average_latency_seconds": 0.2,
        "p95_latency_seconds": 0.2,
        "total_tokens": 50,
        "results": [
            {
                "id": "safe-case",
                "retrieval_passed": True,
                "answer_passed": True,
                "latency_seconds": 0.2,
                "tokens": 50,
            }
        ],
    }

    rendered = render_markdown(report)

    assert "safe-case" in rendered
    assert "Raw model answers are intentionally not committed" in rendered
