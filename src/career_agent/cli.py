"""Command-line entry point for the Autonomous AI Career Agent.

``confirm_submission`` (Phase 8c, ADR-0024) is this project's first real,
executable source of a :class:`~career_agent.domain.models.HumanConfirmation`.

``apply`` (Phase 8e, ADR-0026) is the runnable command that acts on one
opportunity: load a real profile and a real opportunity, tailor and gate a
real resume with the real, Groq/Claude-backed generator and verifier,
render it, and ask a real human to confirm it. It deliberately stops there
-- real submission (Tier 2 browser, Tier 3 email draft-only) is a separate,
supervised act via the tiered ``Applicator``, never automatic from
``apply`` itself.

**The real ``ClaimVerifier`` is gated by an actual check, not a claim.**
ADR-0016 requires the promptfoo suite to pass on live calls before a real
``ClaimVerifier`` is wired into a real apply/auto path. That requirement is
enforced structurally, not just by written policy and the import-linter
contract that (correctly) leaves ``cli.py`` itself unconstrained, since it
is the composition root: ``run_apply_command``/``run_auto_command`` both
call :func:`~career_agent.llm.promptfoo_gate.verify_promptfoo_results`
before constructing the real verifier -- refusing to run without a real,
current, actually-passing results artifact on disk, not a flag typed from
memory.

The opportunity ``apply`` acts on is read from a plain JSON file
(``--opportunity-file``) -- the same handoff format ``discover`` (Phase 13,
ADR-0037) and ``auto`` (Phase 17, ADR-0041) both write, so a future
persistent-store lookup could replace the file handoff without either
command's internal tailoring/gating logic needing to change. ``auto`` is
the one bounded, cron-safe pass that composes discover -> rank -> tailor+gate
-> record -> notify end to end -- structurally incapable of confirming or
submitting (no input function, no ``HumanConfirmation``, no ``Applicator``
anywhere in its call graph), always ending with a handoff file and a
notification pointing back at ``apply`` for the human's own confirmation.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from career_agent import __version__
from career_agent.agents.application.engine import ApplicationPreparationEngine
from career_agent.agents.planner.decide import DecisionScore
from career_agent.agents.planner.sensitivity import RankFlipPoint, rank_flip_points
from career_agent.agents.resume.gate import LLMTruthfulnessGate
from career_agent.agents.resume.generator import LLMResumeGenerator, MissingSummaryError
from career_agent.agents.resume.materials import ResumeVariantEngine
from career_agent.agents.resume.pipeline import ResumeTailoringPipeline
from career_agent.agents.review.review_engine import ReviewEngine
from career_agent.agents.submission.submission_engine import SubmissionEngine
from career_agent.core.bus import EventBus
from career_agent.core.config import Settings
from career_agent.core.interfaces import (
    ResumeGenerator,
    SemanticKeywordMatcher,
    TruthfulnessGate,
)
from career_agent.domain.application_session import ApplicationSession
from career_agent.domain.ats_scoring import AtsScoreBelowThresholdError
from career_agent.domain.ats_urls import resolve_ats_kind
from career_agent.domain.execution import (
    ExecutionRequest,
    SubmissionOutcome,
    execute_allowed,
    resolve_source_policy,
)
from career_agent.domain.ingestion import ADD, IngestionDraft
from career_agent.domain.job_preferences import (
    JobPreferences,
    generate_search_queries,
)
from career_agent.domain.models import (
    Application,
    HumanConfirmation,
    LegalStatusSection,
    MasterProfile,
    Opportunity,
    SubmissionPreview,
)
from career_agent.domain.pareto import ObjectivePoint, analyze_frontier
from career_agent.domain.review import ReviewSession, build_review_session
from career_agent.domain.submission import SubmissionResult
from career_agent.integrations.adapters.base import FeatureUnavailableError
from career_agent.integrations.browser.browser_manager import BrowserManager
from career_agent.integrations.browser.session_manager import SessionManager
from career_agent.integrations.browser_session import (
    EncryptedSessionStore,
    KeyringKeyProvider,
)
from career_agent.llm.promptfoo_gate import (
    PromptfooNotValidatedError,
    diagnose_prompt_drift,
    verify_promptfoo_results,
)
from career_agent.llm.prompts import TRUTHFULNESS_GATE_PROMPT_VERSION
from career_agent.llm.providers import (
    NoLLMProviderConfiguredError,
    select_claim_verifier,
    select_content_drafter,
    select_semantic_matcher,
)
from career_agent.storage.cv_ingest import (
    DocumentParseError,
    UnsupportedDocumentError,
    apply_confirmed_promotions,
    document_digest,
    ingest_document,
    read_document,
)
from career_agent.storage.excel import export_applications
from career_agent.storage.job_preferences import (
    load_job_preferences,
    save_job_preferences,
)
from career_agent.storage.profile import (
    ProfileValidationError,
    load_master_profile,
    save_legal_status,
    write_profile_scaffold,
)
from career_agent.storage.sqlite import (
    SqliteApplicationSessionStore,
    SqliteApplicationStore,
    SqliteOpportunityRepository,
    SqliteResumeVariantStore,
    SqliteReviewSessionStore,
    SqliteRunJournal,
    SqliteSubmissionResultStore,
)

_YES = {"y", "yes"}


def confirm_submission(
    preview: SubmissionPreview,
    *,
    input_fn: Callable[[str], str] = input,
    confirmed_by: str | None = None,
) -> HumanConfirmation | None:
    """Show ``preview`` and ask for an explicit yes/no confirmation.

    Returns ``None`` -- never a :class:`HumanConfirmation` -- for anything
    other than an exact "y"/"yes" (case-insensitive) answer, including
    empty or malformed input. There is no default-to-yes path: silence or
    an unrecognized answer is treated as "no," not as "proceed."
    """
    print(f"Tier: {preview.tier}")
    print(f"Target: {preview.target}")
    print("Content:")
    print(preview.rendered_content)
    print()
    answer = input_fn("Submit this application? [y/N]: ").strip().lower()
    if answer not in _YES:
        return None
    return HumanConfirmation(
        preview_token=preview.preview_token,
        confirmed_by=confirmed_by or getpass.getuser(),
        confirmed_at=datetime.now(UTC),
    )


def _load_opportunity(path: Path) -> Opportunity:
    """Load an :class:`Opportunity` from a plain JSON file.

    Raises ``OSError``/``json.JSONDecodeError``/``pydantic.ValidationError``
    on a missing, malformed, or invalid file -- the caller is responsible
    for catching these and printing a clean message. Explicit
    ``encoding="utf-8"`` -- a real opportunity's title/description can
    carry non-ASCII content (accented names, CJK text, emoji), and without
    this, ``Path.read_text()`` falls back to the platform's default
    encoding (cp1252 on Windows), which cannot decode/encode it.
    """
    return Opportunity.model_validate(
        json.loads(path.read_text(encoding="utf-8"))
    )


async def _apply_pipeline(
    profile: MasterProfile,
    opportunity: Opportunity,
    generator: ResumeGenerator,
    gate: TruthfulnessGate,
    *,
    input_fn: Callable[[str], str] = input,
    artifacts_dir: Path | None = None,
    ats_threshold: float | None = None,
    semantic_matcher: SemanticKeywordMatcher | None = None,
    application_store: SqliteApplicationStore | None = None,
    run_journal: SqliteRunJournal | None = None,
    notifier: object | None = None,
) -> int:
    """Tailor, gate, render, and confirm -- injectable for testing.

    Returns a process exit code. Never raises for an expected failure mode
    (a missing summary, a gate rejection, a declined confirmation) --
    prints a clean message and returns non-zero/zero as appropriate instead.
    Deliberately does not call any ``Applicator``: no real ``ATSAdapter``
    exists yet, so there is nothing real to submit through (ADR-0026).

    ``artifacts_dir`` (Phase 9, ADR-0033): where real DOCX/PDF files are
    written for an approved resume; ``None`` skips file generation.

    ``application_store`` (Phase 22, ADR-0048), when given, is consulted
    *before* tailoring even starts: an opportunity with an existing
    non-``"rejected"`` application record is refused outright, since a
    fresh attempt risks a duplicate real-world submission. This tool never
    decides that risk is acceptable on the user's behalf -- resolving it
    (or removing the stale record) is an explicit human act.

    ``run_journal`` (Phase 23, ADR-0049), when given, records this
    invocation's own stage transitions under a fresh ``run_id`` -- purely
    for reconstruction/auditability, never a gate: this call's actual
    behavior is identical whether or not a journal is supplied.
    """
    run_id = str(uuid.uuid4())

    def _emit(
        stage: str,
        event_type: str,
        *,
        outcome: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        if run_journal is not None:
            run_journal.append(
                run_id, stage, event_type, outcome=outcome, metadata=metadata
            )

    _emit("run", "RUN_STARTED", metadata={"opportunity_id": opportunity.id})

    if application_store is not None:
        prior_status = application_store.prior_attempt_status(opportunity.id)
        if prior_status is not None:
            print(
                f"Refusing to tailor: opportunity {opportunity.id!r} already "
                f"has a recorded application attempt with status "
                f"{prior_status!r}. Applying again could create a duplicate "
                f"real-world submission -- this is never retried "
                f"automatically. If the prior record is stale or wrong, "
                f"resolve it directly in the application store first."
            )
            _emit(
                "idempotency_guard",
                "RUN_REFUSED",
                outcome=prior_status,
            )
            return 1
    bus = EventBus()
    if notifier is not None:
        from career_agent.core.events import (
            ApplicationFailed,
            HumanActionRequired,
            OutcomeRecorded,
        )
        from career_agent.integrations.notifications import NotifyingSubscriber

        subscriber = NotifyingSubscriber(notifier)  # notify, never gate
        for event_type in (HumanActionRequired, ApplicationFailed, OutcomeRecorded):
            bus.subscribe(event_type, subscriber)
    pipeline = ResumeTailoringPipeline(
        generator,
        gate,
        bus,
        artifacts_dir=artifacts_dir,
        ats_threshold=ats_threshold,
        semantic_matcher=semantic_matcher,
    )
    _emit("tailoring", "TAILORING_STARTED")
    try:
        result = await pipeline.run(opportunity, profile)
    except MissingSummaryError as exc:
        print(f"Cannot tailor a resume: {exc}")
        _emit("tailoring", "RUN_COMPLETED", outcome="missing_summary")
        return 1
    except AtsScoreBelowThresholdError as exc:
        print("The ATS score gate refused this application:")
        print(str(exc))
        _emit("tailoring", "RUN_COMPLETED", outcome="ats_gate_failed")
        return 1
    _emit("tailoring", "TAILORING_COMPLETED")

    def _record(application: Application, *, ats_total: float | None) -> None:
        # Recorded once per run, only after this run's true terminal status
        # is known (Phase 36/ADR-0058): a rejected or declined attempt made
        # zero real-world side effect, so its row must read back that way to
        # ``prior_attempt_status`` -- never the placeholder "pending" a
        # since-declined run would otherwise be stuck at forever.
        if application_store is not None:
            application_store.record(
                application,
                company=opportunity.canonical_company,
                source=opportunity.source,
                ats_total=ats_total,
            )

    ats_total = result.ats_report.total if result.ats_report else None

    if result.submittable is None:
        _record(result.application, ats_total=ats_total)
        print("The truthfulness gate rejected this draft:")
        for rejection in result.application.resume.truthfulness.rejections:
            print(f"  - [{rejection.category}] {rejection.detail}")
        _emit("truthfulness", "RUN_COMPLETED", outcome="rejected")
        return 1
    _emit("truthfulness", "TRUTHFULNESS_APPROVED")

    rendered = result.application.resume.rendered_text or ""
    print(rendered)
    for artifact in result.application.resume.artifacts:
        print(f"Wrote {artifact.format.upper()}: {artifact.path}")

    preview = SubmissionPreview(
        application_id=result.application.id,
        tier="ats_api",
        target=opportunity.source_url,
        rendered_content=rendered,
        preview_token=str(uuid.uuid4()),
    )
    _emit("confirmation", "AWAITING_CONFIRMATION")
    confirmation = confirm_submission(preview, input_fn=input_fn)
    if confirmation is None:
        _record(
            result.application.model_copy(update={"status": "declined"}),
            ats_total=ats_total,
        )
        print("Not confirmed. Exiting without submitting.")
        _emit("confirmation", "RUN_COMPLETED", outcome="declined")
        return 0

    # Execution-safety boundary (Phase 24, ADR-0050). A human confirmation
    # authorizes *attempting* a submission; whether an attempt is actually
    # permitted is a separate, deterministic, fail-closed decision. No
    # automated executor is wired in this build (``executor_available`` is
    # a hardcoded False -- there is no executor registry, and none of the
    # three unwired applicators has a deterministic acknowledgement model
    # safe to submit through), so the boundary always refuses with an
    # explicit reason. This is exactly today's "nothing was sent" behavior,
    # now reasoned and journaled instead of implicit.
    ats_kind = resolve_ats_kind(opportunity.source_url)
    decision = execute_allowed(
        ExecutionRequest(
            source_policy=resolve_source_policy(opportunity.source, ats_kind),
            executor_available=False,
            confirmation_present=True,
            artifact_matches=True,
            prior_outcome=SubmissionOutcome.NOT_ATTEMPTED,
            journal_has_unresolved_intent=False,
        )
    )
    if decision.allowed:
        # Unreachable while ``executor_available`` is False (proven by the
        # boundary's fail-closed first check). Kept as a fail-closed guard
        # so a future edit enabling execution cannot silently fall through
        # here without also wiring the executor call this branch would need
        # -- rule 30: an irreversible action must have an explicit executor.
        raise RuntimeError(
            "execution boundary permitted execution but no executor is "
            "wired -- refusing to proceed (ADR-0050)"
        )
    _record(result.application, ats_total=ats_total)
    _emit("execution_boundary", "EXECUTION_REFUSED", outcome=decision.reason)
    print(
        f"Confirmed. Execution boundary: {decision.reason} -- no automated "
        f"executor is wired (ADR-0050); real submission remains a separate, "
        f"manual step. Nothing was actually sent."
    )
    _emit("confirmation", "RUN_COMPLETED", outcome="confirmed_not_submitted")
    return 0


async def run_apply_command(
    *,
    profile_path: Path,
    opportunity_path: Path,
    promptfoo_results_dir: Path | None = None,
    input_fn: Callable[[str], str] = input,
) -> int:
    """The real ``career-agent apply`` entry point.

    Loads a real profile and opportunity from disk, positively verifies the
    promptfoo suite has passed for the current verifier prompt version
    before constructing the real, Claude-backed verifier, then delegates to
    :func:`_apply_pipeline`.
    """
    try:
        profile = load_master_profile(profile_path)
    except (
        OSError,
        json.JSONDecodeError,
        ProfileValidationError,
        ValidationError,
    ) as exc:
        print(f"Could not load profile from {profile_path}: {exc}")
        return 1

    try:
        opportunity = _load_opportunity(opportunity_path)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"Could not load opportunity from {opportunity_path}: {exc}")
        return 1

    settings = Settings()
    try:
        claim_verifier = select_claim_verifier(settings)
    except NoLLMProviderConfiguredError as exc:
        print(str(exc))
        return 1

    results_dir = promptfoo_results_dir or Path(settings.promptfoo_results_dir)
    try:
        verify_promptfoo_results(
            claim_verifier.prompt_version,
            results_dir,
            provider_id=claim_verifier.provider_id,
        )
    except PromptfooNotValidatedError as exc:
        print(str(exc))
        return 1

    try:
        content_drafter = select_content_drafter(settings)
    except NoLLMProviderConfiguredError as exc:
        print(str(exc))
        return 1

    generator = LLMResumeGenerator(content_drafter)
    gate = LLMTruthfulnessGate(claim_verifier)
    semantic_matcher = select_semantic_matcher(settings)
    return await _apply_pipeline(
        profile,
        opportunity,
        generator,
        gate,
        input_fn=input_fn,
        artifacts_dir=Path(settings.artifacts_dir),
        ats_threshold=settings.ats_threshold,
        semantic_matcher=semantic_matcher,
        application_store=SqliteApplicationStore(Path(settings.database_path)),
        run_journal=SqliteRunJournal(Path(settings.database_path)),
        notifier=build_notifier(settings),
    )


async def run_prepare_command(
    *, profile_path: Path, opportunity_path: Path
) -> int:
    """The real ``career-agent prepare`` entry point (Phase 51, ADR-0069).

    Tailors and gates a résumé and assembles a cover letter (Phase 50's
    ``ResumeVariantEngine``, reused unmodified), then opens a real browser
    and fills as much of the live application form as it safely can --
    stopping before any Submit click. Never constructs an ``Applicator``
    and never invokes a submission method -- see
    ``ApplicationPreparationEngine`` for the structural guarantee.
    """
    try:
        profile = load_master_profile(profile_path)
    except (
        OSError,
        json.JSONDecodeError,
        ProfileValidationError,
        ValidationError,
    ) as exc:
        print(f"Could not load profile from {profile_path}: {exc}")
        return 1

    try:
        opportunity = _load_opportunity(opportunity_path)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"Could not load opportunity from {opportunity_path}: {exc}")
        return 1

    settings = Settings()
    try:
        claim_verifier = select_claim_verifier(settings)
    except NoLLMProviderConfiguredError as exc:
        print(str(exc))
        return 1

    results_dir = Path(settings.promptfoo_results_dir)
    try:
        verify_promptfoo_results(
            claim_verifier.prompt_version,
            results_dir,
            provider_id=claim_verifier.provider_id,
        )
    except PromptfooNotValidatedError as exc:
        print(str(exc))
        return 1

    try:
        content_drafter = select_content_drafter(settings)
    except NoLLMProviderConfiguredError as exc:
        print(str(exc))
        return 1

    generator = LLMResumeGenerator(content_drafter)
    gate = LLMTruthfulnessGate(claim_verifier)
    semantic_matcher = select_semantic_matcher(settings)
    pipeline = ResumeTailoringPipeline(
        generator,
        gate,
        EventBus(),
        artifacts_dir=Path(settings.artifacts_dir),
        ats_threshold=settings.ats_threshold,
        semantic_matcher=semantic_matcher,
    )
    variant_store = SqliteResumeVariantStore(Path(settings.database_path))
    variant_engine = ResumeVariantEngine(pipeline)
    category = opportunity.title
    try:
        materials = await variant_engine.build_materials(
            opportunity,
            profile,
            category=category,
            prior_variants=variant_store.by_category(category),
        )
    except MissingSummaryError as exc:
        print(f"Cannot tailor a resume: {exc}")
        return 1
    except AtsScoreBelowThresholdError as exc:
        print("The ATS score gate refused this application:")
        print(str(exc))
        return 1

    if materials.tailoring.submittable is None:
        print("The truthfulness gate rejected this draft:")
        for rejection in materials.tailoring.application.resume.truthfulness.rejections:
            print(f"  - [{rejection.category}] {rejection.detail}")
        return 1
    if materials.new_variant is not None:
        variant_store.save(materials.new_variant)

    print(f"Provider detected: {resolve_ats_kind(opportunity.source_url)}")
    print("Opening browser...")

    browser_manager = BrowserManager()
    session_manager = SessionManager(
        EncryptedSessionStore(
            Path(settings.browser_session_dir), KeyringKeyProvider()
        )
    )
    engine = ApplicationPreparationEngine(browser_manager, session_manager)
    try:
        session = await engine.build_session(
            opportunity,
            materials.tailoring.submittable,
            cover_letter=materials.cover_letter,
            resume_variant_id=(
                materials.new_variant.id if materials.new_variant else None
            ),
        )
    except FeatureUnavailableError as exc:
        print(str(exc))
        return 1
    finally:
        await browser_manager.close()

    SqliteApplicationSessionStore(Path(settings.database_path)).save(session)
    session_file = _write_application_session_handoff(
        session, Path(settings.artifacts_dir)
    )

    print(f"Application prepared. Status: {session.status}")
    if session.filled_fields:
        print(f"Filled fields: {session.filled_fields}")
    if session.uploaded_files:
        print(f"Uploaded: {session.uploaded_files}")
    if session.missing_fields:
        print(f"Needs human review: {session.missing_fields}")
    for warning in session.warnings:
        print(f"Warning: {warning}")
    print("Nothing was submitted.")
    print(
        f"Session written to: {session_file} -- review it with: "
        f"career-agent review --session {session_file}"
    )
    return 0


def _write_application_session_handoff(
    session: ApplicationSession, artifacts_dir: Path
) -> Path:
    """Write ``session`` as a JSON handoff.

    Mirrors ``discover``'s own opportunity-file handoff convention
    (ADR-0026) -- ``review`` (Phase 52) is the consumer, the same
    relationship ``apply`` has to ``discover``.
    """
    sessions_dir = artifacts_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    path = sessions_dir / f"{session.id}.json"
    path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
    return path


def _load_application_session(path: Path) -> ApplicationSession:
    """Load an :class:`ApplicationSession` from a plain JSON file.

    Raises ``OSError``/``json.JSONDecodeError``/``pydantic.ValidationError``
    on a missing, malformed, or invalid file -- mirrors ``_load_opportunity``
    exactly, including explicit ``encoding="utf-8"``.
    """
    return ApplicationSession.model_validate(
        json.loads(path.read_text(encoding="utf-8"))
    )


def run_review_command(
    *, session_path: Path, input_fn: Callable[[str], str] = input
) -> int:
    """The real ``career-agent review`` entry point (Phase 52, ADR-0070).

    Loads a prepared, unsubmitted :class:`ApplicationSession` from disk
    (written by ``prepare``), presents its deterministic summary, and
    records exactly one explicit human decision. Never touches a browser,
    never constructs an ``Applicator``, never submits anything -- see
    ``ReviewEngine`` for the structural guarantee.
    """
    try:
        session = _load_application_session(session_path)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"Could not load application session from {session_path}: {exc}")
        return 1

    settings = Settings()
    result = ReviewEngine().review(session, input_fn=input_fn)

    review = build_review_session(str(uuid.uuid4()), session, result)
    SqliteReviewSessionStore(Path(settings.database_path)).save(review)
    review_file = _write_review_session_handoff(review, Path(settings.artifacts_dir))

    print(f"Decision: {result.status}")
    if result.approved:
        print(
            "Approved. Nothing was submitted -- only `career-agent submit` "
            "can act on this, and only after several more fail-closed "
            "checks and one final explicit confirmation."
        )
        print(
            f"Review written to: {review_file} -- submit it with: "
            f"career-agent submit --review-session {review_file} "
            f"--opportunity-file <path> --profile <path>"
        )
    else:
        print("Not approved. Nothing was submitted.")
    return 0


def _write_review_session_handoff(review: ReviewSession, artifacts_dir: Path) -> Path:
    """Write ``review`` as a JSON handoff for ``career-agent submit``.

    Mirrors ``prepare``'s own ``ApplicationSession`` handoff (ADR-0069/0070)
    exactly -- same directory, same shape, same "engine returns data, the
    composition root persists/hands it off" convention.
    """
    sessions_dir = artifacts_dir / "reviews"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    path = sessions_dir / f"{review.id}.json"
    path.write_text(review.model_dump_json(indent=2), encoding="utf-8")
    return path


def _resolve_prior_submission_outcome(
    results: list[SubmissionResult],
) -> SubmissionOutcome:
    """The most recent submission result for this opportunity, as an outcome.

    ``results`` is newest-first (``SqliteSubmissionResultStore.by_opportunity``).
    Fail-closed: ``UNKNOWN``/``ABORTED`` map to ``OUTCOME_UNCERTAIN`` (never
    automatically retryable, ADR-0050) rather than being treated as safe to
    retry just because they are not a definite success.
    """
    if not results:
        return SubmissionOutcome.NOT_ATTEMPTED
    status_to_outcome: dict[str, SubmissionOutcome] = {
        "SUBMITTED": SubmissionOutcome.DEFINITELY_SUBMITTED,
        "UNKNOWN": SubmissionOutcome.OUTCOME_UNCERTAIN,
        "ABORTED": SubmissionOutcome.OUTCOME_UNCERTAIN,
        "FAILED": SubmissionOutcome.DEFINITELY_NOT_SUBMITTED,
        "REFUSED": SubmissionOutcome.NOT_ATTEMPTED,
        "CANCELLED": SubmissionOutcome.NOT_ATTEMPTED,
    }
    return status_to_outcome[results[0].status]


def _countdown_and_confirm(
    seconds: int = 5,
    *,
    sleep_fn: Callable[[float], None] = time.sleep,
    input_fn: Callable[[str], str] = input,
) -> bool:
    """Real, un-bypassable final gate: a countdown, then a blocking ENTER.

    ``input_fn`` raising ``KeyboardInterrupt`` (a real Ctrl+C) propagates
    straight out -- ``SubmissionEngine.submit`` catches it and records
    ``CANCELLED``. There is no code path here that returns ``True`` without
    ``input_fn`` actually being called and returning.
    """
    print("Submitting in")
    for remaining in range(seconds, 0, -1):
        print(f"{remaining}...")
        sleep_fn(1)
    input_fn("Press ENTER to continue (Ctrl+C to cancel): ")
    return True


async def run_submit_command(
    *,
    review_session_path: Path,
    opportunity_path: Path,
    profile_path: Path,
    confirm_fn: Callable[[], bool] | None = None,
) -> int:
    """The real ``career-agent submit`` entry point (Phase 53, ADR-0071).

    The only command in this codebase that can click a real Submit button
    -- and only after every precondition in ``domain/execution.py``'s
    fail-closed boundary holds, plus one final, explicit, un-bypassable
    human confirmation (:func:`_countdown_and_confirm`). Re-tailors fresh
    (the same way ``prepare`` originally did) so the résumé actually
    submitted is verified byte-for-byte against what was stored at
    prepare-time -- a profile edit between ``prepare`` and ``submit``
    fails the artifact-integrity check rather than silently submitting
    different content than what was reviewed.
    """
    try:
        review = ReviewSession.model_validate(
            json.loads(review_session_path.read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"Could not load review session from {review_session_path}: {exc}")
        return 1

    try:
        profile = load_master_profile(profile_path)
    except (
        OSError,
        json.JSONDecodeError,
        ProfileValidationError,
        ValidationError,
    ) as exc:
        print(f"Could not load profile from {profile_path}: {exc}")
        return 1

    try:
        opportunity = _load_opportunity(opportunity_path)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"Could not load opportunity from {opportunity_path}: {exc}")
        return 1

    settings = Settings()
    application_sessions = SqliteApplicationSessionStore(
        Path(settings.database_path)
    ).by_opportunity(opportunity.id)
    application_session = next(
        (s for s in application_sessions if s.id == review.application_session_id),
        None,
    )
    if application_session is None:
        print(
            f"No ApplicationSession {review.application_session_id!r} found for "
            f"opportunity {opportunity.id!r} -- run `career-agent prepare` again."
        )
        return 1

    variant_store = SqliteResumeVariantStore(Path(settings.database_path))
    stored_variant = (
        variant_store.get(application_session.resume_variant_id)
        if application_session.resume_variant_id
        else None
    )

    try:
        claim_verifier = select_claim_verifier(settings)
    except NoLLMProviderConfiguredError as exc:
        print(str(exc))
        return 1
    results_dir = Path(settings.promptfoo_results_dir)
    try:
        verify_promptfoo_results(
            claim_verifier.prompt_version,
            results_dir,
            provider_id=claim_verifier.provider_id,
        )
    except PromptfooNotValidatedError as exc:
        print(str(exc))
        return 1
    try:
        content_drafter = select_content_drafter(settings)
    except NoLLMProviderConfiguredError as exc:
        print(str(exc))
        return 1

    generator = LLMResumeGenerator(content_drafter)
    gate = LLMTruthfulnessGate(claim_verifier)
    semantic_matcher = select_semantic_matcher(settings)
    pipeline = ResumeTailoringPipeline(
        generator,
        gate,
        EventBus(),
        artifacts_dir=Path(settings.artifacts_dir),
        ats_threshold=settings.ats_threshold,
        semantic_matcher=semantic_matcher,
    )
    variant_engine = ResumeVariantEngine(pipeline)
    category = opportunity.title
    try:
        materials = await variant_engine.build_materials(
            opportunity,
            profile,
            category=category,
            prior_variants=variant_store.by_category(category),
        )
    except MissingSummaryError as exc:
        print(f"Cannot tailor a resume: {exc}")
        return 1
    except AtsScoreBelowThresholdError as exc:
        print("The ATS score gate refused this application:")
        print(str(exc))
        return 1

    if materials.tailoring.submittable is None:
        print(
            "The truthfulness gate rejected the freshly re-tailored draft -- "
            "refusing to submit."
        )
        return 1

    submission_store = SqliteSubmissionResultStore(Path(settings.database_path))
    prior_outcome = _resolve_prior_submission_outcome(
        submission_store.by_opportunity(opportunity.id)
    )

    session_store = EncryptedSessionStore(
        Path(settings.browser_session_dir), KeyringKeyProvider()
    )
    engine = SubmissionEngine(session_store)
    try:
        result = await engine.submit(
            opportunity,
            materials.tailoring.submittable,
            review,
            application_session,
            stored_variant.content if stored_variant is not None else None,
            prior_outcome=prior_outcome,
            confirm_fn=confirm_fn or _countdown_and_confirm,
        )
    except FeatureUnavailableError as exc:
        print(str(exc))
        return 1

    submission_store.save(result)

    print(f"Status: {result.status}")
    if result.submitted:
        print("Submitted. Nothing further is automated.")
    else:
        print(f"Not submitted. Reason: {result.refusal_reason or result.status}")
    for warning in result.warnings:
        print(f"Warning: {warning}")
    print("Recorded.")
    return 0 if result.status in ("SUBMITTED", "CANCELLED") else 1


#: Printed once per ranked-summary run, only if some displayed opportunity's
#: evidence-quality signal is below 1.0 (ADR-0046) -- explicit, so a heuristic
#: linear-shrinkage interval (domain/pareto.py, ADR-0045) is never mistaken
#: for a calibrated statistical confidence, which this project has no
#: historical accuracy data to actually calibrate.
_EVIDENCE_QUALITY_CAVEAT = (
    "Note: [Pareto-optimal]/[dominated by] reflects a heuristic evidence-"
    "quality band derived from each source's extraction confidence "
    "(ADR-0012/0045), not a calibrated statistical probability."
)


def _objective_point(
    opportunity: Opportunity, decision: DecisionScore
) -> ObjectivePoint:
    """Adapt Decide's scalar-ranking output into Pareto's generic input.

    The only place ``DecisionScore``'s four named fields and
    ``Opportunity.provenance.extraction_confidence`` meet
    ``domain.pareto.ObjectivePoint`` -- deliberately here, not inside
    either module, since neither should know about the other's type
    (ADR-0045's decoupling, ADR-0046's integration policy).
    """
    return ObjectivePoint(
        id=opportunity.id,
        objectives={
            "profile_match": decision.profile_match,
            "source_reliability": decision.source_reliability,
            "freshness": decision.freshness,
            "salary_transparency": decision.salary_transparency,
        },
        confidence=opportunity.provenance.extraction_confidence,
    )


def _dominance_annotations(
    included: list[tuple[Opportunity, DecisionScore]],
) -> dict[str, str]:
    """Per-opportunity Pareto-frontier annotation (ADR-0046), advisory only.

    Computed over the **full** ``included`` set, never a truncated display
    slice -- a lower-ranked opportunity outside a printed top-10 could
    still be the one that dominates a displayed one, and silently ignoring
    it would misreport dominance.
    """
    if not included:
        return {}
    points = [_objective_point(o, d) for o, d in included]
    frontier = analyze_frontier(points)
    by_id = {e.id: e for e in frontier.explanations}
    annotations: dict[str, str] = {}
    for opportunity, _decision in included:
        explanation = by_id[opportunity.id]
        if explanation.pareto_optimal:
            annotations[opportunity.id] = " [Pareto-optimal]"
        else:
            annotations[opportunity.id] = (
                f" [dominated by: {', '.join(explanation.dominated_by)}]"
            )
    return annotations


def _sensitivity_summary(
    included: list[tuple[Opportunity, DecisionScore]],
) -> list[str]:
    """The bounded, top-1-vs-runner-up sensitivity summary (ADR-0046).

    Deliberately not a full O(n) (let alone O(n^2)) dump of every adjacent
    pair -- the single most decision-relevant question a ranked list can
    answer is "how fragile is my top pick", which is exactly the #1-vs-#2
    comparison. Reuses :func:`rank_flip_points` unmodified and filters its
    output to that one pair rather than relying on its internal ordering.
    """
    if len(included) < 2:
        return []
    decisions = [decision for _opportunity, decision in included]
    top_pair_flips: list[RankFlipPoint] = [
        flip
        for flip in rank_flip_points(decisions)
        if flip.higher_id == decisions[0].opportunity_id
        and flip.lower_id == decisions[1].opportunity_id
    ]
    if not top_pair_flips:
        return []
    lines = [
        f"Sensitivity (#1 vs #2, ADR-0045/0046): current margin "
        f"{top_pair_flips[0].current_margin:.1f}"
    ]
    reachable = [flip for flip in top_pair_flips if flip.breakeven_delta is not None]
    if not reachable:
        lines.append(
            "  no single weight's valid [0,1] range could flip this order."
        )
    else:
        closest = min(reachable, key=lambda flip: abs(flip.breakeven_delta))  # type: ignore[arg-type]
        lines.append(
            f"  most sensitive to {closest.weight_name!r}: current weight "
            f"{closest.current_weight:.2f}, flips at delta "
            f"{closest.breakeven_delta:+.3f}; {len(reachable)} of "
            f"{len(top_pair_flips)} weights could flip this order alone."
        )
    return lines


async def run_discover_command(
    sources: list[tuple[str, object]],
    repo: object,
    *,
    since: datetime,
    out_dir: Path,
    profile: MasterProfile | None = None,
    scorer: object | None = None,
) -> int:
    """Run every configured source, dedup via ``repo``, write handoff files.

    Injectable (sources + repo) for tests; ``build_discovery_sources``
    wires the real ones from Settings. Each genuinely-new opportunity is
    written to ``out_dir`` as the exact JSON file format ``apply
    --opportunity-file`` already consumes (ADR-0026's handoff, produced
    for real for the first time). A failing source is reported and
    skipped -- one broken API must not sink the whole run -- but is never
    silently absent from the summary.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    new_count = 0
    new_opportunities = []
    for name, source in sources:
        try:
            found = await source.fetch(since)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001 -- per-source isolation
            print(f"[{name}] FAILED: {exc}")
            continue
        fresh = 0
        for opportunity in found:
            if await repo.add(opportunity):  # type: ignore[attr-defined]
                fresh += 1
                new_count += 1
                new_opportunities.append(opportunity)
                handoff = out_dir / f"{opportunity.id}.json"
                # Explicit encoding="utf-8": model_dump_json() (unlike
                # stdlib json.dumps' ensure_ascii=True default) writes real
                # Unicode characters verbatim -- a title/description with
                # an emoji or non-Latin script would otherwise hit the
                # platform's default encoding (cp1252 on Windows), which
                # cannot represent it at all.
                handoff.write_text(
                    opportunity.model_dump_json(indent=2), encoding="utf-8"
                )
        print(f"[{name}] {len(found)} fetched, {fresh} new")
    print(f"{new_count} new opportunit{'y' if new_count == 1 else 'ies'} -> {out_dir}")
    if profile is not None and scorer is not None and new_opportunities:
        included, excluded = scorer.rank(new_opportunities, profile)  # type: ignore[attr-defined]
        print("Ranked (Decide layer, ADR-0038):")
        # Advisory decision intelligence (ADR-0045/0046): computed over the
        # full `included` set, never just the printed top-10 -- never
        # changes which opportunities are included/excluded/ordered.
        dominance = _dominance_annotations(included)
        for opportunity, decision in included[:10]:
            print(
                f"  {decision.total:5.1f}  {opportunity.canonical_company}: "
                f"{opportunity.title}  ({out_dir / (opportunity.id + '.json')})"
                f"{dominance.get(opportunity.id, '')}"
            )
        for decision in excluded:
            print(
                f"  EXCLUDED {decision.opportunity_id}: "
                f"{'; '.join(decision.exclude_reasons)}"
            )
        if any(
            opportunity.provenance.extraction_confidence < 1.0
            for opportunity, _decision in included
        ):
            print(_EVIDENCE_QUALITY_CAVEAT)
        for line in _sensitivity_summary(included):
            print(line)
    return 0


