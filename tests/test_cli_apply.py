"""Phase 8e / ADR-0026: the real `career-agent apply` command.

``_apply_pipeline`` is tested directly, injected with fakes -- it never
touches a real Anthropic client. ``run_apply_command`` is tested only for
its file-loading and promptfoo-gate-ordering behavior (also fully offline);
the real, Claude-backed construction path it wires together on success is
untestable live in this sandbox, disclosed the same as every other real
external-system client in this project.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from career_agent.agents.resume.gate import LLMTruthfulnessGate
from career_agent.agents.resume.generator import LLMResumeGenerator
from career_agent.cli import _apply_pipeline, run_apply_command
from career_agent.core.interfaces import ClaimVerdict
from career_agent.domain.models import DraftedTailoring, MasterProfile
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


def _write_opportunity_file(tmp_path: Path) -> Path:
    path = tmp_path / "opportunity.json"
    path.write_text(json.dumps(_opportunity_payload()))
    return path


def _honest_profile() -> MasterProfile:
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer."
    return profile


def _honest_drafted() -> DraftedTailoring:
    from career_agent.domain.models import TailoredWorkEntry

    return DraftedTailoring(
        work=[
            TailoredWorkEntry(
                source_entry_id="work-techco",
                position="Software Engineer",
                highlights=["Built REST APIs serving 2M requests/day"],
            )
        ],
        skills=["Python"],
    )


# ---------------------------------------------------------------------------
# _apply_pipeline -- fully offline, fake-backed
# ---------------------------------------------------------------------------


async def test_approved_draft_prints_resume_and_confirms_yes() -> None:
    generator = LLMResumeGenerator(FakeContentDrafter(_honest_drafted()))
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
    from career_agent.domain.models import Opportunity

    opportunity = Opportunity.model_validate(_opportunity_payload())
    exit_code = await _apply_pipeline(
        _honest_profile(), opportunity, generator, gate, input_fn=lambda _: "y"
    )
    assert exit_code == 0


async def test_approved_draft_but_declined_confirmation_exits_zero_no_submission() -> (
    None
):
    generator = LLMResumeGenerator(FakeContentDrafter(_honest_drafted()))
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
    from career_agent.domain.models import Opportunity

    opportunity = Opportunity.model_validate(_opportunity_payload())
    exit_code = await _apply_pipeline(
        _honest_profile(), opportunity, generator, gate, input_fn=lambda _: ""
    )
    assert exit_code == 0


async def test_rejected_draft_exits_nonzero_and_never_asks_for_confirmation() -> None:
    """A rejected draft must not reach confirm_submission at all -- proven
    by an input_fn that raises if it's ever called."""
    generator = LLMResumeGenerator(
        FakeContentDrafter(DraftedTailoring(skills=["Kubernetes"]))
    )
    gate = LLMTruthfulnessGate(FakeClaimVerifier({}))

    def _fail_if_called(_: str) -> str:
        raise AssertionError("confirm_submission must not be reached")

    from career_agent.domain.models import Opportunity

    opportunity = Opportunity.model_validate(_opportunity_payload())
    exit_code = await _apply_pipeline(
        _honest_profile(), opportunity, generator, gate, input_fn=_fail_if_called
    )
    assert exit_code == 1


async def test_rejected_draft_is_recorded_and_does_not_block_retry(
    tmp_path: Path,
) -> None:
    """The rejected-draft record() call still fires (audit trail for the
    funnel report, ADR-0039) after being moved to fire once the terminal
    status is known (Phase 36 refactor) -- and, unchanged from before,
    "rejected" never blocks a fresh attempt (ADR-0048)."""
    from career_agent.domain.models import Opportunity
    from career_agent.storage.sqlite import SqliteApplicationStore

    generator = LLMResumeGenerator(
        FakeContentDrafter(DraftedTailoring(skills=["Kubernetes"]))
    )
    gate = LLMTruthfulnessGate(FakeClaimVerifier({}))
    opportunity = Opportunity.model_validate(_opportunity_payload())
    store = SqliteApplicationStore(tmp_path / "db.sqlite")

    def _fail_if_called(_: str) -> str:
        raise AssertionError("confirm_submission must not be reached")

    exit_code = await _apply_pipeline(
        _honest_profile(),
        opportunity,
        generator,
        gate,
        input_fn=_fail_if_called,
        application_store=store,
    )
    assert exit_code == 1
    rows = store.all_rows()
    assert len(rows) == 1
    assert rows[0]["status"] == "rejected"
    assert store.prior_attempt_status(opportunity.id) is None


