"""Phase 57 (ADR-0075): Skill Gap Analysis ranks missing skills with a named reason."""

from __future__ import annotations

from career_agent.agents.coach.skill_gap import skill_gap_report


def test_skill_gap_report_ranks_and_explains_missing_skills() -> None:
    jd = "Requires Kubernetes and strong Communication skills."
    report = skill_gap_report("I have no relevant experience listed here.", jd)
    assert report.qualifies_percent < 100
    assert report.missing_skills[0].keyword == "Kubernetes"
    assert "hard skill" in report.missing_skills[0].reason.lower()


def test_skill_gap_report_full_match_has_no_gaps() -> None:
    report = skill_gap_report("I know Python.", "Looking for a Python developer.")
    assert report.qualifies_percent == 100.0
    assert report.missing_skills == []