def build_discovery_sources(
    settings: Settings, preferences: JobPreferences | None = None
) -> list[tuple[str, object]]:
    """Wire every source whose config is present (composition root).

    Phase 46 (ADR-0064): when ``preferences`` is given and
    :func:`~career_agent.domain.job_preferences.generate_search_queries`
    yields at least one query, each keyword-capable source (Adzuna/Reed/
    USAJobs/Jooble) is instantiated once *per generated query* instead of
    once with the static ``settings.discovery_keywords`` default --
    "Software Engineer Remote India", "Backend Developer India", ... each
    becomes its own discovery pass, fanned out across the same
    already-existing source classes rather than a new discovery mechanism.
    Falls back to exactly the prior single-keyword behavior when
    ``preferences`` is ``None`` or generates no queries (e.g. no titles
    configured yet) -- current discovery is extended, never removed.
    """
    from career_agent.integrations.http import HttpxClient
    from career_agent.plugins.sources.job_boards import (
        AdzunaSource,
        ArbeitnowSource,
        JoobleSource,
        ReedSource,
        RemoteOkSource,
        RemotiveSource,
        TheMuseSource,
        UsaJobsSource,
    )

    client = HttpxClient()
    generated_queries = generate_search_queries(preferences) if preferences else []
    keyword_queries = generated_queries or [settings.discovery_keywords]

    def _label(base: str, query: str) -> str:
        return base if len(keyword_queries) == 1 else f"{base}[{query}]"

    sources: list[tuple[str, object]] = []
    if settings.adzuna_app_id and settings.adzuna_app_key:
        countries = [
            country.strip()
            for country in settings.adzuna_countries.split(",")
            if country.strip()
        ]
        for query in keyword_queries:
            sources.append(
                (
                    _label("adzuna", query),
                    AdzunaSource(
                        app_id=settings.adzuna_app_id,
                        app_key=settings.adzuna_app_key,
                        countries=countries,
                        keywords=query,
                        client=client,
                    ),
                )
            )
    if settings.reed_api_key:
        for query in keyword_queries:
            sources.append(
                (
                    _label("reed", query),
                    ReedSource(
                        api_key=settings.reed_api_key, keywords=query, client=client
                    ),
                )
            )
    if settings.usajobs_api_key and settings.usajobs_user_agent:
        for query in keyword_queries:
            sources.append(
                (
                    _label("usajobs", query),
                    UsaJobsSource(
                        api_key=settings.usajobs_api_key,
                        user_agent=settings.usajobs_user_agent,
                        keywords=query,
                        client=client,
                    ),
                )
            )
    if settings.jooble_api_key:
        for query in keyword_queries:
            sources.append(
                (
                    _label("jooble", query),
                    JoobleSource(
                        api_key=settings.jooble_api_key,
                        keywords=query,
                        location=settings.jooble_location,
                        client=client,
                    ),
                )
            )
    if settings.arbeitnow_enabled:
        sources.append(("arbeitnow", ArbeitnowSource(client=client)))
    if settings.themuse_enabled:
        sources.append(("themuse", TheMuseSource(client=client)))
    if settings.remotive_enabled:
        sources.append(("remotive", RemotiveSource(client=client)))
    if settings.remoteok_enabled:
        sources.append(("remoteok", RemoteOkSource(client=client)))
    return sources


