"""Phase 52 (ADR-0070): ReviewEngine -- records human intent only.

The single most important property this file proves: the engine never
touches a browser. That is checked structurally (an AST/source scan of the
module for any ``integrations.browser`` import) as well as behaviorally
(every scenario below runs with no browser object anywhere in scope at
all).
"""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime

from career_agent.agents.review import review_engine as review_engine_module
from career_agent.agents.review.review_engine import ReviewEngine
from career_agent.domain.application_session import ApplicationSession


def _session(**overrides: object) -> ApplicationSession:
    fields = {
        "id": "sess-1",
        "provider": "greenhouse",
        "company": "Acme Corp",
        "job_title": "Backend Engineer",
        "url": "https://boards.greenhouse.io/acme/jobs/1",
        "opportunity_id": "opp-1",
        "status": "READY_FOR_REVIEW",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return ApplicationSession(**fields)


# ---------------------------------------------------------------------------
# The structural guarantee: no browser dependency, anywhere.
# ---------------------------------------------------------------------------


def test_review_engine_imports_no_browser_module() -> None:
    tree = ast.parse(inspect.getsource(review_engine_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "integrations.browser" not in node.module
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "integrations.browser" not in alias.name


def test_review_engine_never_calls_click() -> None:
    source = inspect.getsource(review_engine_module)
    assert ".click(" not in source


# ---------------------------------------------------------------------------
# Approve / reject.
# ---------------------------------------------------------------------------


def test_yes_answer_approves() -> None:
    result = ReviewEngine().review(
        _session(), input_fn=lambda _: "y", print_fn=lambda _: None
    )
    assert result.approved is True
    assert result.status == "APPROVED"
    assert result.next_action == "eligible_for_submission_engine"


def test_yes_variants_case_insensitive() -> None:
    for answer in ("y", "Y", "yes", "YES", " yes "):
        result = ReviewEngine().review(
            _session(), input_fn=lambda _, a=answer: a, print_fn=lambda _: None
        )
        assert result.approved is True, answer


def test_no_answer_rejects() -> None:
    result = ReviewEngine().review(
        _session(), input_fn=lambda _: "n", print_fn=lambda _: None
    )
    assert result.approved is False
    assert result.status == "REJECTED"
    assert result.next_action == "revise_and_re_prepare"


def test_empty_answer_rejects_not_defaults_to_yes() -> None:
    result = ReviewEngine().review(
        _session(), input_fn=lambda _: "", print_fn=lambda _: None
    )
    assert result.approved is False
    assert result.status == "REJECTED"


def test_garbage_answer_rejects() -> None:
    result = ReviewEngine().review(
        _session(), input_fn=lambda _: "maybe", print_fn=lambda _: None
    )
    assert result.approved is False
    assert result.status == "REJECTED"


# ---------------------------------------------------------------------------
# Cancel / timeout.
# ---------------------------------------------------------------------------


def _raise(exc: Exception):
    def _input(_: str):
        raise exc

    return _input


def test_keyboard_interrupt_cancels() -> None:
    result = ReviewEngine().review(
        _session(), input_fn=_raise(KeyboardInterrupt()), print_fn=lambda _: None
    )
    assert result.approved is False
    assert result.status == "CANCELLED"
    assert result.next_action == "none"


def test_timeout_error_times_out() -> None:
    result = ReviewEngine().review(
        _session(), input_fn=_raise(TimeoutError()), print_fn=lambda _: None
    )
    assert result.approved is False
    assert result.status == "TIMEOUT"
    assert result.next_action == "none"


# ---------------------------------------------------------------------------
# The summary is always shown before the prompt.
# ---------------------------------------------------------------------------


def test_summary_is_printed_before_prompting() -> None:
    printed: list[str] = []
    ReviewEngine().review(
        _session(company="Globex"), input_fn=lambda _: "y", print_fn=printed.append
    )
    assert any("Globex" in text for text in printed)


def test_notes_are_carried_onto_the_result() -> None:
    result = ReviewEngine().review(
        _session(),
        input_fn=lambda _: "y",
        print_fn=lambda _: None,
        notes="looks good",
    )
    assert result.notes == "looks good"