async def test_missing_summary_exits_nonzero_without_crashing() -> None:
    generator = LLMResumeGenerator(FakeContentDrafter(_honest_drafted()))
    gate = LLMTruthfulnessGate(FakeClaimVerifier({}))

    from career_agent.domain.models import Opportunity

    opportunity = Opportunity.model_validate(_opportunity_payload())
    profile = sample_master_profile()
    assert profile.basics.summary is None
    exit_code = await _apply_pipeline(profile, opportunity, generator, gate)
    assert exit_code == 1


async def test_prior_non_rejected_attempt_refuses_to_tailor_again(
    tmp_path: Path,
) -> None:
    """Phase 22 / ADR-0048: never silently re-attempt a recorded application."""
    from career_agent.domain.models import (
        Application,
        BasicsSection,
        LegalStatusSection,
        Opportunity,
        Statement,
        TailoredContent,
        TailoredResume,
        TruthfulnessResult,
    )
    from career_agent.storage.sqlite import SqliteApplicationStore

    generator = LLMResumeGenerator(FakeContentDrafter(_honest_drafted()))
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
    opportunity = Opportunity.model_validate(_opportunity_payload())
    store = SqliteApplicationStore(tmp_path / "db.sqlite")
    prior_resume = TailoredResume(
        id="resume-prior",
        opportunity_id=opportunity.id,
        profile_version="profile-v1",
        content=TailoredContent(summary="Engineer."),
        truthfulness=TruthfulnessResult(
            profile_version="profile-v1",
            approved=True,
            statements=[
                Statement(text="x", evidence=None, confidence=1, verified=True)
            ],
            prompt_version="test-v1",
        ),
    )
    prior_application = Application(
        id="prior-app",
        opportunity_id=opportunity.id,
        resume=prior_resume,
        applicant=BasicsSection(name="Ada", email="ada@example.com"),
        legal_status=LegalStatusSection(),
        status="submitted",
    )
    store.record(
        prior_application, company="acme", source="ats_api", ats_total=None
    )

    def _fail_if_called(_: str) -> str:
        raise AssertionError("must refuse before ever tailoring")

    exit_code = await _apply_pipeline(
        _honest_profile(),
        opportunity,
        generator,
        gate,
        input_fn=_fail_if_called,
        application_store=store,
    )
    assert exit_code == 1


async def test_declined_confirmation_does_not_permanently_block_retry(
    tmp_path: Path,
) -> None:
    """Phase 36 (real-world Windows evidence): a user who types 'n' at the
    confirmation prompt made zero real-world submission attempt -- no
    executor was ever reached (ADR-0050). The application-attempt
    idempotency guard (ADR-0048) exists to block a *risky* repeat attempt;
    a declined run carries the same "no side effect occurred" property as
    a truthfulness rejection, so it must not permanently soft-lock the
    opportunity the way a real submitted/paused_for_human/failed attempt
    legitimately would."""
    from career_agent.domain.models import Opportunity
    from career_agent.storage.sqlite import SqliteApplicationStore

    generator = LLMResumeGenerator(FakeContentDrafter(_honest_drafted()))
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
    opportunity = Opportunity.model_validate(_opportunity_payload())
    store = SqliteApplicationStore(tmp_path / "db.sqlite")

    first_exit = await _apply_pipeline(
        _honest_profile(),
        opportunity,
        generator,
        gate,
        input_fn=lambda _: "n",
        application_store=store,
    )
    assert first_exit == 0

    # The declined attempt is recorded (audit trail preserved) but must not
    # read back as a blocking prior attempt.
    assert store.prior_attempt_status(opportunity.id) is None

    # A fresh attempt for the same opportunity must not be refused.
    second_exit = await _apply_pipeline(
        _honest_profile(),
        opportunity,
        generator,
        gate,
        input_fn=lambda _: "y",
        application_store=store,
    )
    assert second_exit == 0


