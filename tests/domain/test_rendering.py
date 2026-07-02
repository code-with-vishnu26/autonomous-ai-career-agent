"""Case #6 revisited (ADR-0016 correction): the generator can't write a date,
but a real one must still reach the rendered resume, resolved downstream from
the linked profile entry -- never invented, never absent.
"""

from __future__ import annotations

from datetime import date

import pytest

from career_agent.domain.models import (
    BasicsSection,
    MasterProfile,
    TailoredWorkEntry,
    WorkEntry,
)
from career_agent.domain.rendering import resolve_work_dates


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
