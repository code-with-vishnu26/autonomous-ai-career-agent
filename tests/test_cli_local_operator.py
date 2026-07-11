"""Phase 56 (ADR-0074): the CLI's fixed local-operator account.

``career-agent prepare``/``review``/``submit`` have no login flow -- they
always operate as one auto-provisioned account
(``Settings.cli_local_user_email``), resolved via
``migrate_to_multi_user`` at the start of each command. This proves that
resolution actually happens and that what gets persisted is owned by that
real account, not left ownerless.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from career_agent.cli import run_review_command
from career_agent.core.config import Settings
from career_agent.storage.sqlite import SqliteReviewSessionStore, SqliteUserStore


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


@pytest.fixture(autouse=True)
def _isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "career_agent.db"))


def test_review_command_provisions_and_owns_data_as_the_local_operator(
    tmp_path: Path,
) -> None:
    session_path = tmp_path / "session.json"
    session_path.write_text(json.dumps(_session_payload()))

    exit_code = run_review_command(session_path=session_path, input_fn=lambda _: "y")
    assert exit_code == 0

    db_path = Path(os.environ["DATABASE_PATH"])
    settings = Settings()
    operator = SqliteUserStore(db_path).by_email(settings.cli_local_user_email)
    assert operator is not None

    reviews = SqliteReviewSessionStore(db_path).by_user(operator.id)
    assert [r.id for r in reviews] == [
        r.id for r in SqliteReviewSessionStore(db_path).by_application_session("sess-1")
    ]
    assert len(reviews) == 1


def test_review_command_is_idempotent_across_repeated_invocations(
    tmp_path: Path,
) -> None:
    """Running a second command doesn't create a second operator account."""
    session_path = tmp_path / "session.json"
    session_path.write_text(json.dumps(_session_payload()))
    run_review_command(session_path=session_path, input_fn=lambda _: "y")

    session_path_2 = tmp_path / "session2.json"
    session_path_2.write_text(json.dumps(_session_payload(id="sess-2")))
    run_review_command(session_path=session_path_2, input_fn=lambda _: "n")

    db_path = Path(os.environ["DATABASE_PATH"])
    settings = Settings()
    operator = SqliteUserStore(db_path).by_email(settings.cli_local_user_email)
    reviews = SqliteReviewSessionStore(db_path).by_user(operator.id)
    assert len(reviews) == 2