def _load_preferences_if_present(settings: Settings) -> JobPreferences | None:
    """Load Job Search Preferences if the file exists; ``None`` if absent.

    Absence is normal (no wizard has been run yet) and falls back to
    ``build_discovery_sources``'s prior static-keyword behavior. Malformed
    *existing* content is a real error, not silently ignored -- a user's
    configured preferences must not silently stop applying with no
    indication why -- so it propagates for the caller to catch with the
    same clean-message contract every other loader in this module follows.
    """
    path = Path(settings.job_preferences_path)
    if not path.exists():
        return None
    return load_job_preferences(path)


def _build_decide_scorer(settings: Settings) -> object:
    """Build the one ``DeterministicDecideScorer`` shared by discover/auto.

    So the two commands can never silently diverge on which opportunities
    Decide excludes.
    """
    from career_agent.agents.planner.decide import (
        DecideFilters,
        DeterministicDecideScorer,
    )

    return DeterministicDecideScorer(
        DecideFilters(
            blacklist_companies=[
                c.strip()
                for c in settings.decide_blacklist_companies.split(",")
                if c.strip()
            ],
            allowed_locations=[
                c.strip()
                for c in settings.decide_allowed_locations.split(",")
                if c.strip()
            ],
            remote_only=settings.decide_remote_only,
        )
    )


