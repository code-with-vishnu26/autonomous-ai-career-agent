"""Phase 53 (ADR-0071): SqliteSubmissionResultStore -- append-only, same
discipline as every other store in storage/sqlite.py."""

from __future__ import annotations

from pathlib import Path

from career_agent.domain.submission import SubmissionResult
from career_agent.storage.sqlite import SqliteSubmissionResultStore


def _result(
    id_: str, opportunity_id: str = "opp-1", **overrides: object
) -> SubmissionResult:
    fields = {
        "id": id_,
        "application_session_id": "sess-1",
        "review_session_id": "review-1",
        "opportunity_id": opportunity_id,
        "provider": "greenhouse",
        "company": "Acme Corp",
        "job_title": "Backend Engineer",
        "submitted": False,
        "status": "REFUSED",
    }
    fields.update(overrides)
    return SubmissionResult(**fields)


def test_save_then_by_opportunity_round_trips(tmp_path: Path) -> None:
    store = SqliteSubmissionResultStore(tmp_path / "db.sqlite")
    result = _result("sub-1")
    store.save(result)
    assert store.by_opportunity("opp-1") == [result]


def test_by_opportunity_only_returns_matching(tmp_path: Path) -> None:
    store = SqliteSubmissionResultStore(tmp_path / "db.sqlite")
    store.save(_result("sub-1", opportunity_id="opp-1"))
    store.save(_result("sub-2", opportunity_id="opp-2"))
    assert [r.id for r in store.by_opportunity("opp-1")] == ["sub-1"]
    assert [r.id for r in store.by_opportunity("opp-2")] == ["sub-2"]


def test_by_opportunity_unknown_returns_empty(tmp_path: Path) -> None:
    store = SqliteSubmissionResultStore(tmp_path / "db.sqlite")
    assert store.by_opportunity("nonexistent") == []


def test_save_is_append_only_never_overwrites(tmp_path: Path) -> None:
    store = SqliteSubmissionResultStore(tmp_path / "db.sqlite")
    original = _result("sub-1", status="REFUSED")
    store.save(original)
    mutated = original.model_copy(update={"status": "SUBMITTED", "submitted": True})
    store.save(mutated)
    result = store.by_opportunity("opp-1")
    assert len(result) == 1
    assert result[0].status == "REFUSED"


def test_all_results_returns_every_opportunity(tmp_path: Path) -> None:
    store = SqliteSubmissionResultStore(tmp_path / "db.sqlite")
    store.save(_result("sub-1", opportunity_id="opp-1"))
    store.save(_result("sub-2", opportunity_id="opp-2"))
    ids = {r.id for r in store.all_results()}
    assert ids == {"sub-1", "sub-2"}


def test_survives_close_and_reopen(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite"
    SqliteSubmissionResultStore(path).save(_result("sub-1"))
    reopened = SqliteSubmissionResultStore(path)
    assert [r.id for r in reopened.by_opportunity("opp-1")] == ["sub-1"]


def test_export_submissions_writes_a_formatted_filterable_sheet(
    tmp_path: Path,
) -> None:
    from openpyxl import load_workbook

    from career_agent.storage.excel import export_submissions

    results = [_result("sub-1", status="SUBMITTED", submitted=True)]
    written = export_submissions(results, tmp_path / "out" / "submissions.xlsx")
    sheet = load_workbook(written).active
    header = [cell.value for cell in sheet[1]]
    assert "Company" in header
    assert "Status" in header
    assert sheet.auto_filter.ref is not None
