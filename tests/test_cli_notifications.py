"""Phase 58 (ADR-0077): CLI commands create real in-app notifications.

``prepare``/``review``/``submit`` already have their own end-to-end
command tests (``test_cli_review.py``, ``test_cli_submit.py``); this file
only proves the notification side effect Phase 58 added on top -- that a
real ``Notification`` row lands in ``SqliteNotificationStore`` for the
CLI's local operator account, never silently skipped or fabricated.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from career_agent.cli import run_review_command
from career_agent.core.config import Settings
from career_agent.storage.sqlite import SqliteNotificationStore, migrate_to_multi_user


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


def _operator_user_id() -> str:
    settings = Settings()
    return migrate_to_multi_user(
        Path(settings.database_path),
        default_operator_email=settings.cli_local_user_email,
    )


def test_approving_a_review_creates_a_review_approved_notification(
    tmp_path: Path,
) -> None:
    session_path = _write_session_file(tmp_path)
    exit_code = run_review_command(session_path=session_path, input_fn=lambda _: "y")
    assert exit_code == 0

    user_id = _operator_user_id()
    notifications = SqliteNotificationStore(
        Path(os.environ["DATABASE_PATH"])
    ).by_user(user_id)
    assert any(n.category == "review_approved" for n in notifications)
    assert any(n.type == "SUCCESS" for n in notifications)


def test_rejecting_a_review_creates_a_review_rejected_notification(
    tmp_path: Path,
) -> None:
    session_path = _write_session_file(tmp_path)
    exit_code = run_review_command(session_path=session_path, input_fn=lambda _: "n")
    assert exit_code == 0

    user_id = _operator_user_id()
    notifications = SqliteNotificationStore(
        Path(os.environ["DATABASE_PATH"])
    ).by_user(user_id)
    assert any(n.category == "review_rejected" for n in notifications)


def test_cancelling_a_review_creates_no_notification(tmp_path: Path) -> None:
    def _interrupt(_: str) -> str:
        raise KeyboardInterrupt

    session_path = _write_session_file(tmp_path)
    exit_code = run_review_command(session_path=session_path, input_fn=_interrupt)
    assert exit_code == 0

    user_id = _operator_user_id()
    notifications = SqliteNotificationStore(
        Path(os.environ["DATABASE_PATH"])
    ).by_user(user_id)
    assert notifications == []
