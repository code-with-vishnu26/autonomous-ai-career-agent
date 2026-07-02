"""Phase 8c / ADR-0024: confirm_submission is this project's first real,
executable HumanConfirmation source -- no default-to-yes path, ever.
"""

from __future__ import annotations

from career_agent.cli import confirm_submission
from career_agent.domain.models import SubmissionPreview


def _preview() -> SubmissionPreview:
    return SubmissionPreview(
        application_id="app-1",
        tier="ats_api",
        target="greenhouse",
        rendered_content="Experienced engineer.",
        preview_token="token-123",
    )


def test_yes_produces_a_confirmation_naming_the_exact_preview() -> None:
    confirmation = confirm_submission(_preview(), input_fn=lambda _: "y")
    assert confirmation is not None
    assert confirmation.preview_token == "token-123"


def test_yes_is_case_insensitive_and_whitespace_tolerant() -> None:
    confirmation = confirm_submission(_preview(), input_fn=lambda _: "  YES  ")
    assert confirmation is not None


def test_explicit_no_returns_none() -> None:
    assert confirm_submission(_preview(), input_fn=lambda _: "n") is None


def test_empty_input_returns_none_not_a_default_yes() -> None:
    """The load-bearing test: silence must never be treated as consent."""
    assert confirm_submission(_preview(), input_fn=lambda _: "") is None


def test_malformed_input_returns_none_rather_than_crashing() -> None:
    assert confirm_submission(_preview(), input_fn=lambda _: "asdf;lkj") is None


def test_confirmed_by_can_be_overridden() -> None:
    confirmation = confirm_submission(
        _preview(), input_fn=lambda _: "y", confirmed_by="test-user"
    )
    assert confirmation is not None
    assert confirmation.confirmed_by == "test-user"
