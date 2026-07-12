"""Phase 53 (ADR-0071): the real `career-agent submit` command.

``run_submit_command`` re-tailors via the same real LLM-provider wiring
``run_apply_command``/``run_prepare_command`` use -- untestable live in
this sandbox, disclosed the same way. This file tests everything reachable
without a live provider: file-loading errors, the "no matching
ApplicationSession" precondition (checked before any LLM wiring), and the
promptfoo-gate-ordering guarantee via source inspection (mirroring
``test_apply_and_auto_gate_before_constructing_the_live_verifier``).
"""

from __future__ import annotations

import asyncio
import inspect
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import career_agent.cli as cli_module
from career_agent.cli import run_submit_command
from career_agent.domain.review import ReviewSession


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


def _profile_payload() -> dict:
    return {
        "version": "profile-v1",
        "basics": {"name": "Ada Lovelace", "email": "ada@example.com"},
    }


def _review_session() -> ReviewSession:
    return ReviewSession(
        id="review-1",
        application_session_id="sess-1",
        company="Acme Corp",
        job_title="Software Engineer",
        provider="greenhouse",
        approval_status="APPROVED",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _write(tmp_path: Path, name: str, payload: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload))
    return path


@pytest.fixture(autouse=True)
def _isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "career_agent.db"))


def test_missing_review_session_file_returns_one(tmp_path: Path) -> None:
    opportunity_path = _write(tmp_path, "opp.json", _opportunity_payload())
    profile_path = _write(tmp_path, "profile.json", _profile_payload())
    exit_code = asyncio.run(
        run_submit_command(
            review_session_path=tmp_path / "nonexistent.json",
            opportunity_path=opportunity_path,
            profile_path=profile_path,
        )
    )
    assert exit_code == 1


def test_malformed_review_session_file_returns_one(tmp_path: Path) -> None:
    review_path = tmp_path / "review.json"
    review_path.write_text("{ not valid json")
    opportunity_path = _write(tmp_path, "opp.json", _opportunity_payload())
    profile_path = _write(tmp_path, "profile.json", _profile_payload())
    exit_code = asyncio.run(
        run_submit_command(
            review_session_path=review_path,
            opportunity_path=opportunity_path,
            profile_path=profile_path,
        )
    )
    assert exit_code == 1


def test_missing_opportunity_file_returns_one(tmp_path: Path) -> None:
    review_path = tmp_path / "review.json"
    review_path.write_text(_review_session().model_dump_json())
    profile_path = _write(tmp_path, "profile.json", _profile_payload())
    exit_code = asyncio.run(
        run_submit_command(
            review_session_path=review_path,
            opportunity_path=tmp_path / "nonexistent.json",
            profile_path=profile_path,
        )
    )
    assert exit_code == 1


def test_missing_profile_file_returns_one(tmp_path: Path) -> None:
    review_path = tmp_path / "review.json"
    review_path.write_text(_review_session().model_dump_json())
    opportunity_path = _write(tmp_path, "opp.json", _opportunity_payload())
    exit_code = asyncio.run(
        run_submit_command(
            review_session_path=review_path,
            opportunity_path=opportunity_path,
            profile_path=tmp_path / "nonexistent.json",
        )
    )
    assert exit_code == 1


def test_no_matching_application_session_returns_one_before_any_llm_wiring(
    tmp_path: Path,
) -> None:
    """The "no ApplicationSession found" check runs before select_claim_verifier
    -- reachable fully offline, no live provider required."""
    review_path = tmp_path / "review.json"
    review_path.write_text(_review_session().model_dump_json())
    opportunity_path = _write(tmp_path, "opp.json", _opportunity_payload())
    profile_path = _write(tmp_path, "profile.json", _profile_payload())
    exit_code = asyncio.run(
        run_submit_command(
            review_session_path=review_path,
            opportunity_path=opportunity_path,
            profile_path=profile_path,
        )
    )
    assert exit_code == 1


def test_gates_before_constructing_the_live_verifier() -> None:
    """Mirrors test_apply_and_auto_gate_before_constructing_the_live_verifier
    (Phase 28, ADR-0054). Phase 63 extracted this ordering guarantee out of
    ``run_submit_command`` into ``submit_prepared_application`` (now shared
    with the web API's submission endpoint, ADR-0081) -- this test moved
    with the logic it verifies."""
    src = inspect.getsource(cli_module.submit_prepared_application)
    assert "select_claim_verifier" in src
    assert "verify_promptfoo_results" in src
    assert src.index("verify_promptfoo_results") < src.index(
        "LLMResumeGenerator"
    ), "submit_prepared_application: promptfoo gate must precede verifier construction"


def test_no_application_session_check_precedes_llm_wiring() -> None:
    """Structural proof: the ApplicationSession lookup (and its refusal path)
    textually precedes the handoff to ``submit_prepared_application`` --
    where all LLM-provider wiring now lives (Phase 63) -- so a wrong/missing
    session is caught before any LLM provider is ever touched."""
    src = inspect.getsource(cli_module.run_submit_command)
    assert src.index("SqliteApplicationSessionStore(") < src.index(
        "submit_prepared_application("
    )
