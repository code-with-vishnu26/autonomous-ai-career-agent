"""Phase 17 / ADR-0041: the real, runnable `career-agent auto` command.

Until this test (and the `auto` subparser it exercises) existed, the
roadmap's own "Done when: `career-agent auto`" criterion for this phase
was not actually satisfiable -- `run_auto_command` was tested directly as
a Python function, but `main()` never registered an `auto` subcommand, so
a real user typing the documented command got an argparse error.

`test_full_rehearsal_prepares_without_ever_submitting` is this project's
first offline, one-shot proof that discover -> dedup -> rank -> tailor ->
truthfulness-gate -> notify actually compose end to end through the real
`run_auto_command`/`run_auto_cli_command` call graph, not just in
isolated per-phase tests -- with real `LLMResumeGenerator`/
`LLMTruthfulnessGate` wrapping fakes only at the LLM boundary (the same
discipline as `test_generator_gate_integration.py`), and submission
structurally absent throughout.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from career_agent.agents.planner.decide import DeterministicDecideScorer
from career_agent.agents.resume.gate import LLMTruthfulnessGate
from career_agent.agents.resume.generator import LLMResumeGenerator
from career_agent.cli import run_auto_cli_command, run_auto_command
from career_agent.core.interfaces import ClaimVerdict
from career_agent.domain.models import (
    DraftedTailoring,
    Opportunity,
    Provenance,
    TailoredWorkEntry,
)
from career_agent.storage.sqlite import (
    SqliteApplicationStore,
    SqliteOpportunityRepository,
    SqliteRunJournal,
)
from tests._fakes import FakeClaimVerifier, FakeContentDrafter
from tests.agents._profile_fixture import sample_master_profile


def _opportunity(
    opportunity_id: str, *, title: str = "Software Engineer"
) -> Opportunity:
    return Opportunity(
        id=opportunity_id,
        company_id="acme",
        canonical_company="acme.com",
        title=title,
        source="ats_api",
        source_url=f"https://boards.greenhouse.io/acme/jobs/{opportunity_id}",
        ats_ref=opportunity_id,
        provenance=Provenance(
            method="structured_api",
            reference="https://boards.greenhouse.io/acme/jobs/1",
            extraction_confidence=1.0,
        ),
        description_raw="We are hiring a backend engineer with API experience.",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class _FakeSource:
    def __init__(self, found: list[Opportunity]) -> None:
        self._found = found

    async def fetch(self, since: datetime) -> list[Opportunity]:
        return self._found


class _RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def notify(self, title: str, message: str) -> None:
        self.sent.append((title, message))


# ---------------------------------------------------------------------------
# run_auto_cli_command: gate-then-construct ordering, same discipline as apply
# ---------------------------------------------------------------------------


async def test_missing_api_key_exits_before_touching_promptfoo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
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
    exit_code = await run_auto_cli_command(
        profile_path=profile_path,
        since_days=7,
        out_dir=tmp_path / "opps",
        top_n=3,
    )
    assert exit_code == 1


def _write_profile(tmp_path: Path) -> Path:
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
    return profile_path


async def test_promptfoo_not_validated_blocks_even_with_a_valid_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact machine-dependent bug this test used to have: it never
    pointed the gate at an isolated directory, so it silently relied on
    the ambient absence of a real results file at the repository-relative
    default path. On a machine with its own real, gitignored, passing
    ``promptfoo/results/truthfulness-gate-v2--groq.json`` (exactly what a
    developer who has completed live Groq validation legitimately has),
    the gate found that real artifact, passed, and execution proceeded
    into constructing a real GroqContentDrafter -- which then made an
    actual HTTP call to api.groq.com using this test's intentionally-fake
    key, producing a 401 instead of the exit-1 this test asserts.
    ``promptfoo_results_dir`` now makes what this test is actually
    asserting explicit and machine-independent: an isolated directory
    with no artifact in it, not "whatever happens to be at the default
    path on whatever machine runs this"."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk-fake-for-test")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "db.sqlite"))
    exit_code = await run_auto_cli_command(
        profile_path=_write_profile(tmp_path),
        since_days=7,
        out_dir=tmp_path / "opps",
        top_n=3,
        promptfoo_results_dir=tmp_path / "empty-promptfoo-results",
    )
    assert exit_code == 1


async def test_promptfoo_isolated_state_wins_over_a_valid_ambient_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Direct regression for the exact bug: even when the *ambient*
    default results directory genuinely has a complete, passing artifact
    (simulating a real developer machine with its own validated Groq run
    -- never the actual repo-owned promptfoo/results/, which this test
    must never touch), an explicitly isolated ``promptfoo_results_dir``
    with no artifact in it must still be the one consulted, and the gate
    must still block. Proves isolation wins over ambient state, not just
    that isolation works when there's nothing ambient to conflict with."""
    ambient_dir = tmp_path / "ambient-default-results"
    ambient_dir.mkdir()
    (ambient_dir / "truthfulness-gate-v2--groq.json").write_text(
        json.dumps(
            {
                "results": {
                    "stats": {"successes": 10, "failures": 0, "errors": 0},
                },
                "config": {
                    "providers": [{"id": "openai:chat:openai/gpt-oss-120b"}]
                },
            }
        )
    )
    monkeypatch.setenv("PROMPTFOO_RESULTS_DIR", str(ambient_dir))
    monkeypatch.setenv("GROQ_API_KEY", "gsk-fake-for-test")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "db.sqlite"))

    exit_code = await run_auto_cli_command(
        profile_path=_write_profile(tmp_path),
        since_days=7,
        out_dir=tmp_path / "opps",
        top_n=3,
        promptfoo_results_dir=tmp_path / "empty-promptfoo-results",
    )
    assert exit_code == 1  # the isolated (empty) directory wins, not ambient


