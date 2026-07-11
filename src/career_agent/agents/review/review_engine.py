"""ReviewEngine: presents a summary and records one explicit human decision.

**This class touches no browser, ever.** It never imports anything from
``career_agent.integrations.browser`` and never sees a live Playwright
``Page`` -- ``ApplicationSession`` is already pure, fully-serialized data
by the time it reaches here (Phase 51). A source-scan test
(``tests/agents/test_review_engine.py::test_review_engine_imports_no_browser``)
proves this structurally, the same discipline
``ApplicationPreparationEngine``'s no-click guarantee already established.

Only an explicit "y"/"yes" (case-insensitive) answer produces
``APPROVED`` -- mirroring ``cli.py::confirm_submission``'s exact same
no-default-to-yes discipline. There is no code path in this class that can
mark a review approved without that literal answer.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from career_agent.domain.application_session import ApplicationSession
from career_agent.domain.review import ReviewResult, format_review_summary

_YES = {"y", "yes"}


class ReviewEngine:
    """Presents ``ApplicationSession``s for human approval. Records intent only."""

    def review(
        self,
        session: ApplicationSession,
        *,
        input_fn: Callable[[str], str] = input,
        notes: str | None = None,
        print_fn: Callable[[str], None] = print,
    ) -> ReviewResult:
        """Print a deterministic summary, ask for approval, return the decision.

        ``input_fn`` is the sole way this method can conclude ``TIMEOUT``
        or ``CANCELLED``: raising :class:`TimeoutError` or
        :class:`KeyboardInterrupt` respectively. Production use passes
        plain :func:`input` (waits indefinitely, exactly like
        ``confirm_submission``); a caller wanting a bounded wait supplies
        its own timeout-raising wrapper -- this class has no timer of its
        own, since a portable, cross-platform stdin timeout is a real,
        separate concern this phase does not need to solve to prove the
        state exists and is handled correctly.
        """
        print_fn(format_review_summary(session))
        review_time = datetime.now(UTC)
        try:
            answer = input_fn("Approve? [y/N]: ").strip().lower()
        except KeyboardInterrupt:
            return ReviewResult(
                approved=False,
                status="CANCELLED",
                notes=notes,
                review_time=review_time,
                next_action="none",
            )
        except TimeoutError:
            return ReviewResult(
                approved=False,
                status="TIMEOUT",
                notes=notes,
                review_time=review_time,
                next_action="none",
            )

        if answer in _YES:
            return ReviewResult(
                approved=True,
                status="APPROVED",
                notes=notes,
                review_time=review_time,
                next_action="eligible_for_submission_engine",
            )
        return ReviewResult(
            approved=False,
            status="REJECTED",
            notes=notes,
            review_time=review_time,
            next_action="revise_and_re_prepare",
        )
