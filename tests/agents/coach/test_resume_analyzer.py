"""Phase 57 (ADR-0075): Resume Analysis combines the deterministic checks."""

from __future__ import annotations

from career_agent.agents.coach.resume_analyzer import analyze_resume


def test_analyze_resume_combines_coverage_bullets_and_formatting() -> None:
    jd = "We need a Python engineer with Docker experience."
    resume = "Responsible for stuff without any numbers at all in this line"
    result = analyze_resume(resume, jd)
    assert result.ats_score < 100
    missing = {m.keyword for m in result.missing_keywords}
    assert "Docker" in missing or "Python" in missing
    assert len(result.weak_bullets) == 1
    assert any("email" in issue.reason.lower() for issue in result.formatting_issues)