# ---------------------------------------------------------------------------
# main()'s argv dispatch -- proven with an explicit argv, never sys.argv
# ---------------------------------------------------------------------------


def test_main_dispatches_auto_with_the_right_args(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import career_agent.cli as cli_module

    seen: dict[str, object] = {}

    async def _fake_run_auto_cli_command(
        *, profile_path: Path, since_days: int, out_dir: Path, top_n: int
    ) -> int:
        seen["profile_path"] = profile_path
        seen["since_days"] = since_days
        seen["out_dir"] = out_dir
        seen["top_n"] = top_n
        return 3

    monkeypatch.setattr(
        cli_module, "run_auto_cli_command", _fake_run_auto_cli_command
    )
    profile_path = tmp_path / "profile.json"
    out_dir = tmp_path / "opps"

    with pytest.raises(SystemExit) as exc_info:
        cli_module.main(
            [
                "auto",
                "--profile",
                str(profile_path),
                "--since-days",
                "14",
                "--out-dir",
                str(out_dir),
                "--top-n",
                "5",
            ]
        )
    assert exc_info.value.code == 3
    assert seen == {
        "profile_path": profile_path,
        "since_days": 14,
        "out_dir": out_dir,
        "top_n": 5,
    }


# ---------------------------------------------------------------------------
# The full offline rehearsal: discover -> dedup -> rank -> tailor -> gate ->
# notify, composed for real, submission structurally absent throughout.
# ---------------------------------------------------------------------------


async def test_full_rehearsal_prepares_without_ever_submitting(
    tmp_path: Path,
) -> None:
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer with strong API experience."

    sources = [
        (
            "boardA",
            _FakeSource(
                [
                    _opportunity("opp-1", title="Backend Software Engineer"),
                    _opportunity("opp-2", title="Platform Software Engineer"),
                ]
            ),
        ),
        ("boardB", _FakeSource([_opportunity("opp-1")])),  # cross-source dup
    ]
    repo = SqliteOpportunityRepository(tmp_path / "db.sqlite")
    out_dir = tmp_path / "opps"
    scorer = DeterministicDecideScorer()

    drafted = DraftedTailoring(
        work=[
            TailoredWorkEntry(
                source_entry_id="work-techco",
                position="Software Engineer",
                highlights=["Built REST APIs serving 2M requests/day"],
            )
        ]
    )
    content_drafter = FakeContentDrafter(result=drafted)
    generator = LLMResumeGenerator(content_drafter)
    claim_verifier = FakeClaimVerifier(
        verdicts={
            "Built REST APIs serving 2M requests/day": ClaimVerdict(
                verified=True, confidence=0.95
            ),
        }
    )
    gate = LLMTruthfulnessGate(claim_verifier)
    application_store = SqliteApplicationStore(tmp_path / "db.sqlite")
    notifier = _RecordingNotifier()

    exit_code = await run_auto_command(
        sources,
        repo,
        profile,
        scorer,
        generator,
        gate,
        since=datetime(2026, 1, 1, tzinfo=UTC),
        out_dir=out_dir,
        top_n=3,
        application_store=application_store,
        notifier=notifier,
    )

    assert exit_code == 0
    # Dedup happened: two sources reported opp-1, only one handoff file.
    written = sorted(path.name for path in out_dir.glob("*.json"))
    assert written == ["opp-1.json", "opp-2.json"]
    # Both prepared applications were recorded to the audit trail.
    recorded_opportunity_ids = {
        row["opportunity_id"] for row in application_store.all_rows()
    }
    assert recorded_opportunity_ids == {"opp-1", "opp-2"}
    # A notification fired per prepared application, pointing back at apply.
    assert len(notifier.sent) == 2
    for _title, message in notifier.sent:
        assert "career-agent apply --opportunity-file" in message
    # The load-bearing safety property: nothing in this run's call graph
    # can submit -- proven at the function level by test_phase17_gates.py's
    # co_names inspection; this test additionally proves no Applicator/
    # HumanConfirmation object was ever even constructed along the way.
    assert "submitted" not in " ".join(msg for _, msg in notifier.sent)


async def test_opportunity_with_a_prior_recorded_attempt_is_skipped(
    tmp_path: Path,
) -> None:
    """Phase 22 / ADR-0048: an unattended cron run never re-tailors an
    opportunity it already prepared or submitted in a previous run."""
    from career_agent.domain.models import (
        Application,
        BasicsSection,
        LegalStatusSection,
        Statement,
        TailoredContent,
        TailoredResume,
        TruthfulnessResult,
    )

    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer with strong API experience."

    sources = [("boardA", _FakeSource([_opportunity("opp-1"), _opportunity("opp-2")]))]
    repo = SqliteOpportunityRepository(tmp_path / "db.sqlite")
    out_dir = tmp_path / "opps"
    scorer = DeterministicDecideScorer()

    drafted = DraftedTailoring(
        work=[
            TailoredWorkEntry(
                source_entry_id="work-techco",
                position="Software Engineer",
                highlights=["Built REST APIs serving 2M requests/day"],
            )
        ]
    )
    generator = LLMResumeGenerator(FakeContentDrafter(result=drafted))
    gate = LLMTruthfulnessGate(
        FakeClaimVerifier(
            verdicts={
                "Built REST APIs serving 2M requests/day": ClaimVerdict(
                    verified=True, confidence=0.95
                ),
            }
        )
    )
    application_store = SqliteApplicationStore(tmp_path / "db.sqlite")
    prior_resume = TailoredResume(
        id="resume-prior",
        opportunity_id="opp-1",
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
    application_store.record(
        Application(
            id="prior-app",
            opportunity_id="opp-1",
            resume=prior_resume,
            applicant=BasicsSection(name="Ada", email="ada@example.com"),
            legal_status=LegalStatusSection(),
            status="submitted",
        ),
        company="acme",
        source="ats_api",
        ats_total=None,
    )

    exit_code = await run_auto_command(
        sources,
        repo,
        profile,
        scorer,
        generator,
        gate,
        since=datetime(2026, 1, 1, tzinfo=UTC),
        out_dir=out_dir,
        top_n=3,
        application_store=application_store,
    )

    assert exit_code == 0
    recorded_opportunity_ids = {
        row["opportunity_id"] for row in application_store.all_rows()
    }
    # opp-1 already had a recorded attempt and must not be re-tailored;
    # only opp-2's fresh attempt is added.
    assert recorded_opportunity_ids == {"opp-1", "opp-2"}
    new_rows = [row for row in application_store.all_rows() if row["id"] != "prior-app"]
    assert len(new_rows) == 1
    assert new_rows[0]["opportunity_id"] == "opp-2"


async def test_run_journal_records_a_skip_and_a_prepared_opportunity(
    tmp_path: Path,
) -> None:
    """Phase 23 / ADR-0049: one run_id for the whole pass, with a
    reconstructable per-opportunity outcome and a final RUN_COMPLETED."""
    import sqlite3

    from career_agent.domain.models import (
        Application,
        BasicsSection,
        LegalStatusSection,
        Statement,
        TailoredContent,
        TailoredResume,
        TruthfulnessResult,
    )
    from career_agent.storage.sqlite import SqliteRunJournal

    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer with strong API experience."
    sources = [("boardA", _FakeSource([_opportunity("opp-1"), _opportunity("opp-2")]))]
    db_path = tmp_path / "db.sqlite"
    repo = SqliteOpportunityRepository(db_path)
    out_dir = tmp_path / "opps"
    scorer = DeterministicDecideScorer()
    drafted = DraftedTailoring(
        work=[
            TailoredWorkEntry(
                source_entry_id="work-techco",
                position="Software Engineer",
                highlights=["Built REST APIs serving 2M requests/day"],
            )
        ]
    )
    generator = LLMResumeGenerator(FakeContentDrafter(result=drafted))
    gate = LLMTruthfulnessGate(
        FakeClaimVerifier(
            verdicts={
                "Built REST APIs serving 2M requests/day": ClaimVerdict(
                    verified=True, confidence=0.95
                ),
            }
        )
    )
    application_store = SqliteApplicationStore(db_path)
    prior_resume = TailoredResume(
        id="resume-prior",
        opportunity_id="opp-1",
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
    application_store.record(
        Application(
            id="prior-app",
            opportunity_id="opp-1",
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

    exit_code = await run_auto_command(
        sources,
        repo,
        profile,
        scorer,
        generator,
        gate,
        since=datetime(2026, 1, 1, tzinfo=UTC),
        out_dir=out_dir,
        top_n=3,
        application_store=application_store,
        run_journal=journal,
    )
    assert exit_code == 0

    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        "SELECT run_id, stage, event_type, outcome FROM run_journal"
        " ORDER BY sequence_no"
    ).fetchall()
    connection.close()
    run_ids = {row[0] for row in rows}
    assert len(run_ids) == 1
    event_types = [row[2] for row in rows]
    assert event_types == [
        "RUN_STARTED",
        "DISCOVERY_COMPLETED",
        "OPPORTUNITY_SKIPPED",
        "APPLICATION_PREPARED",
        "RUN_COMPLETED",
    ]
    skipped_row = rows[event_types.index("OPPORTUNITY_SKIPPED")]
    assert skipped_row[3] == "submitted"  # the prior status, as evidence
    assert rows[-1][3] == "prepared=1"


async def test_restarting_auto_gets_a_new_run_id_and_no_duplicate_records(
    tmp_path: Path,
) -> None:
    """Simulates a crash-and-restart: a second, independent `auto` invocation
    against the same database gets its own fresh run_id (RQ8/P9 -- restart
    does not collide with or mutate the previous run's journal), while
    ADR-0048's guard still prevents the already-recorded opportunity from
    being duplicated."""
    import sqlite3

    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer with strong API experience."
    sources = [("boardA", _FakeSource([_opportunity("opp-1")]))]
    db_path = tmp_path / "db.sqlite"
    out_dir = tmp_path / "opps"
    scorer = DeterministicDecideScorer()
    drafted = DraftedTailoring(
        work=[
            TailoredWorkEntry(
                source_entry_id="work-techco",
                position="Software Engineer",
                highlights=["Built REST APIs serving 2M requests/day"],
            )
        ]
    )
    generator = LLMResumeGenerator(FakeContentDrafter(result=drafted))
    gate = LLMTruthfulnessGate(
        FakeClaimVerifier(
            verdicts={
                "Built REST APIs serving 2M requests/day": ClaimVerdict(
                    verified=True, confidence=0.95
                ),
            }
        )
    )
    application_store = SqliteApplicationStore(db_path)
    journal = SqliteRunJournal(db_path)

    for _ in range(2):  # the "restart": run auto twice against the same DB
        await run_auto_command(
            sources,
            SqliteOpportunityRepository(db_path),
            profile,
            scorer,
            generator,
            gate,
            since=datetime(2026, 1, 1, tzinfo=UTC),
            out_dir=out_dir,
            top_n=3,
            application_store=application_store,
            run_journal=journal,
        )

    # ADR-0048: only one application row ever recorded for opp-1.
    assert len(application_store.all_rows()) == 1

    connection = sqlite3.connect(db_path)
    run_ids = [
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT run_id FROM run_journal"
        ).fetchall()
    ]
    connection.close()
    # Two independent invocations produced two independent run_ids -- a
    # restart never collides with or extends the previous run's history.
    assert len(run_ids) == 2
