"""Command-line entry point for the Autonomous AI Career Agent.

``confirm_submission`` (Phase 8c, ADR-0024) is this project's first real,
executable source of a :class:`~career_agent.domain.models.HumanConfirmation`.

``apply`` (Phase 8e, ADR-0026) is the first real, runnable command: load a
real profile and a real opportunity, tailor and gate a real resume with the
real, Claude-backed generator and verifier, render it, and ask a real human
to confirm it. It deliberately stops there -- there is no real
``ATSAdapter`` implementation anywhere in this codebase yet (only
``FakeATSAdapter``, test-only), so a confirmed application has nowhere real
to actually be sent. The command says so plainly rather than pretending to
submit; real submission is separate, named future work.

**The real ``ClaimVerifier`` is gated by an actual check, not a claim.**
ADR-0016 requires the promptfoo suite to pass on live calls before
``AnthropicClaimVerifier`` is wired into a real apply path. Until this
command existed, that requirement was enforced only by written policy and
by an import-linter contract that (correctly) leaves ``cli.py`` itself
unconstrained, since it is the composition root. ``run_apply_command``
calls :func:`~career_agent.llm.promptfoo_gate.verify_promptfoo_results`
before constructing the real verifier -- it refuses to run without a real,
current, actually-passing results artifact on disk, not a flag typed from
memory.

The opportunity is read from a plain JSON file
(``--opportunity-file``), not looked up by id from a persistent store --
no persistent ``OpportunityRepository`` exists yet, and no ``discover``
command exists to produce one. This is the narrowest real scope: a future
``discover`` command can produce this same file format without either
command's internal logic needing to change, and a future persistent store
can replace the file handoff later the same way.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from career_agent import __version__
from career_agent.agents.resume.gate import LLMTruthfulnessGate
from career_agent.agents.resume.generator import LLMResumeGenerator, MissingSummaryError
from career_agent.agents.resume.pipeline import ResumeTailoringPipeline
from career_agent.core.bus import EventBus
from career_agent.core.config import Settings
from career_agent.core.interfaces import (
    ResumeGenerator,
    SemanticKeywordMatcher,
    TruthfulnessGate,
)
from career_agent.domain.ats_scoring import AtsScoreBelowThresholdError
from career_agent.domain.models import (
    HumanConfirmation,
    LegalStatusSection,
    MasterProfile,
    Opportunity,
    SubmissionPreview,
)
from career_agent.llm.promptfoo_gate import (
    PromptfooNotValidatedError,
    verify_promptfoo_results,
)
from career_agent.llm.prompts import TRUTHFULNESS_GATE_PROMPT_VERSION
from career_agent.llm.providers import (
    NoLLMProviderConfiguredError,
    select_claim_verifier,
    select_content_drafter,
    select_semantic_matcher,
)
from career_agent.storage.excel import export_applications
from career_agent.storage.profile import (
    ProfileValidationError,
    load_master_profile,
    save_legal_status,
)
from career_agent.storage.sqlite import (
    SqliteApplicationStore,
    SqliteOpportunityRepository,
)

_YES = {"y", "yes"}

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_PROMPTFOO_RESULTS_DIR = _REPO_ROOT / "promptfoo" / "results"


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
    for catching these and printing a clean message.
    """
    return Opportunity.model_validate(json.loads(path.read_text()))


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
    """
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
    try:
        result = await pipeline.run(opportunity, profile)
    except MissingSummaryError as exc:
        print(f"Cannot tailor a resume: {exc}")
        return 1
    except AtsScoreBelowThresholdError as exc:
        print("The ATS score gate refused this application:")
        print(str(exc))
        return 1

    if application_store is not None:
        application_store.record(
            result.application,
            company=opportunity.canonical_company,
            source=opportunity.source,
            ats_total=result.ats_report.total if result.ats_report else None,
        )

    if result.submittable is None:
        print("The truthfulness gate rejected this draft:")
        for rejection in result.application.resume.truthfulness.rejections:
            print(f"  - [{rejection.category}] {rejection.detail}")
        return 1

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
    confirmation = confirm_submission(preview, input_fn=input_fn)
    if confirmation is None:
        print("Not confirmed. Exiting without submitting.")
        return 0

    print(
        "Confirmed. No real ATS adapter is wired in yet -- real submission "
        "is separate, future work (ADR-0026). Nothing was actually sent."
    )
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

    results_dir = promptfoo_results_dir or _DEFAULT_PROMPTFOO_RESULTS_DIR
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
        notifier=build_notifier(settings),
    )


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
                handoff.write_text(opportunity.model_dump_json(indent=2))
        print(f"[{name}] {len(found)} fetched, {fresh} new")
    print(f"{new_count} new opportunit{'y' if new_count == 1 else 'ies'} -> {out_dir}")
    if profile is not None and scorer is not None and new_opportunities:
        included, excluded = scorer.rank(new_opportunities, profile)  # type: ignore[attr-defined]
        print("Ranked (Decide layer, ADR-0038):")
        for opportunity, decision in included[:10]:
            print(
                f"  {decision.total:5.1f}  {opportunity.canonical_company}: "
                f"{opportunity.title}  ({out_dir / (opportunity.id + '.json')})"
            )
        for decision in excluded:
            print(
                f"  EXCLUDED {decision.opportunity_id}: "
                f"{'; '.join(decision.exclude_reasons)}"
            )
    return 0


def build_discovery_sources(settings: Settings) -> list[tuple[str, object]]:
    """Wire every source whose config is present (composition root)."""
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
    keywords = settings.discovery_keywords
    sources: list[tuple[str, object]] = []
    if settings.adzuna_app_id and settings.adzuna_app_key:
        countries = [
            country.strip()
            for country in settings.adzuna_countries.split(",")
            if country.strip()
        ]
        sources.append(
            (
                "adzuna",
                AdzunaSource(
                    app_id=settings.adzuna_app_id,
                    app_key=settings.adzuna_app_key,
                    countries=countries,
                    keywords=keywords,
                    client=client,
                ),
            )
        )
    if settings.reed_api_key:
        sources.append(
            (
                "reed",
                ReedSource(
                    api_key=settings.reed_api_key, keywords=keywords, client=client
                ),
            )
        )
    if settings.usajobs_api_key and settings.usajobs_user_agent:
        sources.append(
            (
                "usajobs",
                UsaJobsSource(
                    api_key=settings.usajobs_api_key,
                    user_agent=settings.usajobs_user_agent,
                    keywords=keywords,
                    client=client,
                ),
            )
        )
    if settings.jooble_api_key:
        sources.append(
            (
                "jooble",
                JoobleSource(
                    api_key=settings.jooble_api_key,
                    keywords=keywords,
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
            results_dir or _DEFAULT_PROMPTFOO_RESULTS_DIR,
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
    """
    await run_discover_command(
        sources, repo, since=since, out_dir=out_dir
    )
    handoffs = sorted(out_dir.glob("*.json"))
    opportunities = [
        Opportunity.model_validate(json.loads(path.read_text()))
        for path in handoffs
    ]
    included, _excluded = scorer.rank(opportunities, profile)  # type: ignore[attr-defined]
    prepared = 0
    for opportunity, decision in included[:top_n]:
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
            continue
        prepared += 1
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
        help="Defaults to promptfoo/results at the repo root.",
    )

    args = parser.parse_args(argv)

    if args.command == "discover":
        from career_agent.agents.planner.decide import (
            DecideFilters,
            DeterministicDecideScorer,
        )

        settings = Settings()
        since = datetime.now(UTC) - timedelta(days=args.since_days)
        profile = (
            load_master_profile(args.profile) if args.profile is not None else None
        )
        scorer = DeterministicDecideScorer(
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
        exit_code = asyncio.run(
            run_discover_command(
                build_discovery_sources(settings),
                SqliteOpportunityRepository(Path(settings.database_path)),
                since=since,
                out_dir=args.out_dir,
                profile=profile,
                scorer=scorer,
            )
        )
        raise SystemExit(exit_code)

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

    if args.command == "apply":
        exit_code = asyncio.run(
            run_apply_command(
                profile_path=args.profile, opportunity_path=args.opportunity_file
            )
        )
        raise SystemExit(exit_code)

    print(f"Autonomous AI Career Agent v{__version__} — scaffolding (Phase 1).")
    print("Not yet runnable; see ROADMAP.md for the build plan.")


if __name__ == "__main__":
    main()