def _all_journal_rows(db_path: Path) -> list[tuple]:
    """Raw peek at every journal row -- test-only, the store exposes no
    "list all runs" method (not needed by any real caller yet)."""
    import sqlite3

    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        "SELECT run_id, sequence_no, stage, event_type, outcome"
        " FROM run_journal ORDER BY run_id, sequence_no"
    ).fetchall()
    connection.close()
    return rows


async def test_run_journal_records_the_happy_path_stage_history(
    tmp_path: Path,
) -> None:
    """Phase 23 / ADR-0049: a fresh run_id, in-order stage transitions,
    ending with RUN_COMPLETED -- purely informational, never a gate."""
    from career_agent.domain.models import Opportunity
    from career_agent.storage.sqlite import SqliteRunJournal

    generator = LLMResumeGenerator(FakeContentDrafter(_honest_drafted()))
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
    opportunity = Opportunity.model_validate(_opportunity_payload())
    db_path = tmp_path / "db.sqlite"
    journal = SqliteRunJournal(db_path)

    exit_code = await _apply_pipeline(
        _honest_profile(),
        opportunity,
        generator,
        gate,
        input_fn=lambda _: "y",
        run_journal=journal,
    )
    assert exit_code == 0

    rows = _all_journal_rows(db_path)
    run_ids = {row[0] for row in rows}
    assert len(run_ids) == 1  # exactly one run_id for this whole invocation
    event_types = [row[3] for row in rows]
    assert event_types == [
        "RUN_STARTED",
        "TAILORING_STARTED",
        "TAILORING_COMPLETED",
        "TRUTHFULNESS_APPROVED",
        "AWAITING_CONFIRMATION",
        "EXECUTION_REFUSED",
        "RUN_COMPLETED",
    ]
    # Phase 24 / ADR-0050: even after a human confirms, the execution
    # boundary refuses because no automated executor is wired -- the
    # confirmed run still ends "not submitted".
    execution_row = rows[event_types.index("EXECUTION_REFUSED")]
    assert execution_row[4] == "REFUSED_NO_EXECUTOR"
    assert rows[-1][4] == "confirmed_not_submitted"


async def test_run_journal_records_idempotency_refusal_without_tailoring(
    tmp_path: Path,
) -> None:
    """A refused re-attempt (ADR-0048) is itself a reconstructable event,
    distinct from a real tailoring run."""
    from career_agent.domain.models import (
        Application,
        BasicsSection,
        LegalStatusSection,
        Opportunity,
        Statement,
        TailoredContent,
        TailoredResume,
        TruthfulnessResult,
    )
    from career_agent.storage.sqlite import SqliteApplicationStore, SqliteRunJournal

    opportunity = Opportunity.model_validate(_opportunity_payload())
    db_path = tmp_path / "db.sqlite"
    store = SqliteApplicationStore(db_path)
    prior_resume = TailoredResume(
        id="resume-prior",
        opportunity_id=opportunity.id,
        profile_version="profile-v1",
        content=TailoredContent(summary="Engineer."),
        truthfulness=TruthfulnessResult(
            profile_version="profile-v1",
            approved=True,
            statements=[
                Statement(text="x", evidence=None, confidence=1, verified=True)
            ],
            prompt_version="test-v1",
        ),
    )
    store.record(
        Application(
            id="prior-app",
            opportunity_id=opportunity.id,
            resume=prior_resume,
            applicant=BasicsSection(name="Ada", email="ada@example.com"),
            legal_status=LegalStatusSection(),
            status="submitted",
        ),
        company="acme",
        source="ats_api",
        ats_total=None,
    )
    journal = SqliteRunJournal(db_path)
    generator = LLMResumeGenerator(FakeContentDrafter(_honest_drafted()))
    gate = LLMTruthfulnessGate(FakeClaimVerifier({}))

    def _fail_if_called(_: str) -> str:
        raise AssertionError("must refuse before ever tailoring")

    exit_code = await _apply_pipeline(
        _honest_profile(),
        opportunity,
        generator,
        gate,
        input_fn=_fail_if_called,
        application_store=store,
        run_journal=journal,
    )
    assert exit_code == 1

    event_types = [row[3] for row in _all_journal_rows(db_path)]
    assert event_types == ["RUN_STARTED", "RUN_REFUSED"]


