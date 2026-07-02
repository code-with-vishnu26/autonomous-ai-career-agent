"""Case #6 revisited (ADR-0016 correction): the generator can't write a date,
but a real one must still reach the rendered resume, resolved downstream from
the linked profile entry -- never invented, never absent.

Also ADR-0025: ``render_tailored_resume`` is the actual plain-text renderer,
tested here with the same weight as the gate's own adversarial matrix, not
as a routine formatting test -- this is the first artifact in the whole
system a human outside the project will actually read.
"""

from __future__ import annotations

from datetime import date

import pytest

from career_agent.domain.models import (
    BasicsSection,
    MasterProfile,
    ProjectEntry,
    SkillEntry,
    TailoredContent,
    TailoredProjectEntry,
    TailoredWorkEntry,
    WorkEntry,
)
from career_agent.domain.rendering import render_tailored_resume, resolve_work_dates


def _profile() -> MasterProfile:
    return MasterProfile(
        version="profile-v1",
        basics=BasicsSection(name="Ada Lovelace", email="ada@example.com"),
        work=[
            WorkEntry(
                id="work-techco",
                name="Techco",
                position="Software Engineer",
                start_date=date(2022, 1, 1),
                end_date=date(2024, 6, 30),
                highlights=[],
            )
        ],
    )


def test_resolve_work_dates_returns_the_real_profile_dates() -> None:
    entry = TailoredWorkEntry(
        source_entry_id="work-techco", position="Software Engineer", highlights=[]
    )
    start, end = resolve_work_dates(entry, _profile())
    assert start == date(2022, 1, 1)
    assert end == date(2024, 6, 30)


def test_resolve_work_dates_handles_ongoing_employment() -> None:
    profile = _profile()
    profile.work[0].end_date = None
    entry = TailoredWorkEntry(
        source_entry_id="work-techco", position="Software Engineer", highlights=[]
    )
    start, end = resolve_work_dates(entry, profile)
    assert start == date(2022, 1, 1)
    assert end is None


def test_resolve_work_dates_raises_for_an_unresolvable_entry() -> None:
    """Should never happen post-gate (blocked as employer_mismatch), but is
    not silently tolerated here either -- same discipline as the gate itself."""
    entry = TailoredWorkEntry(
        source_entry_id="work-does-not-exist", position="X", highlights=[]
    )
    with pytest.raises(KeyError, match="work-does-not-exist"):
        resolve_work_dates(entry, _profile())


# ---------------------------------------------------------------------------
# render_tailored_resume (ADR-0025) -- a realistic, multi-entry profile,
# not a single-work-entry fixture: this is what a real employer receives.
# ---------------------------------------------------------------------------


def _realistic_profile() -> MasterProfile:
    return MasterProfile(
        version="profile-v2",
        basics=BasicsSection(
            name="Ada Lovelace",
            email="ada@example.com",
            summary="Backend engineer with 5 years of distributed systems experience.",
        ),
        work=[
            WorkEntry(
                id="work-techco",
                name="Techco",
                position="Senior Software Engineer",
                start_date=date(2022, 1, 1),
                end_date=None,
                highlights=["Built REST APIs serving 2M requests/day"],
            ),
            WorkEntry(
                id="work-startupco",
                name="Startupco",
                position="Software Engineer",
                start_date=date(2019, 3, 1),
                end_date=date(2021, 12, 31),
                highlights=["Cut deployment time from 1 hour to 5 minutes"],
            ),
        ],
        skills=[
            SkillEntry(id="skill-python", name="Python"),
            SkillEntry(id="skill-postgres", name="PostgreSQL"),
        ],
        projects=[
            ProjectEntry(
                id="proj-internal",
                name="Internal Tool",
                highlights=["Built an internal deployment dashboard"],
            )
        ],
    )


def _realistic_content() -> TailoredContent:
    return TailoredContent(
        summary="Backend engineer with 5 years of distributed systems experience.",
        work=[
            TailoredWorkEntry(
                source_entry_id="work-techco",
                position="Senior Software Engineer",
                highlights=["Built REST APIs serving 2M requests/day"],
            ),
            TailoredWorkEntry(
                source_entry_id="work-startupco",
                position="Software Engineer",
                highlights=["Cut deployment time from 1 hour to 5 minutes"],
            ),
        ],
        skills=["Python", "PostgreSQL"],
        projects=[
            TailoredProjectEntry(
                source_entry_id="proj-internal",
                name="Internal Tool",
                highlights=["Built an internal deployment dashboard"],
            )
        ],
    )


def test_render_produces_a_structurally_complete_resume() -> None:
    """Not just 'does it render without crashing' -- every section a real
    employer expects must actually be present in the output."""
    profile = _realistic_profile()
    rendered = render_tailored_resume(_realistic_content(), profile)

    assert "Backend engineer with 5 years" in rendered
    assert "Senior Software Engineer" in rendered
    assert "2022-01-01 - Present" in rendered
    assert "Built REST APIs serving 2M requests/day" in rendered
    assert "Software Engineer" in rendered
    assert "2019-03-01 - 2021-12-31" in rendered
    assert "Cut deployment time from 1 hour to 5 minutes" in rendered
    assert "Python" in rendered
    assert "PostgreSQL" in rendered
    assert "Internal Tool" in rendered
    assert "Built an internal deployment dashboard" in rendered


def test_render_raises_for_an_unresolvable_work_entry_rather_than_skipping_it() -> (
    None
):
    """The core proof: the renderer is a second, independent consumer of
    source_entry_id references and must not trust the gate already ran --
    a silent skip would produce a resume quietly missing a job."""
    content = TailoredContent(
        summary="x",
        work=[
            TailoredWorkEntry(
                source_entry_id="work-does-not-exist",
                position="Staff Engineer",
                highlights=["Led a major initiative"],
            )
        ],
    )
    with pytest.raises(KeyError, match="work-does-not-exist"):
        render_tailored_resume(content, _realistic_profile())


def test_render_raises_for_an_unresolvable_project_entry_rather_than_skipping_it() -> (
    None
):
    content = TailoredContent(
        summary="x",
        projects=[
            TailoredProjectEntry(
                source_entry_id="proj-does-not-exist",
                name="Ghost Project",
                highlights=["Did something"],
            )
        ],
    )
    with pytest.raises(KeyError, match="proj-does-not-exist"):
        render_tailored_resume(content, _realistic_profile())
