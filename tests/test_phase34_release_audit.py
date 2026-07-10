"""Phase 34 (ADR-0056): v1.0 release-audit drift guards.

These pin the facts the v1.0.0 *release decision* depends on (the version
pin itself was advanced from `1.0.0rc1` to `1.0.0` by ADR-0059/Phase 37 on
real evidence), so a silent regression -- a version bump, a wired executor,
a README that starts overclaiming again, or a missing release artifact --
fails a test instead of shipping unnoticed. They make **no** live call and
change **no** safety semantics; they only read package metadata, run the
pure execution boundary offline, and scan committed docs.
"""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

from career_agent.domain.execution import (
    ExecutionRequest,
    SourcePolicy,
    SubmissionOutcome,
    execute_allowed,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_release_candidate_version_is_pinned() -> None:
    """The release metadata is exactly v1.0.0 (ADR-0056 policy; promoted from
    1.0.0rc1 by ADR-0059/Phase 37 on real live-Groq + CI evidence).

    Advancing this is a deliberate release-promotion decision that must re-run
    the RELEASE_CHECKLIST, not an incidental edit."""
    assert version("career-agent") == "1.0.0"


def test_external_submission_is_unreachable_no_executor_wired() -> None:
    """Even under the most permissive real source policy and an otherwise
    perfect request, the boundary refuses because no executor is available --
    the hardcoded fail-closed fact behind the PREPARE_ONLY scope (ADR-0050/56).
    """
    decision = execute_allowed(
        ExecutionRequest(
            source_policy=SourcePolicy.ASSISTED,
            executor_available=False,  # the whole build's hardcoded reality
            confirmation_present=True,
            artifact_matches=True,
            prior_outcome=SubmissionOutcome.NOT_ATTEMPTED,
            journal_has_unresolved_intent=False,
        )
    )
    assert decision.allowed is False


def test_cli_constructs_no_applicator() -> None:
    """The composition root wires no executor: `Applicator` appears only in
    prose, never as a constructor call `Applicator(` (I12)."""
    cli_src = (_REPO_ROOT / "src" / "career_agent" / "cli.py").read_text(
        encoding="utf-8"
    )
    assert "Applicator(" not in cli_src


def test_readme_states_prepare_only_and_does_not_overclaim() -> None:
    """The README must scope the release as prepare-only and must not carry the
    pre-Phase-34 overclaims (I20)."""
    readme = (_REPO_ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert "prepare_only" in readme or "prepare-only" in readme
    # The specific stale overclaims corrected in Phase 34 must not reappear.
    assert "not yet runnable" not in readme
    assert "scaffolding only" not in readme
    assert "submit through a tiered" not in readme


def test_release_artifacts_exist() -> None:
    """The justified release artifacts are committed (ADR-0056 consequences)."""
    for rel in (
        "SECURITY.md",
        "RELEASE_CHECKLIST.md",
        "docs/release/v1.0.0-rc1-notes.md",
        "docs/adr/0056-v1-prepare-only-release-scope.md",
    ):
        assert (_REPO_ROOT / rel).is_file(), rel
