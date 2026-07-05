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
from datetime import UTC, datetime
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
    MasterProfile,
    Opportunity,
    SubmissionPreview,
)
from career_agent.llm.claim_verifier import AnthropicClaimVerifier
from career_agent.llm.content_drafter import AnthropicContentDrafter
from career_agent.llm.promptfoo_gate import (
    PromptfooNotValidatedError,
    verify_promptfoo_results,
)
from career_agent.llm.prompts import TRUTHFULNESS_GATE_PROMPT_VERSION
from career_agent.llm.semantic_matcher import AnthropicSemanticKeywordMatcher
from career_agent.storage.profile import ProfileValidationError, load_master_profile

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
    if not settings.anthropic_api_key:
        print(
            "ANTHROPIC_API_KEY is not set -- required to tailor and gate a "
            "real resume."
        )
        return 1

    results_dir = promptfoo_results_dir or _DEFAULT_PROMPTFOO_RESULTS_DIR
    try:
        verify_promptfoo_results(TRUTHFULNESS_GATE_PROMPT_VERSION, results_dir)
    except PromptfooNotValidatedError as exc:
        print(str(exc))
        return 1

    generator = LLMResumeGenerator(
        AnthropicContentDrafter(api_key=settings.anthropic_api_key)
    )
    gate = LLMTruthfulnessGate(
        AnthropicClaimVerifier(api_key=settings.anthropic_api_key)
    )
    semantic_matcher = AnthropicSemanticKeywordMatcher(
        api_key=settings.anthropic_api_key
    )
    return await _apply_pipeline(
        profile,
        opportunity,
        generator,
        gate,
        input_fn=input_fn,
        artifacts_dir=Path(settings.artifacts_dir),
        ats_threshold=settings.ats_threshold,
        semantic_matcher=semantic_matcher,
    )


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

    args = parser.parse_args(argv)

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
