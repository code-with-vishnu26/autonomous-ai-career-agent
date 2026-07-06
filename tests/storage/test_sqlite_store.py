"""Phase 13 / ADR-0037: SQLite persistence.

The repository fidelity suite runs the SAME contract scenarios as the
in-memory implementation's tests -- two-key dedup exactly (ADR-0014) --
plus the one thing memory can't prove: survival across a real close and
reopen of the database file.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from career_agent.core.interfaces import OpportunityRepository
from career_agent.domain.models import (
    Application,
    BasicsSection,
    LegalStatusSection,
    Opportunity,
    Provenance,
    Statement,
    TailoredContent,
    TailoredResume,
    TruthfulnessResult,
)
from career_agent.storage.excel import export_applications
from career_agent.storage.sqlite import (
    SqliteApplicationStore,
    SqliteOpportunityRepository,
)


def _opp(
    opportunity_id: str = "id-1",
    *,
    canonical_company: str = "acme",
    title: str = "Engineer",
    location: str | None = None,
    ats_ref: str | None = None,
) -> Opportunity:
    return Opportunity(
        id=opportunity_id,
        company_id="acme",
        canonical_company=canonical_company,
        title=title,
        source="ats_api",
        source_url="https://example.invalid/1",
        provenance=Provenance(
            method="structured_api",
            reference="https://example.invalid/api/1",
            extraction_confidence=1.0,
        ),
        ats_ref=ats_ref,
        location=location,
        description_raw="",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_sqlite_repo_satisfies_the_contract(tmp_path: Path) -> None:
    assert isinstance(
        SqliteOpportunityRepository(tmp_path / "db.sqlite"), OpportunityRepository
    )


def test_sqlite_repo_exposes_only_the_contract_methods(tmp_path: Path) -> None:
    """Same fidelity guard as the in-memory impl: add + get, nothing more."""
    public = {
        name
        for name in vars(SqliteOpportunityRepository)
        if not name.startswith("_")
    }
    assert public == {"add", "get"}


async def test_add_is_idempotent_by_id(tmp_path: Path) -> None:
    repo = SqliteOpportunityRepository(tmp_path / "db.sqlite")
    assert await repo.add(_opp("id-1")) is True
    assert await repo.add(_opp("id-1")) is False


async def test_non_authoritative_fingerprint_match_is_a_cross_source_dupe(
    tmp_path: Path,
) -> None:
    repo = SqliteOpportunityRepository(tmp_path / "db.sqlite")
    assert await repo.add(_opp("id-1", ats_ref="native-1")) is True
    # Same company/title/location, no native id -> cross-source duplicate.
    assert await repo.add(_opp("id-2", ats_ref=None)) is False


async def test_two_authoritative_reqs_sharing_a_fingerprint_stay_separate(
    tmp_path: Path,
) -> None:
    repo = SqliteOpportunityRepository(tmp_path / "db.sqlite")
    assert await repo.add(_opp("id-1", ats_ref="native-1")) is True
    assert await repo.add(_opp("id-2", ats_ref="native-2")) is True  # no over-merge


async def test_round_trip_survives_close_and_reopen(tmp_path: Path) -> None:
    """The one guarantee memory can't provide: real persistence."""
    db = tmp_path / "db.sqlite"
    first = SqliteOpportunityRepository(db)
    stored = _opp("id-1", ats_ref="native-1")
    assert await first.add(stored) is True
    del first

    reopened = SqliteOpportunityRepository(db)
    loaded = await reopened.get("id-1")
    assert loaded == stored  # full model equality, not just presence
    assert await reopened.add(stored) is False  # dedup state persisted too


def _application(app_id: str = "app-1") -> Application:
    resume = TailoredResume(
        id="resume-1",
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
    return Application(
        id=app_id,
        opportunity_id="opp-1",
        resume=resume,
        applicant=BasicsSection(name="Ada", email="ada@example.com"),
        legal_status=LegalStatusSection(),
        status="pending",
    )


def test_application_store_is_append_only_and_exports_to_excel(
    tmp_path: Path,
) -> None:
    store = SqliteApplicationStore(tmp_path / "db.sqlite")
    store.record(_application(), company="acme", source="job_board", ats_total=81.5)
    # Re-recording the same id never overwrites (append-only discipline).
    store.record(_application(), company="CHANGED", source="job_board", ats_total=1.0)
    rows = store.all_rows()
    assert len(rows) == 1
    assert rows[0]["company"] == "acme"
    assert rows[0]["ats_total"] == 81.5
    assert rows[0]["latest_outcome"] is None

    store.record_outcome("app-1", "interview", "onsite")
    rows = store.all_rows()
    assert rows[0]["latest_outcome"] == "interview:onsite"
    assert store.outcome_rows()[0]["kind"] == "interview"

    written = export_applications(rows, tmp_path / "out" / "apps.xlsx")
    from openpyxl import load_workbook

    sheet = load_workbook(written).active
    header = [cell.value for cell in sheet[1]]
    assert "Company" in header
    assert "ATS Score" in header
    values = [cell.value for cell in sheet[2]]
    assert "acme" in values
    assert "approved" in values  # truthfulness rendered readable
    assert "interview:onsite" in values


def _application_with(
    app_id: str, opportunity_id: str, status: str
) -> Application:
    application = _application(app_id)
    return application.model_copy(
        update={"opportunity_id": opportunity_id, "status": status}
    )


def test_prior_attempt_status_is_none_when_nothing_recorded(tmp_path: Path) -> None:
    store = SqliteApplicationStore(tmp_path / "db.sqlite")
    assert store.prior_attempt_status("opp-never-attempted") is None


def test_prior_attempt_status_ignores_rejected_attempts(tmp_path: Path) -> None:
    """A truthfulness-rejected attempt had no external side effect (ADR-0003)."""
    store = SqliteApplicationStore(tmp_path / "db.sqlite")
    store.record(
        _application_with("app-1", "opp-1", "rejected"),
        company="acme",
        source="job_board",
        ats_total=None,
    )
    assert store.prior_attempt_status("opp-1") is None


def test_prior_attempt_status_reports_non_rejected_statuses(tmp_path: Path) -> None:
    store = SqliteApplicationStore(tmp_path / "db.sqlite")
    store.record(
        _application_with("app-1", "opp-1", "submitted"),
        company="acme",
        source="job_board",
        ats_total=None,
    )
    assert store.prior_attempt_status("opp-1") == "submitted"
