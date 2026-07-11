"""SubmissionEngine: the only code path that may click a real Submit button.

Composes the existing, real Tier-2 executor
(:class:`~career_agent.agents.apply.browser_applicator.BrowserApplicator`,
ADR-0020/0028/0032 -- built, tested, and unwired from the CLI since Phase
7b3, specifically pending the execution-safety boundary this phase finally
satisfies) behind the fail-closed permission gate
(:mod:`career_agent.domain.execution`, ADR-0050) that has been waiting for
exactly this moment since Phase 24: *"this module does not enable
execution; it defines the conditions under which execution would be
permitted, so that a future phase wiring a real executor cannot do so
without satisfying every condition here."*

**Every precondition is checked before the browser is ever touched a
second time**, and a real, final, un-bypassable human confirmation (the
countdown + "press ENTER") happens only after every other condition
already holds -- so a doomed attempt never wastes the human's attention
asking them to confirm something that was always going to be refused.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from career_agent.agents.apply.browser_applicator import (
    BrowserApplicator,
    ChallengeStillPresentError,
    NoApplicableFormFillerError,
    RequiredFieldsStillUnresolvedError,
    UnsupportedFormFieldsError,
)
from career_agent.agents.apply.form_fillers import (
    FormFiller,
    FormFillerNotImplementedError,
    MissingResumeArtifactError,
)
from career_agent.core.events import ApplicationSubmitted, HumanActionRequired
from career_agent.domain.application_session import ApplicationSession
from career_agent.domain.ats_urls import resolve_ats_kind
from career_agent.domain.execution import (
    ExecutionRequest,
    SubmissionOutcome,
    execute_allowed,
    resolve_source_policy,
)
from career_agent.domain.models import (
    HumanConfirmation,
    Opportunity,
    PauseAcknowledgment,
    SubmittableApplication,
    TailoredContent,
)
from career_agent.domain.review import ReviewSession
from career_agent.domain.submission import SubmissionResult
from career_agent.integrations.adapters.base import FeatureUnavailableError
from career_agent.storage.memory import InMemoryOpportunityRepository

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext

    from career_agent.integrations.browser_session import EncryptedSessionStore


class CancelledByUserError(Exception):
    """The human declined the final countdown/confirmation prompt."""


def _default_confirm() -> bool:
    """Production default: block on a real ENTER, never auto-confirm."""
    input("Press ENTER to submit, or Ctrl+C to cancel: ")
    return True


class SubmissionEngine:
    """Fail-closed gate in front of the existing, real Tier-2 executor."""

    def __init__(
        self,
        session_store: EncryptedSessionStore,
        *,
        form_fillers: dict[str, FormFiller] | None = None,
        chromium_executable_path: str | None = None,
        on_context_ready: Callable[[BrowserContext], Awaitable[None]] | None = None,
    ) -> None:
        """Configure the session store and Chromium.

        The same way ``BrowserApplicator`` already does -- this class
        constructs one internally per call, never reusing a
        cross-invocation live browser handle (none can survive a process
        boundary anyway).
        """
        self._session_store = session_store
        self._form_fillers = form_fillers
        self._chromium_executable_path = chromium_executable_path
        self._on_context_ready = on_context_ready

    async def submit(
        self,
        opportunity: Opportunity,
        application: SubmittableApplication,
        review_session: ReviewSession,
        application_session: ApplicationSession,
        stored_variant_content: TailoredContent | None,
        *,
        prior_outcome: SubmissionOutcome = SubmissionOutcome.NOT_ATTEMPTED,
        confirm_fn: Callable[[], bool] = _default_confirm,
    ) -> SubmissionResult:
        """Attempt one submission. Fail-closed at every step; never guesses."""
        result_id = str(uuid.uuid4())
        started_at = datetime.now(UTC)

        def _finish(
            *, status: str, submitted: bool, warnings: list[str] | None = None,
            refusal_reason: str | None = None, confirmation_id: str | None = None,
        ) -> SubmissionResult:
            return SubmissionResult(
                id=result_id,
                application_session_id=application_session.id,
                review_session_id=review_session.id,
                opportunity_id=opportunity.id,
                provider=application_session.provider,
                company=application_session.company,
                job_title=application_session.job_title,
                submitted=submitted,
                status=status,  # type: ignore[arg-type]
                confirmation_id=confirmation_id,
                submitted_at=datetime.now(UTC) if submitted else None,
                duration_seconds=(datetime.now(UTC) - started_at).total_seconds(),
                warnings=warnings or [],
                refusal_reason=refusal_reason,
            )

        # -- Preconditions this module checks itself, before ever consulting
        # -- the execution-safety boundary (ADR-0071's own explicit list).
        if review_session.application_session_id != application_session.id:
            return _finish(
                status="REFUSED", submitted=False,
                refusal_reason="review_application_mismatch",
            )
        if review_session.approval_status != "APPROVED":
            return _finish(
                status="REFUSED", submitted=False,
                refusal_reason="review_not_approved",
            )
        if application_session.status != "READY_FOR_REVIEW":
            return _finish(
                status="REFUSED", submitted=False,
                refusal_reason="application_not_ready",
            )

        artifact_matches = (
            stored_variant_content is not None
            and stored_variant_content == application.application.resume.content
        )

        ats_kind = resolve_ats_kind(opportunity.source_url)
        source_policy = resolve_source_policy(opportunity.source, ats_kind)

        # Dry-run the boundary with confirmation_present=True: if anything
        # OTHER than confirmation would refuse, find out now -- never make
        # the human sit through a countdown for an attempt that was always
        # going to be refused.
        preflight = execute_allowed(
            ExecutionRequest(
                source_policy=source_policy,
                executor_available=True,
                confirmation_present=True,
                artifact_matches=artifact_matches,
                prior_outcome=prior_outcome,
                journal_has_unresolved_intent=False,
            )
        )
        if not preflight.allowed:
            return _finish(
                status="REFUSED", submitted=False, refusal_reason=preflight.reason
            )

        # The real, final, un-bypassable human gate.
        try:
            confirm_fn()
        except (KeyboardInterrupt, CancelledByUserError):
            return _finish(status="CANCELLED", submitted=False)

        repo = InMemoryOpportunityRepository()
        await repo.add(opportunity)
        applicator = BrowserApplicator(
            self._session_store,
            repo,
            form_fillers=self._form_fillers,
            chromium_executable_path=self._chromium_executable_path,
            on_context_ready=self._on_context_ready,
        )
        try:
            preview = await applicator.prepare(application)
        except NoApplicableFormFillerError as exc:
            raise FeatureUnavailableError(
                f"no submission support for opportunity {opportunity.id!r}: {exc}"
            ) from exc

        confirmation = HumanConfirmation(
            preview_token=preview.preview_token,
            confirmed_by="career-agent submit",
            confirmed_at=datetime.now(UTC),
        )
        try:
            event = await applicator.submit(preview, confirmation)
        except (UnsupportedFormFieldsError, MissingResumeArtifactError) as exc:
            # Both are raised before any click -- verified by reading
            # BrowserApplicator.submit()'s own control flow (fill/triage
            # happens entirely inside a try block that closes the browser
            # and re-raises *before* _click_submit_and_check_challenge is
            # ever reached). Safe to record as a definite non-submission.
            return _finish(status="FAILED", submitted=False, warnings=[str(exc)])
        except FormFillerNotImplementedError as exc:
            raise FeatureUnavailableError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 -- an unforeseen failure anywhere
            # inside submit(), which also contains the click itself -- an
            # exception here does NOT prove the click never fired, so this
            # is UNKNOWN (never FAILED): the same "ambiguous evidence can
            # never become a definite result" discipline
            # domain.execution.outcome_from_ack already enforces.
            return _finish(status="UNKNOWN", submitted=False, warnings=[str(exc)])

        if isinstance(event, ApplicationSubmitted):
            return _finish(
                status="SUBMITTED",
                submitted=True,
                warnings=[
                    "no verified confirmation-id/receipt selector exists for "
                    "any platform in this codebase -- confirmation_id is "
                    "intentionally left unset rather than guessed"
                ],
            )

        if isinstance(event, HumanActionRequired):
            return await self._resolve_pause(applicator, event, _finish)

        return _finish(status="UNKNOWN", submitted=False, warnings=[str(event)])

    async def _resolve_pause(
        self, applicator: BrowserApplicator, event: HumanActionRequired, finish
    ) -> SubmissionResult:
        """One resume attempt for a Phase A/B pause -- never an unbounded loop.

        The human clears the challenge or fills the manifested fields
        directly on the visible browser window (this class never does
        either itself), then this prompts once for acknowledgment. If
        still unresolved, records ``UNKNOWN`` and tells the human to check
        the browser directly rather than guessing or retrying silently.
        """
        pause_tokens = list(applicator._paused)  # noqa: SLF001 -- same-package access
        if not pause_tokens:
            return finish(status="UNKNOWN", submitted=False)
        pause_token = pause_tokens[-1]
        print(f"Action required ({event.reason}): complete it on the visible browser.")
        input("Press ENTER once resolved: ")
        ack = PauseAcknowledgment(
            pause_token=pause_token,
            confirmed_by="career-agent submit",
            confirmed_at=datetime.now(UTC),
        )
        try:
            resumed = await applicator.resume(pause_token, ack)
        except (ChallengeStillPresentError, RequiredFieldsStillUnresolvedError) as exc:
            return finish(
                status="UNKNOWN",
                submitted=False,
                warnings=[
                    f"still unresolved after one resume attempt: {exc}. Check "
                    f"the browser window directly."
                ],
            )
        if isinstance(resumed, ApplicationSubmitted):
            return finish(
                status="SUBMITTED",
                submitted=True,
                warnings=[
                    "no verified confirmation-id/receipt selector exists for "
                    "any platform in this codebase -- confirmation_id is "
                    "intentionally left unset rather than guessed"
                ],
            )
        return finish(status="UNKNOWN", submitted=False, warnings=[str(resumed)])
