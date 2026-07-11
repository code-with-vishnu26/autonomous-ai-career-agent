"""Phase 52 (ADR-0070): the real `career-agent review` command.

Fully offline -- no LLM/network/browser involved at all, unlike
apply/prepare, so this exercises the real, end-to-end command, not just
file-loading behavior.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from career_agent.cli import run_review_command
from career_agent.domain.application_session import ApplicationSession
from career_agent.storage.sqlite import SqliteReviewSessionStore


def _session_payload(**overrides: object) -> dict:
    payload = {
        "id": "sess-1",
        "provider": "greenhouse",
        "company": "Acme Corp",
        "job_title": "Backend Engineer",
        "url": "https://boards.greenhouse.io/acme/jobs/1",
        "opportunity_id": "opp-1",
        "status": "READY_FOR_REVIEW",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
    }
    payload.update(overrides)
    return payload


def _write_session_file(tmp_path: Path, **overrides: object) -> Path:
    path = tmp_path / "session.json"
    path.write_text(json.dumps(_session_payload(**overrides)))
    return path


@pytest.fixture(autouse=True)
def _isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "career_agent.db"))


def test_approving_returns_zero_and_persists_a_review(tmp_path: Path) -> None:
    session_path = _write_session_file(tmp_path)
    exit_code = run_review_command(session_path=session_path, input_fn=lambda _: "y")
    assert exit_code == 0
    store = SqliteReviewSessionStore(Path(os.environ["DATABASE_PATH"]))
    reviews = store.by_application_session("sess-1")
    assert len(reviews) == 1
    assert reviews[0].approval_status == "APPROVED"


def test_rejecting_returns_zero_and_persists_a_rejection(tmp_path: Path) -> None:
    session_path = _write_session_file(tmp_path)
    exit_code = run_review_command(session_path=session_path, input_fn=lambda _: "n")
    assert exit_code == 0
    store = SqliteReviewSessionStore(Path(os.environ["DATABASE_PATH"]))
    reviews = store.by_application_session("sess-1")
    assert reviews[0].approval_status == "REJECTED"


def test_cancelling_persists_cancelled(tmp_path: Path) -> None:
    def _interrupt(_: str) -> str:
        raise KeyboardInterrupt

    session_path = _write_session_file(tmp_path)
    exit_code = run_review_command(session_path=session_path, input_fn=_interrupt)
    assert exit_code == 0
    store = SqliteReviewSessionStore(Path(os.environ["DATABASE_PATH"]))
    reviews = store.by_application_session("sess-1")
    assert reviews[0].approval_status == "CANCELLED"


def test_missing_session_file_returns_one(tmp_path: Path) -> None:
    exit_code = run_review_command(
        session_path=tmp_path / "nonexistent.json", input_fn=lambda _: "y"
    )
    assert exit_code == 1


def test_malformed_session_file_returns_one(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text("{ not valid json")
    exit_code = run_review_command(session_path=path, input_fn=lambda _: "y")
    assert exit_code == 1


def test_invalid_session_schema_returns_one(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text(json.dumps({"id": "sess-1"}))  # missing required fields
    exit_code = run_review_command(session_path=path, input_fn=lambda _: "y")
    assert exit_code == 1


def test_the_loaded_session_round_trips_correctly(tmp_path: Path) -> None:
    """Canary: the file `prepare` writes is exactly what `review` can load."""
    session = ApplicationSession(
        id="sess-2",
        provider="lever",
        company="Globex",
        job_title="Platform Engineer",
        url="https://jobs.lever.co/globex/1",
        opportunity_id="opp-2",
        status="READY_FOR_REVIEW",
        uploaded_files=["/tmp/resume.docx"],
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    path = tmp_path / "session.json"
    path.write_text(session.model_dump_json())
    exit_code = run_review_command(session_path=path, input_fn=lambda _: "y")
    assert exit_code == 0
    store = SqliteReviewSessionStore(Path(os.environ["DATABASE_PATH"]))
    reviews = store.by_application_session("sess-2")
    assert reviews[0].company == "Globex"