# ---------------------------------------------------------------------------
# run_apply_command -- file loading and promptfoo-gate ordering, still offline
# ---------------------------------------------------------------------------


async def test_missing_profile_file_exits_cleanly(tmp_path: Path) -> None:
    exit_code = await run_apply_command(
        profile_path=tmp_path / "does-not-exist.json",
        opportunity_path=_write_opportunity_file(tmp_path),
    )
    assert exit_code == 1


async def test_missing_opportunity_file_exits_cleanly(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    profile_path.write_text("{}")
    exit_code = await run_apply_command(
        profile_path=profile_path,
        opportunity_path=tmp_path / "does-not-exist.json",
    )
    assert exit_code == 1


async def test_missing_api_key_exits_before_touching_promptfoo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No ANTHROPIC_API_KEY must fail before even checking promptfoo results
    -- proven by pointing promptfoo_results_dir at a directory that would
    itself raise if actually inspected past this point."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "basics": {"name": "Ada", "email": "ada@example.com", "summary": "x"},
                "work": [],
                "education": [],
                "skills": [],
                "projects": [],
            }
        )
    )
    exit_code = await run_apply_command(
        profile_path=profile_path,
        opportunity_path=_write_opportunity_file(tmp_path),
        promptfoo_results_dir=tmp_path / "nonexistent-promptfoo-dir",
    )
    assert exit_code == 1


async def test_promptfoo_not_validated_blocks_even_with_a_valid_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A valid ANTHROPIC_API_KEY alone must not be enough to proceed -- the
    promptfoo gate must still block, before any real Anthropic client is
    constructed. This is the symmetric, load-bearing ordering proof: the
    previous test proves the API-key check happens first when the key is
    absent; this proves the promptfoo check still bites even when the key
    check has already passed."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-for-test")
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "basics": {"name": "Ada", "email": "ada@example.com", "summary": "x"},
                "work": [],
                "education": [],
                "skills": [],
                "projects": [],
            }
        )
    )
    exit_code = await run_apply_command(
        profile_path=profile_path,
        opportunity_path=_write_opportunity_file(tmp_path),
        promptfoo_results_dir=tmp_path / "nonexistent-promptfoo-dir",
    )
    assert exit_code == 1


# ---------------------------------------------------------------------------
# main()'s argv dispatch -- proven with an explicit argv, never sys.argv
# ---------------------------------------------------------------------------


def test_main_dispatches_apply_with_the_right_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import career_agent.cli as cli_module

    seen: dict[str, Path] = {}

    async def _fake_run_apply_command(
        *, profile_path: Path, opportunity_path: Path
    ) -> int:
        seen["profile_path"] = profile_path
        seen["opportunity_path"] = opportunity_path
        return 3

    monkeypatch.setattr(cli_module, "run_apply_command", _fake_run_apply_command)
    profile_path = tmp_path / "profile.json"
    opportunity_path = tmp_path / "opportunity.json"

    with pytest.raises(SystemExit) as exc_info:
        cli_module.main(
            [
                "apply",
                "--profile",
                str(profile_path),
                "--opportunity-file",
                str(opportunity_path),
            ]
        )
    assert exc_info.value.code == 3
    assert seen["profile_path"] == profile_path
    assert seen["opportunity_path"] == opportunity_path
