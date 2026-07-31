import pytest

from app import (
    MAX_DOCUMENT_CHUNKS,
    MAX_FILE_SIZE_BYTES,
    MAX_QUESTIONS_PER_SESSION,
    has_reached_question_limit,
    validate_chunk_count,
    validate_file_size,
)


def test_file_size_accepts_exact_limit() -> None:
    validate_file_size(MAX_FILE_SIZE_BYTES)


def test_file_size_rejects_value_over_limit() -> None:
    with pytest.raises(ValueError, match="file_too_large"):
        validate_file_size(MAX_FILE_SIZE_BYTES + 1)


def test_chunk_count_accepts_exact_limit() -> None:
    validate_chunk_count(MAX_DOCUMENT_CHUNKS)


def test_chunk_count_rejects_value_over_limit() -> None:
    with pytest.raises(ValueError, match="too_many_chunks"):
        validate_chunk_count(MAX_DOCUMENT_CHUNKS + 1)


def test_question_limit_boundaries() -> None:
    assert not has_reached_question_limit(MAX_QUESTIONS_PER_SESSION - 1)
    assert has_reached_question_limit(MAX_QUESTIONS_PER_SESSION)
    assert has_reached_question_limit(MAX_QUESTIONS_PER_SESSION + 1)