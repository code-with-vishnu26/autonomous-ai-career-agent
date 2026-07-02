"""The one MasterProfile fixture the truthfulness-gate matrix is built against.

Mirrors the HN fixture's approach: a single, realistic profile that
instantiates every archetype in the reviewer-defined adversarial matrix, rather
than a bespoke profile per case.
"""

from __future__ import annotations

from datetime import date

from career_agent.domain.models import (
    BasicsSection,
    MasterProfile,
    ProjectEntry,
    SkillEntry,
    WorkEntry,
)


def sample_master_profile() -> MasterProfile:
    """A profile covering all 12 adversarial matrix cases."""
    return MasterProfile(
        version="profile-v1",
        basics=BasicsSection(name="Ada Lovelace", email="ada@example.com"),
        work=[
            WorkEntry(
                id="work-techco",
                name="Techco",
                position="Software Engineer",
                start_date=date(2022, 1, 1),
                end_date=None,
                highlights=[
                    "Built REST APIs serving 2M requests/day",
                    "Cut pipeline runtime 40%",
                ],
            )
        ],
        skills=[
            SkillEntry(id="skill-python", name="Python"),
            SkillEntry(id="skill-django", name="Django"),
            SkillEntry(id="skill-postgres", name="PostgreSQL"),
            SkillEntry(id="skill-docker", name="Docker"),
        ],
        projects=[
            ProjectEntry(
                id="proj-internal",
                name="Internal Tool",
                highlights=["Built an internal tool"],
            )
        ],
    )