_LEGAL_ANSWERS = {"yes": True, "no": False, "skip": None}


def run_capture_legal_status_command(
    profile_path: Path, *, input_fn: Callable[[str], str] = input
) -> int:
    """The first MasterProfile writer: explicit LegalStatusSection capture.

    No defaults, no inference (ADR-0032's deferred capture flow, built in
    Phase 13/ADR-0037): only the exact answers "yes"/"no"/"skip" are
    accepted; anything else -- including empty input -- is treated as
    "skip", which leaves the fact ``None`` ("never asked"). Unrecognized
    input can never become an answer, in either polarity.
    """
    try:
        profile = load_master_profile(profile_path)
    except (
        OSError,
        json.JSONDecodeError,
        ProfileValidationError,
        ValidationError,
    ) as exc:
        print(f"Could not load profile from {profile_path}: {exc}")
        return 1

    def ask(question: str, current: bool | None) -> bool | None:
        shown = "not yet captured" if current is None else ("yes" if current else "no")
        answer = input_fn(f"{question} (currently: {shown}) [yes/no/skip]: ")
        normalized = answer.strip().lower()
        if normalized not in _LEGAL_ANSWERS:
            print(f"Unrecognized answer {answer!r} -- skipping (stays as-is).")
            return current
        result = _LEGAL_ANSWERS[normalized]
        return current if result is None and normalized == "skip" else result

    current = profile.legal_status
    updated = LegalStatusSection(
        work_authorized_us=ask(
            "Are you legally authorized to work in the United States?",
            current.work_authorized_us,
        ),
        requires_sponsorship=ask(
            "Will you now or in the future require sponsorship?",
            current.requires_sponsorship,
        ),
    )
    save_legal_status(profile_path, updated)
    print(
        f"Saved legal status to {profile_path} "
        f"(profile version will change on next load)."
    )
    return 0


