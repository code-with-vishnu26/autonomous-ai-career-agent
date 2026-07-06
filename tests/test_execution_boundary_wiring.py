"""Phase 24 / ADR-0050: the execution boundary as wired into the CLI.

Family F (integration) + the no-bypass structural guarantees. Proves the
reachable ``apply`` path consults the boundary and refuses real execution
with an explicit reason, and that nothing anywhere in the composition root
flips the executor on -- so neither a high rank, a passing truthfulness
gate, nor any other signal can authorize a submission (I15-I20).
"""

from __future__ import annotations

import inspect
from pathlib import Path

from career_agent import cli
from career_agent.agents.resume.gate import LLMTruthfulnessGate
from career_agent.agents.resume.generator import LLMResumeGenerator
from career_agent.cli import _apply_pipeline
from career_agent.core.interfaces import ClaimVerdict
from career_agent.domain.models import DraftedTailoring, Opportunity, TailoredWorkEntry
from career_agent.storage.sqlite import SqliteRunJournal
from tests._fakes import FakeClaimVerifier, FakeContentDrafter
from tests.agents._profile_fixture import sample_master_profile


def _opportunity_payload() -> dict:
    return {
        "id": "opp-1",
        "company_id": "acme",
        "canonical_company": "acme.com",
        "title": "Software Engineer",
        "source": "ats_api",
        "source_url": "https://boards.greenhouse.io/acme/jobs/12345",
        "provenance": {
            "method": "structured_api",
            "reference": "https://boards.greenhouse.io/acme/jobs/12345",
            "extraction_confidence": 1.0,
        },
        "description_raw": "We are hiring a backend engineer.",
        "discovered_at": "2026-01-01T00:00:00Z",
    }


def _honest_profile():
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer."
    return profile


def _honest_generator_and_gate():
    generator = LLMResumeGenerator(
        FakeContentDrafter(
            DraftedTailoring(
                work=[
                    TailoredWorkEntry(
                        source_entry_id="work-techco",
                        position="Software Engineer",
                        highlights=["Built REST APIs serving 2M requests/day"],
                    )
                ],
                skills=["Python"],
            )
        )
    )
    gate = LLMTruthfulnessGate(
        FakeClaimVerifier(
            {
                "Software Engineer": ClaimVerdict(verified=True, confidence=1.0),
                "Built REST APIs serving 2M requests/day": ClaimVerdict(
                    verified=True, confidence=0.95
                ),
            }
        )
    )
    return generator, gate


async def test_confirmed_apply_refuses_real_execution_with_explicit_reason(
    tmp_path: Path, capsys
) -> None:
    """Even a fully-approved, human-confirmed run does not submit: the
    boundary refuses because no executor is wired, and says so."""
    generator, gate = _honest_generator_and_gate()
    opportunity = Opportunity.model_validate(_opportunity_payload())
    journal = SqliteRunJournal(tmp_path / "db.sqlite")

    exit_code = await _apply_pipeline(
        _honest_profile(),
        opportunity,
        generator,
        gate,
        input_fn=lambda _: "y",  # human confirms
        run_journal=journal,
    )

    assert exit_code == 0  # a refusal-to-execute is not an error
    out = capsys.readouterr().out
    assert "REFUSED_NO_EXECUTOR" in out
    assert "Nothing was actually sent." in out


def test_no_cli_code_path_ever_enables_an_executor() -> None:
    """I15-I20 / no-bypass: ``executor_available`` is only ever passed False.

    Nothing -- not a passing truthfulness gate, a high rank, Pareto-optimal
    status, an ATS score, nor an LLM output -- can authorize a submission,
    because the composition root never constructs an ExecutionRequest with
    a truthy ``executor_available``.
    """
    source = inspect.getsource(cli)
    assert "executor_available=True" not in source
    assert "executor_available=False" in source  # the one wiring that exists


def test_apply_and_auto_share_one_boundary_and_neither_can_submit() -> None:
    """I20: there is a single boundary function; auto cannot route around a
    refusal apply enforces, because there is no second decision surface."""
    cli_source = inspect.getsource(cli)
    # Exactly one import of the boundary decision function, one call site.
    assert cli_source.count("execute_allowed(") == 1
    # Neither reachable command constructs a real Applicator (Phase 24
    # audit) -- so the boundary is the *only* thing between confirmation
    # and a (currently nonexistent) submission.
    for forbidden in (
        "TieredApplicator(",
        "BrowserApplicator(",
        "EmailApplicator(",
        "SubmissionPipeline(",
    ):
        assert forbidden not in cli_source
