"""Phase 59 (ADR-0076): structured logging configuration."""

from __future__ import annotations

import json
import logging

import pytest

from career_agent.core.config import Settings
from career_agent.core.logging_config import (
    JsonFormatter,
    configure_logging,
    effective_json_logs,
)


@pytest.fixture
def _restore_root_handlers():
    """`configure_logging` replaces every root handler -- restore whatever
    pytest's own logging setup left in place so later tests aren't affected."""
    root = logging.getLogger()
    original = list(root.handlers)
    original_level = root.level
    yield
    root.handlers[:] = original
    root.setLevel(original_level)


def test_effective_json_logs_defaults_on_in_production() -> None:
    settings = Settings(environment="production", json_logs=None)
    assert effective_json_logs(settings) is True


def test_effective_json_logs_defaults_off_outside_production() -> None:
    settings = Settings(environment="development", json_logs=None)
    assert effective_json_logs(settings) is False


def test_effective_json_logs_explicit_setting_wins() -> None:
    prod_off = Settings(environment="production", json_logs=False)
    dev_on = Settings(environment="development", json_logs=True)
    assert effective_json_logs(prod_off) is False
    assert effective_json_logs(dev_on) is True


def test_json_formatter_emits_valid_json_with_extras() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="career_agent.api.requests",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="GET /health -> 200",
        args=(),
        exc_info=None,
    )
    record.status_code = 200
    payload = json.loads(formatter.format(record))
    assert payload["message"] == "GET /health -> 200"
    assert payload["level"] == "INFO"
    assert payload["status_code"] == 200


def test_configure_logging_does_not_duplicate_handlers(_restore_root_handlers) -> None:
    """Calling this twice (e.g. two lifespan starts in one process) must
    never accumulate a second handler -- exactly one survives either way,
    regardless of what a test runner's own logging setup left in place."""
    configure_logging(Settings(environment="development"))
    configure_logging(Settings(environment="development"))
    root = logging.getLogger()
    assert len(root.handlers) == 1