def _ask_list(
    input_fn: Callable[[str], str], prompt: str, current: list[str]
) -> list[str]:
    """Comma-separated list prompt; blank input keeps the current value."""
    shown = ", ".join(current) if current else "none"
    answer = input_fn(f"{prompt} (currently: {shown}; comma-separated): ").strip()
    if not answer:
        return current
    return [item.strip() for item in answer.split(",") if item.strip()]


def _ask_optional_str(
    input_fn: Callable[[str], str], prompt: str, current: str | None
) -> str | None:
    """Free-text prompt; blank keeps current, literal '-' clears it to None."""
    shown = current if current is not None else "not set"
    answer = input_fn(f"{prompt} (currently: {shown}): ").strip()
    if not answer:
        return current
    if answer == "-":
        return None
    return answer


def _ask_optional_bool(
    input_fn: Callable[[str], str], prompt: str, current: bool | None
) -> bool | None:
    """yes/no/unset prompt; blank keeps current.

    Same discipline as ``run_capture_legal_status_command``: unrecognized
    input never becomes an answer, in either polarity.
    """
    shown = "not set" if current is None else ("yes" if current else "no")
    answer = input_fn(f"{prompt} (currently: {shown}) [yes/no/unset]: ").strip().lower()
    if not answer:
        return current
    if answer == "yes":
        return True
    if answer == "no":
        return False
    if answer == "unset":
        return None
    print(f"Unrecognized answer {answer!r} -- keeping current value.")
    return current


def _ask_bool(input_fn: Callable[[str], str], prompt: str, current: bool) -> bool:
    """yes/no prompt with a required default; blank keeps current."""
    shown = "yes" if current else "no"
    answer = input_fn(f"{prompt} (currently: {shown}) [yes/no]: ").strip().lower()
    if not answer:
        return current
    if answer in _YES:
        return True
    if answer in {"n", "no"}:
        return False
    print(f"Unrecognized answer {answer!r} -- keeping current value.")
    return current


def _ask_optional_int(
    input_fn: Callable[[str], str], prompt: str, current: int | None
) -> int | None:
    shown = current if current is not None else "not set"
    answer = input_fn(f"{prompt} (currently: {shown}): ").strip()
    if not answer:
        return current
    if answer == "-":
        return None
    try:
        return int(answer)
    except ValueError:
        print(f"{answer!r} is not a whole number -- keeping current value.")
        return current


def _ask_optional_float(
    input_fn: Callable[[str], str], prompt: str, current: float | None
) -> float | None:
    shown = current if current is not None else "not set"
    answer = input_fn(f"{prompt} (currently: {shown}): ").strip()
    if not answer:
        return current
    if answer == "-":
        return None
    try:
        return float(answer)
    except ValueError:
        print(f"{answer!r} is not a number -- keeping current value.")
        return current


def run_preferences_command(
    *,
    path: Path | None = None,
    settings: Settings | None = None,
    input_fn: Callable[[str], str] = input,
) -> int:
    """The ``career-agent preferences`` command.

    An interactive Job Search Preferences wizard (Phase 46, ADR-0064) --
    a separate file from the master profile, by design; see ADR-0064.
    Loads the existing preferences (or a fresh default set if none exist
    yet), asks about every field, and saves. Every prompt shows the current
    value and keeps it on a blank answer, so re-running this command to
    tweak one field never requires re-entering everything else. Never
    touches ``profile.json`` and makes no network/LLM call.
    """
    settings = settings or Settings()
    prefs_path = path or Path(settings.job_preferences_path)

    if prefs_path.exists():
        try:
            current = load_job_preferences(prefs_path)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            print(f"Could not load preferences from {prefs_path}: {exc}")
            return 1
    else:
        current = JobPreferences()

    print("career-agent preferences\n=========================\n")

    try:
        updated = _build_preferences_from_wizard(input_fn, current)
    except ValidationError as exc:
        print(f"\nInvalid input -- nothing was saved: {exc}")
        return 1

    save_job_preferences(prefs_path, updated)
    print(f"\nSaved job search preferences to {prefs_path}.")
    queries = generate_search_queries(updated)
    if queries:
        print("These preferences would generate discovery queries such as:")
        for query in queries[:5]:
            print(f"  - {query}")
    return 0


def _build_preferences_from_wizard(
    input_fn: Callable[[str], str], current: JobPreferences
) -> JobPreferences:
    """The prompt sequence.

    Split out so ``run_preferences_command`` can wrap it in one try/except
    for a single, clean validation-error message instead of an uncaught
    traceback on bad input (e.g. an unrecognized seniority value).
    """
    return JobPreferences(
        preferred_titles=_ask_list(
            input_fn, "What roles are you looking for?", current.preferred_titles
        ),
        alternative_titles=_ask_list(
            input_fn, "Alternative/related titles?", current.alternative_titles
        ),
        seniority=_ask_optional_str(  # type: ignore[arg-type]
            input_fn,
            "Seniority (intern/entry/junior/mid/senior/lead/principal/staff)",
            current.seniority,
        ),
        experience_years_min=_ask_optional_int(
            input_fn, "Minimum years of experience?", current.experience_years_min
        ),
        experience_years_max=_ask_optional_int(
            input_fn, "Maximum years of experience?", current.experience_years_max
        ),
        employment_types=_ask_list(  # type: ignore[arg-type]
            input_fn,
            "Employment types (full_time/part_time/contract/internship/temporary)",
            list(current.employment_types),
        ),
        work_mode=_ask_list(  # type: ignore[arg-type]
            input_fn, "Work mode (remote/hybrid/onsite)", list(current.work_mode)
        ),
        countries=_ask_list(input_fn, "Countries?", current.countries),
        states=_ask_list(input_fn, "States?", current.states),
        cities=_ask_list(input_fn, "Cities?", current.cities),
        salary_min=_ask_optional_float(
            input_fn, "Minimum salary?", current.salary_min
        ),
        salary_max=_ask_optional_float(
            input_fn, "Maximum salary?", current.salary_max
        ),
        salary_currency=_ask_optional_str(
            input_fn, "Salary currency/unit (e.g. USD, LPA)?", current.salary_currency
        ),
        preferred_companies=_ask_list(
            input_fn, "Preferred companies?", current.preferred_companies
        ),
        blacklisted_companies=_ask_list(
            input_fn, "Blacklisted companies?", current.blacklisted_companies
        ),
        industries=_ask_list(input_fn, "Industries?", current.industries),
        visa_sponsorship_required=_ask_optional_bool(
            input_fn,
            "Do you require visa sponsorship?",
            current.visa_sponsorship_required,
        ),
        work_authorization=_ask_optional_str(
            input_fn, "Work authorization (free text)?", current.work_authorization
        ),
        preferred_technologies=_ask_list(
            input_fn, "Preferred technologies/skills?", current.preferred_technologies
        ),
        keywords_include=_ask_list(
            input_fn, "Keywords to include?", current.keywords_include
        ),
        keywords_exclude=_ask_list(
            input_fn, "Keywords to exclude?", current.keywords_exclude
        ),
        max_applications_per_day=_ask_optional_int(
            input_fn,
            "Maximum applications per day (stored only -- not yet enforced)?",
            current.max_applications_per_day,
        ),
        require_human_confirmation=_ask_bool(
            input_fn,
            "Require human confirmation? (informational -- the real "
            "confirmation boundary is always required regardless)",
            current.require_human_confirmation,
        ),
        auto_tailor_resume=_ask_bool(
            input_fn,
            "Auto-tailor resume? (stored only -- not yet wired)",
            current.auto_tailor_resume,
        ),
        auto_generate_cover_letter=_ask_bool(
            input_fn,
            "Auto-generate cover letter? (stored only -- not yet implemented)",
            current.auto_generate_cover_letter,
        ),
        preferred_ats_providers=_ask_list(  # type: ignore[arg-type]
            input_fn,
            "Preferred ATS providers (greenhouse/lever/ashby/workday)?",
            list(current.preferred_ats_providers),
        ),
        time_zone=_ask_optional_str(
            input_fn, "Time zone (IANA name, e.g. Asia/Kolkata)?", current.time_zone
        ),
    )


def run_verify_promptfoo_command(
    provider_id: str, results_dir: Path | None = None
) -> int:
    """Check a real local promptfoo results artifact against the exact production gate.

    No API key, no network call, and no side effect beyond printing a
    verdict. This calls the *same*
    :func:`~career_agent.llm.promptfoo_gate.verify_promptfoo_results` that
    ``apply``
    calls before constructing a real ``ClaimVerifier`` -- not a
    reimplementation of its logic -- against the current
    ``TRUTHFULNESS_GATE_PROMPT_VERSION`` and the requested provider, so a
    "pass" printed here means ``apply`` would also pass this gate for that
    provider right now. It intentionally does not go through
    ``select_claim_verifier`` (which requires that provider's API key to be
    configured just to read its ``provider_id``/``prompt_version``
    attributes) -- both are fixed per provider, so this checks whichever
    ``--provider`` was asked for directly, independent of what is currently
    configured in the environment.
    """
    try:
        verify_promptfoo_results(
            TRUTHFULNESS_GATE_PROMPT_VERSION,
            results_dir or Path(Settings().promptfoo_results_dir),
            provider_id=provider_id,
        )
    except PromptfooNotValidatedError as exc:
        print(str(exc))
        return 1
    print(
        f"PASS: promptfoo results for prompt version "
        f"{TRUTHFULNESS_GATE_PROMPT_VERSION!r} / provider {provider_id!r} "
        f"prove a complete, clean run. This is a structural/content check "
        f"only -- see promptfoo_gate.py's module docstring for what it does "
        f"and does not prove about authenticity."
    )
    return 0


