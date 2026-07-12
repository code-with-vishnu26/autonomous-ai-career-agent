"""Phase 61 (ADR-0079): the request-correlation-ID contextvar and log filter."""

from __future__ import annotations

import logging

from career_agent.core.request_context import (
    RequestIdLogFilter,
    current_request_id,
    reset_request_id,
    set_request_id,
)


def test_current_request_id_defaults_to_empty_string() -> None:
    assert current_request_id() == ""


def test_set_and_reset_request_id() -> None:
    token = set_request_id("abc-123")
    try:
        assert current_request_id() == "abc-123"
    finally:
        reset_request_id(token)
    assert current_request_id() == ""


def test_nested_set_reset_restores_the_outer_value() -> None:
    outer_token = set_request_id("outer")
    inner_token = set_request_id("inner")
    assert current_request_id() == "inner"
    reset_request_id(inner_token)
    assert current_request_id() == "outer"
    reset_request_id(outer_token)
    assert current_request_id() == ""


def test_log_filter_stamps_the_current_request_id_onto_a_record() -> None:
    token = set_request_id("filter-test-id")
    try:
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname=__file__,
            lineno=1, msg="hello", args=(), exc_info=None,
        )
        result = RequestIdLogFilter().filter(record)
        assert result is True
        assert record.request_id == "filter-test-id"  # type: ignore[attr-defined]
    finally:
        reset_request_id(token)


def test_log_filter_stamps_empty_string_outside_a_request() -> None:
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__,
        lineno=1, msg="hello", args=(), exc_info=None,
    )
    RequestIdLogFilter().filter(record)
    assert record.request_id == ""  # type: ignore[attr-defined]
