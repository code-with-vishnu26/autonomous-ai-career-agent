"""Phase 57 (ADR-0075): deterministic resume-vs-JD analysis primitives."""

from __future__ import annotations

from career_agent.domain.coach_analysis import (
    find_formatting_issues,
    find_weak_bullets,
    learning_priority,
    score_coverage,
)


def test_score_coverage_full_match_scores_100() -> None:
    jd = "We need a Python engineer with Docker experience."
    resume = "Built services in Python and shipped them with Docker."
    result = score_coverage(resume, jd)
    assert result.score == 100.0
    assert {m.keyword for m in result.matched} == {"Python", "Docker"}
    assert result.missing == []


def test_score_coverage_partial_match_lists_missing() -> None:
    jd = "We need a Python engineer with Kubernetes experience."
    resume = "I write Python code."
    result = score_coverage(resume, jd)
    assert 0 < result.score < 100
    assert [m.keyword for m in result.missing] == ["Kubernetes"]


def test_score_coverage_no_jd_keywords_scores_100() -> None:
    result = score_coverage("anything", "no taxonomy terms here at all")
    assert result.score == 100.0


def test_find_weak_bullets_flags_missing_verb_and_metric() -> None:
    resume = "Responsible for stuff without any numbers in it at all here"
    issues = find_weak_bullets(resume)
    assert len(issues) == 1
    assert "action verb" in issues[0].reason


def test_find_weak_bullets_accepts_strong_bullet() -> None:
    resume = "Led a team of 5 engineers to ship the new checkout flow"
    assert find_weak_bullets(resume) == []


def test_find_weak_bullets_skips_short_lines() -> None:
    assert find_weak_bullets("Summary") == []


def test_find_formatting_issues_flags_empty_resume() -> None:
    issues = find_formatting_issues("   ")
    assert any("empty" in issue.reason.lower() for issue in issues)


def test_find_formatting_issues_flags_missing_email() -> None:
    issues = find_formatting_issues("Just some text with no contact info.")
    assert any("email" in issue.reason.lower() for issue in issues)


def test_find_formatting_issues_clean_resume_has_no_issues() -> None:
    resume = "Contact: person@example.com\nLed the migration to Docker."
    assert find_formatting_issues(resume) == []


def test_learning_priority_ranks_hard_before_soft() -> None:
    from career_agent.domain.ats_scoring import MissingKeyword

    missing = [
        MissingKeyword(keyword="Communication", kind="soft"),
        MissingKeyword(keyword="Kubernetes", kind="hard"),
    ]
    ranked = learning_priority(missing, "Needs Communication and Kubernetes skills.")
    assert ranked[0].keyword == "Kubernetes"


def test_learning_priority_breaks_ties_by_first_jd_appearance() -> None:
    from career_agent.domain.ats_scoring import MissingKeyword

    missing = [
        MissingKeyword(keyword="Go", kind="hard"),
        MissingKeyword(keyword="Rust", kind="hard"),
    ]
    ranked = learning_priority(missing, "Must know Rust well. Go is a plus.")
    assert [item.keyword for item in ranked] == ["Rust", "Go"]