def run_diagnose_promptfoo_drift_command(
    provider_id: str, results_dir: Path | None = None
) -> int:
    """Report why the prompt-content drift check would accept or reject an artifact.

    Never exposes résumé/claim content or secrets. Reuses the exact same
    parsing (``_recorded_prompt_raw``) and
    normalization (``_canonicalize_prompt_text``) the real
    ``verify_promptfoo_results`` check uses -- this can never disagree
    with what that check actually does, because it calls the same code,
    not a reimplementation of it.
    """
    print(
        diagnose_prompt_drift(
            TRUTHFULNESS_GATE_PROMPT_VERSION,
            results_dir or Path(Settings().promptfoo_results_dir),
            provider_id=provider_id,
        )
    )
    return 0


def run_export_command(database_path: Path, xlsx_path: Path) -> int:
    """Export the application audit trail to a formatted Excel workbook."""
    store = SqliteApplicationStore(database_path)
    rows = store.all_rows()
    written = export_applications(rows, xlsx_path)
    print(f"Wrote {len(rows)} application(s) to {written}")
    return 0



_OUTCOME_KINDS = {"viewed", "response", "interview", "offer", "rejection"}


def run_outcome_command(
    database_path: Path,
    application_id: str,
    kind: str,
    stage: str | None,
) -> int:
    """Record one real-world outcome for a recorded application (ADR-0039).

    Refuses an unknown application id (a typo must not create an orphan
    outcome row) and an unknown kind -- typed inputs only, no free text
    becoming data.
    """
    if kind not in _OUTCOME_KINDS:
        print(f"Unknown outcome kind {kind!r}; expected one of "
              f"{sorted(_OUTCOME_KINDS)}")
        return 1
    store = SqliteApplicationStore(database_path)
    known_ids = {str(row["id"]) for row in store.all_rows()}
    if application_id not in known_ids:
        print(
            f"No recorded application with id {application_id!r} -- outcomes "
            f"attach only to real recorded attempts."
        )
        return 1
    store.record_outcome(application_id, kind, stage)
    print(f"Recorded {kind}" + (f" (stage: {stage})" if stage else "") +
          f" for {application_id}")
    return 0


def run_report_command(database_path: Path) -> int:
    """Print the per-variant raw-counts funnel report (ADR-0039)."""
    from career_agent.agents.learning.funnel import (
        build_funnel_report,
        render_funnel_report,
    )

    store = SqliteApplicationStore(database_path)
    report = build_funnel_report(store.all_rows(), store.outcome_rows())
    print(render_funnel_report(report))
    return 0



def build_notifier(settings: Settings) -> object | None:
    """Telegram when configured, else ntfy, else None (composition root)."""
    from career_agent.integrations.http import HttpxClient
    from career_agent.integrations.notifications import (
        NtfyNotifier,
        TelegramNotifier,
    )

    if settings.telegram_bot_token and settings.telegram_chat_id:
        return TelegramNotifier(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
            client=HttpxClient(),
        )
    if settings.ntfy_topic:
        return NtfyNotifier(topic=settings.ntfy_topic, client=HttpxClient())
    return None



