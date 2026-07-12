"""Phase 57 (ADR-0075): Job Match Score wraps the deterministic coverage check."""

from __future__ import annotations

from career_agent.agents.coach.job_match import job_match_score


def test_job_match_score_reflects_coverage() -> None:
    result = job_match_score("I know Python.", "Looking for a Python developer.")
    assert result.match_score == 100.0
    assert result.missing_keywords == []
