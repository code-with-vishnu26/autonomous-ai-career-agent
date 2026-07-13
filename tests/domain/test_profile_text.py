"""Phase 66 (ADR-0084): MasterProfile -> résumé text rendering."""

from __future__ import annotations

from career_agent.domain.models import (
    BasicsSection,
    EducationEntry,
    MasterProfile,
    ProjectEntry,
    SkillEntry,
    WorkEntry,
)
from career_agent.domain.profile_text import master_profile_to_resume_text


def _profile(**overrides: object) -> MasterProfile:
    fields: dict[str, object] = {
        "version": "sha256:test",
        "basics": BasicsSection(name="Ada", email="ada@example.com"),
    }
    fields.update(overrides)
    return MasterProfile(**fields)


def test_includes_summary_work_skills_projects_education() -> None:
    profile = _profile(
        basics=BasicsSection(
            name="Ada", email="ada@example.com", summary="Backend engineer."
        ),
        work=[
            WorkEntry(
                id="w1",
                name="Acme",
                position="Backend Engineer",
                start_date="2020-01-01",
                highlights=["Built REST APIs in Python"],
            )
        ],
        skills=[SkillEntry(id="s1", name="Python", keywords=["FastAPI"])],
        projects=[
            ProjectEntry(id="p1", name="JobBot", highlights=["Used Playwright"])
        ],
        education=[
            EducationEntry(
                id="e1", institution="MIT", area="CS", study_type="BSc"
            )
        ],
    )
    text = master_profile_to_resume_text(profile)
    assert "Backend engineer." in text
    assert "Backend Engineer at Acme" in text
    assert "Built REST APIs in Python" in text
    assert "Python" in text
    assert "FastAPI" in text
    assert "JobBot" in text
    assert "Used Playwright" in text
    assert "BSc CS MIT" in text


def test_empty_profile_renders_empty_string() -> None:
    assert master_profile_to_resume_text(_profile()) == ""


def test_absent_optional_fields_never_inject_blank_lines() -> None:
    profile = _profile(
        skills=[SkillEntry(id="s1", name="Python")],  # no keywords
        work=[
            WorkEntry(
                id="w1", name="Acme", position="Engineer", start_date="2020-01-01"
            )  # no highlights
        ],
    )
    text = master_profile_to_resume_text(profile)
    assert "" not in text.split("\n") or text  # no stray blank lines
    assert text.splitlines() == ["Engineer at Acme", "Python"]