async def run_auto_command(
    sources: list[tuple[str, object]],
    repo: object,
    profile: MasterProfile,
    scorer: object,
    generator: ResumeGenerator,
    gate: TruthfulnessGate,
    *,
    since: datetime,
    out_dir: Path,
    top_n: int = 3,
    ats_threshold: float | None = None,
    artifacts_dir: Path | None = None,
    application_store: SqliteApplicationStore | None = None,
    run_journal: SqliteRunJournal | None = None,
    notifier: object | None = None,
) -> int:
    """One scheduling-safe pass: discover -> rank -> tailor+gate -> notify.

    **Structurally cannot confirm or submit** (Phase 17, ADR-0041): this
    function takes no input function, constructs no ``HumanConfirmation``,
    and calls no ``Applicator`` -- there is no code path from here to a
    submission, which is what makes it safe to run from cron. Both gates
    (truthfulness, ATS) run in full on every prepared application; every
    outcome ends in a notification and a handoff file awaiting the
    human's own ``career-agent apply`` confirmation.

    ``application_store`` (Phase 22, ADR-0048), when given, also skips any
    opportunity that already has a recorded non-``"rejected"`` application
    attempt -- an unattended cron run must never re-tailor (and risk a
    human later re-confirming a duplicate submission for) an opportunity
    it already prepared or submitted in a previous run.

    ``run_journal`` (Phase 23, ADR-0049), when given, records this whole
    pass under one fresh ``run_id`` -- one event per opportunity outcome
    (skipped/failed/rejected/prepared), plus a final ``RUN_COMPLETED`` --
    purely for reconstruction/auditability; behavior is unchanged either way.
    """
    run_id = str(uuid.uuid4())

    def _emit(
        stage: str,
        event_type: str,
        *,
        outcome: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        if run_journal is not None:
            run_journal.append(
                run_id, stage, event_type, outcome=outcome, metadata=metadata
            )

    _emit("run", "RUN_STARTED")
    await run_discover_command(
        sources, repo, since=since, out_dir=out_dir
    )
    handoffs = sorted(out_dir.glob("*.json"))
    opportunities = [
        Opportunity.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in handoffs
    ]
    _emit(
        "discovery",
        "DISCOVERY_COMPLETED",
        metadata={"opportunity_count": str(len(opportunities))},
    )
    included, _excluded = scorer.rank(opportunities, profile)  # type: ignore[attr-defined]
    prepared = 0
    for opportunity, decision in included[:top_n]:
        if application_store is not None:
            prior_status = application_store.prior_attempt_status(opportunity.id)
            if prior_status is not None:
                print(
                    f"[{opportunity.id}] skipped: already has a recorded "
                    f"application attempt (status={prior_status!r}) -- "
                    f"never re-attempted automatically (Phase 22, ADR-0048)"
                )
                _emit(
                    "idempotency_guard",
                    "OPPORTUNITY_SKIPPED",
                    outcome=prior_status,
                    metadata={"opportunity_id": opportunity.id},
                )
                continue
        bus = EventBus()
        pipeline = ResumeTailoringPipeline(
            generator,
            gate,
            bus,
            artifacts_dir=artifacts_dir,
            ats_threshold=ats_threshold,
        )
        try:
            result = await pipeline.run(opportunity, profile)
        except (MissingSummaryError, AtsScoreBelowThresholdError) as exc:
            print(f"[{opportunity.id}] not prepared: {exc}")
            _emit(
                "tailoring",
                "OPPORTUNITY_NOT_PREPARED",
                outcome="tailoring_failed",
                metadata={"opportunity_id": opportunity.id},
            )
            continue
        if application_store is not None:
            application_store.record(
                result.application,
                company=opportunity.canonical_company,
                source=opportunity.source,
                ats_total=result.ats_report.total if result.ats_report else None,
            )
        if result.submittable is None:
            print(f"[{opportunity.id}] truthfulness gate rejected the draft")
            _emit(
                "truthfulness",
                "OPPORTUNITY_NOT_PREPARED",
                outcome="rejected",
                metadata={"opportunity_id": opportunity.id},
            )
            continue
        prepared += 1
        _emit(
            "application",
            "APPLICATION_PREPARED",
            metadata={"opportunity_id": opportunity.id},
        )
        message = (
            f"{opportunity.canonical_company}: {opportunity.title} "
            f"(rank {decision.total:.1f}) is tailored, gated, and waiting "
            f"for YOUR confirmation: career-agent apply --opportunity-file "
            f"{out_dir / (opportunity.id + '.json')}"
        )
        print(message)
        if notifier is not None:
            try:
                await notifier.notify("Application prepared", message)  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001 -- notify, never gate
                print(f"(notification not delivered: {exc})")
    print(f"{prepared} application(s) prepared; none submitted -- submission "
          f"is always your explicit act.")
    _emit("run", "RUN_COMPLETED", outcome=f"prepared={prepared}")
    return 0


async def run_auto_cli_command(
    *,
    profile_path: Path,
    since_days: int,
    out_dir: Path,
    top_n: int,
    promptfoo_results_dir: Path | None = None,
) -> int:
    """The real ``career-agent auto`` composition root (Phase 17, ADR-0041).

    Was, until now, only reachable by calling :func:`run_auto_command`
    directly in a test -- ``main()`` never registered an ``auto``
    subparser at all, so the roadmap's own "Done when: ``career-agent
    auto``" criterion for this phase was not actually satisfiable by a
    real user. Mirrors ``apply``'s gate-then-construct ordering exactly:
    select the real (Groq/Anthropic) ``ClaimVerifier``, positively verify
    its promptfoo results before it's ever used, then select the content
    drafter -- all before ``run_auto_command`` (whose own body is
    structurally incapable of confirming or submitting) ever runs.

    ``promptfoo_results_dir`` mirrors ``run_apply_command``'s existing
    parameter of the same name -- defaults to ``settings.
    promptfoo_results_dir`` (real production behavior, unchanged), but lets
    a caller (a test) point the gate at an isolated directory instead of
    the real, machine-local ``promptfoo/results/``.
    Omitting this was a real gap: unlike ``run_apply_command``, this
    function offered no way for a test to prove "no valid artifact" is
    what it's actually testing, rather than depending on the ambient
    absence of the developer's own real, gitignored validation artifact
    at the repository-relative default path -- which is exactly what let
    a test asserting "blocks even with a valid API key" instead reach a
    real Groq HTTP call on a machine that legitimately has a real, passing
    ``promptfoo/results/truthfulness-gate-v2--groq.json`` on disk.
    """
    settings = Settings()
    since = datetime.now(UTC) - timedelta(days=since_days)
    profile = load_master_profile(profile_path)
    try:
        preferences = _load_preferences_if_present(settings)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(
            f"Could not load job preferences from "
            f"{settings.job_preferences_path}: {exc}"
        )
        return 1
    scorer = _build_decide_scorer(settings)
    try:
        claim_verifier = select_claim_verifier(settings)
    except NoLLMProviderConfiguredError as exc:
        print(str(exc))
        return 1
    results_dir = promptfoo_results_dir or Path(settings.promptfoo_results_dir)
    try:
        verify_promptfoo_results(
            claim_verifier.prompt_version,
            results_dir,
            provider_id=claim_verifier.provider_id,
        )
    except PromptfooNotValidatedError as exc:
        print(str(exc))
        return 1
    try:
        content_drafter = select_content_drafter(settings)
    except NoLLMProviderConfiguredError as exc:
        print(str(exc))
        return 1
    generator = LLMResumeGenerator(content_drafter)
    gate = LLMTruthfulnessGate(claim_verifier)
    return await run_auto_command(
        build_discovery_sources(settings, preferences),
        SqliteOpportunityRepository(Path(settings.database_path)),
        profile,
        scorer,
        generator,
        gate,
        since=since,
        out_dir=out_dir,
        top_n=top_n,
        ats_threshold=settings.ats_threshold,
        artifacts_dir=Path(settings.artifacts_dir),
        application_store=SqliteApplicationStore(Path(settings.database_path)),
        run_journal=SqliteRunJournal(Path(settings.database_path)),
        notifier=build_notifier(settings),
    )


def run_serve_command(*, host: str, port: int) -> int:
    """The ``career-agent serve`` command: run the read-only dashboard API.

    Imports uvicorn/FastAPI lazily (same pattern as the LLM providers
    imported inside command functions above) so the ``web`` extra stays
    optional -- every other CLI command works with a plain install.
    """
    try:
        import uvicorn
    except ImportError:
        print(
            "The web dashboard API requires the 'web' extra: "
            "pip install 'career-agent[web]'"
        )
        return 1
    from career_agent.api.app import create_app

    uvicorn.run(create_app(), host=host, port=port)
    return 0


def run_setup_command(
    *,
    profile_path: Path,
    settings: Settings | None = None,
    promptfoo_results_dir: Path | None = None,
) -> int:
    """The ``career-agent setup`` command: scaffold a profile + readiness report.

    Phase 25 (ADR-0051). Deterministic and fully offline -- no LLM call, no
    network, no secret ever printed. Its single job is to get a new user
    from zero to a first useful run, which the audit found to be this
    project's biggest friction: (1) if no profile exists at ``profile_path``,
    write a schema-correct JSON Resume scaffold to edit -- never overwriting
    an existing file, so a real profile is never destroyed; (2) print a
    readiness report of what is and isn't configured; (3) name the single
    next command to run. Returns 0 always -- ``setup`` is advisory, not a
    gate; nothing here can fail an unrelated flow.
    """
    settings = settings or Settings()
    results_dir = promptfoo_results_dir or Path(settings.promptfoo_results_dir)

    print("career-agent setup\n==================\n")

    # (1) Profile scaffold / load status.
    profile_ready = False
    profile_detail: str
    if write_profile_scaffold(profile_path):
        profile_detail = (
            f"wrote a starter profile to {profile_path} -- open it and "
            f"replace every placeholder with your real, truthful details"
        )
    else:
        try:
            load_master_profile(profile_path)
            profile_ready = True
            profile_detail = f"{profile_path} loads cleanly"
        except (
            OSError,
            json.JSONDecodeError,
            ProfileValidationError,
            ValidationError,
        ) as exc:
            profile_detail = f"{profile_path} exists but does not load yet: {exc}"

    # (2) Provider key presence (never printed, only presence).
    has_groq = bool(settings.groq_api_key)
    has_anthropic = bool(settings.anthropic_api_key)
    key_ready = has_groq or has_anthropic
    if has_groq:
        key_detail = "GROQ_API_KEY is set (free-tier verifier, ADR-0043)"
    elif has_anthropic:
        key_detail = "ANTHROPIC_API_KEY is set (paid fallback verifier)"
    else:
        key_detail = "no GROQ_API_KEY or ANTHROPIC_API_KEY found in the environment"

    # (3) Promptfoo artifact presence (offline, presence-only).
    artifacts = sorted(results_dir.glob("*.json")) if results_dir.is_dir() else []
    promptfoo_ready = bool(artifacts)
    promptfoo_detail = (
        f"{len(artifacts)} results artifact(s) present in {results_dir}"
        if promptfoo_ready
        else f"no promptfoo results artifact found in {results_dir}"
    )

    checks = [
        ("Profile", profile_ready, profile_detail),
        ("LLM provider key", key_ready, key_detail),
        ("Promptfoo validation", promptfoo_ready, promptfoo_detail),
    ]
    for label, ok, detail in checks:
        marker = "[ready]" if ok else "[todo] "
        print(f"  {marker} {label}: {detail}")

    print(
        f"\n  (data paths: database={settings.database_path}, "
        f"artifacts={settings.artifacts_dir})"
    )

    # (4) The single next action, chosen deterministically from the state.
    if not profile_ready:
        nxt = (
            f"Edit {profile_path} with your real details, then re-run "
            f"career-agent setup."
        )
    elif not key_ready:
        nxt = (
            "Set GROQ_API_KEY (free tier) or ANTHROPIC_API_KEY, then re-run "
            "career-agent setup."
        )
    elif not promptfoo_ready:
        nxt = (
            "Run the promptfoo suite (see promptfoo/README), then "
            "career-agent verify-promptfoo --provider groq."
        )
    else:
        nxt = f"You're ready. Try: career-agent discover --profile {profile_path}"
    print(f"\nNext: {nxt}")
    return 0


def run_import_cv_command(*, cv_path: Path, out_path: Path | None = None) -> int:
    """The ``career-agent import-cv`` command (Phase 26, ADR-0052).

    Parses a CV into an UNVERIFIED :class:`IngestionDraft` of source-bound
    fact proposals and writes it to a draft file. **Never touches the
    verified profile** and makes no network/LLM call. Returns non-zero on a
    malformed/unsupported document, after which nothing was written.
    """
    try:
        draft = ingest_document(cv_path)
    except UnsupportedDocumentError as exc:
        print(str(exc))
        return 1
    except (DocumentParseError, OSError) as exc:
        print(f"Could not read {cv_path}: {exc}")
        return 1

    target = out_path or cv_path.with_suffix(".draft.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        draft.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )

    conflicted = sum(1 for p in draft.proposals if p.conflict_ids)
    print(f"Imported {cv_path} ({draft.source_type}).")
    print(f"  {len(draft.proposals)} UNVERIFIED proposal(s) extracted.")
    print(f"  {conflicted} proposal(s) in a detected conflict.")
    print(
        "  Nothing was trusted or written to your profile -- every proposal "
        "is unverified.\n"
    )
    print(f"Draft written to {target}")
    print(
        "Next: open the draft, set \"trust_state\": \"confirmed\" on each "
        "proposal you personally verify (leave the rest, or set "
        '"rejected"), then run:\n'
        f"  career-agent promote-cv --draft {target} --cv {cv_path} "
        "--profile profile.json"
    )
    return 0


def run_promote_cv_command(
    *, draft_path: Path, cv_path: Path, profile_path: Path
) -> int:
    """The ``career-agent promote-cv`` command (Phase 26, ADR-0052).

    Promotes only the proposals a human marked ``confirmed`` in the draft,
    and only through the fail-closed boundary: the source document is
    re-read and its identity checked against the draft (source-drift
    refusal), every promoted proposal's evidence is re-validated against
    that document, and a different existing verified value is never
    overwritten. Writes the profile back only if something was actually
    added; makes no network/LLM call.
    """
    try:
        draft = IngestionDraft.model_validate_json(
            draft_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError, json.JSONDecodeError) as exc:
        print(f"Could not load draft {draft_path}: {exc}")
        return 1

    try:
        raw_bytes, document_text, _ = read_document(cv_path)
    except (UnsupportedDocumentError, DocumentParseError, OSError) as exc:
        print(f"Could not read {cv_path}: {exc}")
        return 1

    if document_digest(raw_bytes) != draft.document_digest:
        print(
            f"Source drift: {cv_path} no longer matches the document this "
            f"draft was built from (its content changed). Re-run "
            f"career-agent import-cv and review the new draft. Nothing was "
            f"promoted."
        )
        return 1

    if not profile_path.exists():
        print(
            f"No profile at {profile_path}. Run 'career-agent setup' first, "
            f"then promote into it. Nothing was promoted."
        )
        return 1
    try:
        profile_raw = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not load profile {profile_path}: {exc}")
        return 1

    updated, results = apply_confirmed_promotions(draft, document_text, profile_raw)

    added = [r for r in results if r.outcome == ADD]
    if added:
        profile_path.write_text(
            json.dumps(updated, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    counts: dict[str, int] = {}
    for result in results:
        counts[result.outcome] = counts.get(result.outcome, 0) + 1
    print(f"Promotion summary for {profile_path}:")
    for outcome in sorted(counts):
        print(f"  {outcome}: {counts[outcome]}")
    for result in results:
        if result.outcome != "NO_OP":
            print(
                f"  - [{result.outcome}] {result.field_path} = "
                f"{result.proposed_value!r} ({result.reason})"
            )
    if added:
        print(
            f"\n{len(added)} fact(s) promoted into {profile_path}. Review the "
            f"file, then: career-agent verify-promptfoo / discover."
        )
    else:
        print(
            "\nNothing was promoted (mark proposals \"confirmed\" in the "
            "draft, or resolve conflicts/overwrites, then re-run)."
        )
    return 0


def main(argv: list[str] | None = None) -> None:
    """Parse CLI arguments and dispatch, or print the Phase 1 placeholder banner.

    ``argv`` defaults to ``None``, which tells :mod:`argparse` to read the
    real process's ``sys.argv`` -- correct for the real ``career-agent``
    entry point. Callers that invoke ``main()`` programmatically (tests)
    must pass an explicit list, even an empty one, so this never
    accidentally parses whatever arguments the *calling* process (e.g.
    pytest) happened to be started with.
    """
    parser = argparse.ArgumentParser(prog="career-agent")
    subparsers = parser.add_subparsers(dest="command")

    setup_parser = subparsers.add_parser(
        "setup",
        help="Get started: scaffold a starter profile if you have none, and "
        "print an offline readiness report with your next step.",
    )
    setup_parser.add_argument(
        "--profile",
        type=Path,
        default=Path("profile.json"),
        help="Where your JSON Resume master profile is (or should be scaffolded).",
    )

    preferences_parser = subparsers.add_parser(
        "preferences",
        help="Interactive Job Search Preferences wizard -- what roles, "
        "locations, and companies to look for. Separate from your master "
        "profile (ADR-0064); never touches profile.json.",
    )
    preferences_parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Defaults to job_preferences.json relative to the current "
        "working directory (Settings.job_preferences_path, "
        ".env-overridable).",
    )

    import_cv_parser = subparsers.add_parser(
        "import-cv",
        help="Parse a CV (.docx/.txt/.md) into an UNVERIFIED draft of "
        "source-bound fact proposals. Never touches your verified profile.",
    )
    import_cv_parser.add_argument("--cv", type=Path, required=True)
    import_cv_parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Draft output path (default: <cv>.draft.json).",
    )

    promote_cv_parser = subparsers.add_parser(
        "promote-cv",
        help="Promote only the proposals you marked 'confirmed' in a draft "
        "into your profile -- fail-closed, never overwriting a different "
        "verified value.",
    )
    promote_cv_parser.add_argument("--draft", type=Path, required=True)
    promote_cv_parser.add_argument("--cv", type=Path, required=True)
    promote_cv_parser.add_argument(
        "--profile", type=Path, default=Path("profile.json")
    )

    apply_parser = subparsers.add_parser(
        "apply",
        help=(
            "Tailor, gate, render, and get a real human confirmation for one "
            "opportunity. Does not submit -- no real ATS adapter is wired in "
            "yet (ADR-0026)."
        ),
    )
    apply_parser.add_argument(
        "--profile",
        type=Path,
        required=True,
        help="Path to your JSON Resume master profile.",
    )
    apply_parser.add_argument(
        "--opportunity-file",
        type=Path,
        required=True,
        help="Path to a JSON file describing the Opportunity to apply to.",
    )

    prepare_parser = subparsers.add_parser(
        "prepare",
        help=(
            "Tailor, gate, generate a cover letter, and fill out a real "
            "application form in a live browser -- stopping before Submit "
            "(Phase 51, ADR-0069). Never submits anything."
        ),
    )
    prepare_parser.add_argument(
        "--profile",
        type=Path,
        required=True,
        help="Path to your JSON Resume master profile.",
    )
    prepare_parser.add_argument(
        "--opportunity-file",
        type=Path,
        required=True,
        help="Path to a JSON file describing the Opportunity to prepare.",
    )

    review_parser = subparsers.add_parser(
        "review",
        help=(
            "Present a prepared application session for human approval and "
            "record the decision (Phase 52, ADR-0070). Never submits "
            "anything; never touches a browser."
        ),
    )
    review_parser.add_argument(
        "--session",
        type=Path,
        required=True,
        help="Path to the session JSON file written by `prepare`.",
    )

    submit_parser = subparsers.add_parser(
        "submit",
        help=(
            "Submit an APPROVED, reviewed application -- the only command "
            "that can click a real Submit button (Phase 53, ADR-0071). "
            "Fails closed on any unmet precondition; requires one final "
            "explicit confirmation."
        ),
    )
    submit_parser.add_argument(
        "--review-session",
        type=Path,
        required=True,
        help="Path to the review session JSON file written by `review`.",
    )
    submit_parser.add_argument(
        "--opportunity-file",
        type=Path,
        required=True,
        help="Path to the same Opportunity JSON file used with `prepare`.",
    )
    submit_parser.add_argument(
        "--profile",
        type=Path,
        required=True,
        help="Path to your JSON Resume master profile.",
    )

    discover_parser = subparsers.add_parser(
        "discover",
        help="Poll every configured source, dedup, persist, and write "
        "opportunity-file handoffs apply can consume.",
    )
    discover_parser.add_argument("--since-days", type=int, default=7)
    discover_parser.add_argument(
        "--out-dir", type=Path, default=Path("data/opportunities")
    )
    discover_parser.add_argument(
        "--profile",
        type=Path,
        default=None,
        help="Optional profile path: enables the ranked summary (ADR-0038).",
    )

    auto_parser = subparsers.add_parser(
        "auto",
        help="One bounded, cron-safe pass: discover -> rank -> tailor+gate "
        "-> record -> notify. Structurally cannot confirm or submit "
        "(ADR-0041) -- always ends with career-agent apply left for you.",
    )
    auto_parser.add_argument(
        "--profile",
        type=Path,
        required=True,
        help="Path to your JSON Resume master profile.",
    )
    auto_parser.add_argument("--since-days", type=int, default=7)
    auto_parser.add_argument(
        "--out-dir", type=Path, default=Path("data/opportunities")
    )
    auto_parser.add_argument(
        "--top-n",
        type=int,
        default=3,
        help="How many top-ranked opportunities to tailor+gate this pass.",
    )

    capture_parser = subparsers.add_parser(
        "capture-legal-status",
        help="Explicitly capture work-authorization/sponsorship answers "
        "into your profile (yes/no/skip -- skip leaves 'never asked').",
    )
    capture_parser.add_argument("--profile", type=Path, required=True)

    outcome_parser = subparsers.add_parser(
        "outcome", help="Record a real-world outcome for an application."
    )
    outcome_parser.add_argument("application_id")
    outcome_parser.add_argument(
        "kind", choices=sorted(_OUTCOME_KINDS)
    )
    outcome_parser.add_argument("--stage", default=None)

    subparsers.add_parser(
        "report", help="Per-variant funnel counts (raw counts, ADR-0039)."
    )

    export_parser = subparsers.add_parser(
        "export", help="Export the application tracker to an Excel workbook."
    )
    export_parser.add_argument(
        "--xlsx", type=Path, default=Path("data/applications.xlsx")
    )

    verify_promptfoo_parser = subparsers.add_parser(
        "verify-promptfoo",
        help="Check a real local promptfoo results artifact against the "
        "exact gate 'apply' uses -- no API key, no network call.",
    )
    verify_promptfoo_parser.add_argument(
        "--provider", required=True, choices=("anthropic", "groq")
    )
    verify_promptfoo_parser.add_argument(
        "--results-dir",
        type=Path,
        default=None,
        help=(
            "Defaults to promptfoo/results relative to the current working "
            "directory (Settings.promptfoo_results_dir, .env-overridable)."
        ),
    )

    diagnose_promptfoo_parser = subparsers.add_parser(
        "diagnose-promptfoo-drift",
        help="Print exactly why the prompt-content drift check in "
        "verify-promptfoo would accept or reject a real local results "
        "artifact -- lengths, hashes, first differing character. No "
        "résumé/claim content or secrets printed.",
    )
    diagnose_promptfoo_parser.add_argument(
        "--provider", required=True, choices=("anthropic", "groq")
    )
    diagnose_promptfoo_parser.add_argument(
        "--results-dir",
        type=Path,
        default=None,
        help=(
            "Defaults to promptfoo/results relative to the current working "
            "directory (Settings.promptfoo_results_dir, .env-overridable)."
        ),
    )

    serve_parser = subparsers.add_parser(
        "serve",
        help="Run the read-only Web Dashboard API (Phase 54, ADR-0072). "
        "Cannot discover, tailor, approve, or submit -- those stay CLI-only.",
    )
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)

    if args.command == "discover":
        settings = Settings()
        since = datetime.now(UTC) - timedelta(days=args.since_days)
        profile = (
            load_master_profile(args.profile) if args.profile is not None else None
        )
        try:
            preferences = _load_preferences_if_present(settings)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            print(
                f"Could not load job preferences from "
                f"{settings.job_preferences_path}: {exc}"
            )
            raise SystemExit(1) from exc
        scorer = _build_decide_scorer(settings)
        exit_code = asyncio.run(
            run_discover_command(
                build_discovery_sources(settings, preferences),
                SqliteOpportunityRepository(Path(settings.database_path)),
                since=since,
                out_dir=args.out_dir,
                profile=profile,
                scorer=scorer,
            )
        )
        raise SystemExit(exit_code)

    if args.command == "preferences":
        raise SystemExit(run_preferences_command(path=args.path))

    if args.command == "auto":
        exit_code = asyncio.run(
            run_auto_cli_command(
                profile_path=args.profile,
                since_days=args.since_days,
                out_dir=args.out_dir,
                top_n=args.top_n,
            )
        )
        raise SystemExit(exit_code)

    if args.command == "setup":
        raise SystemExit(run_setup_command(profile_path=args.profile))

    if args.command == "import-cv":
        raise SystemExit(run_import_cv_command(cv_path=args.cv, out_path=args.out))

    if args.command == "promote-cv":
        raise SystemExit(
            run_promote_cv_command(
                draft_path=args.draft, cv_path=args.cv, profile_path=args.profile
            )
        )

    if args.command == "capture-legal-status":
        raise SystemExit(run_capture_legal_status_command(args.profile))

    if args.command == "outcome":
        settings = Settings()
        raise SystemExit(
            run_outcome_command(
                Path(settings.database_path),
                args.application_id,
                args.kind,
                args.stage,
            )
        )

    if args.command == "report":
        settings = Settings()
        raise SystemExit(run_report_command(Path(settings.database_path)))

    if args.command == "export":
        settings = Settings()
        raise SystemExit(
            run_export_command(Path(settings.database_path), args.xlsx)
        )

    if args.command == "verify-promptfoo":
        raise SystemExit(
            run_verify_promptfoo_command(args.provider, args.results_dir)
        )

    if args.command == "diagnose-promptfoo-drift":
        raise SystemExit(
            run_diagnose_promptfoo_drift_command(args.provider, args.results_dir)
        )

    if args.command == "apply":
        exit_code = asyncio.run(
            run_apply_command(
                profile_path=args.profile, opportunity_path=args.opportunity_file
            )
        )
        raise SystemExit(exit_code)

    if args.command == "prepare":
        exit_code = asyncio.run(
            run_prepare_command(
                profile_path=args.profile, opportunity_path=args.opportunity_file
            )
        )
        raise SystemExit(exit_code)

    if args.command == "review":
        raise SystemExit(run_review_command(session_path=args.session))

    if args.command == "submit":
        exit_code = asyncio.run(
            run_submit_command(
                review_session_path=args.review_session,
                opportunity_path=args.opportunity_file,
                profile_path=args.profile,
            )
        )
        raise SystemExit(exit_code)

    if args.command == "serve":
        raise SystemExit(run_serve_command(host=args.host, port=args.port))

    print(f"Autonomous AI Career Agent v{__version__} — scaffolding (Phase 1).")
    print("Not yet runnable; see ROADMAP.md for the build plan.")


if __name__ == "__main__":
    main()
