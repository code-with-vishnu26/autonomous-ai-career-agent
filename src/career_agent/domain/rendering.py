"""Read-only rendering helpers for tailored content (ADR-0016 correction).

``TailoredWorkEntry`` has no date field, so the generator can never write a
fabricated one -- that structural guarantee is unchanged. But a resume with no
employment dates is not one a recruiter or ATS parser will accept, so the real
dates still have to reach the rendered output. They do, from here: resolved
downstream, directly from the linked :class:`~career_agent.domain.models.
WorkEntry`, never from a field the generator controls. This is the "generator
cannot write it, but a real value still reaches the resume" shape the earlier
field-removal alone did not provide -- see ADR-0016's "Case #6 revisited" note.
"""

from __future__ import annotations

from datetime import date

from .models import MasterProfile, TailoredWorkEntry


def resolve_work_dates(
    entry: TailoredWorkEntry, profile: MasterProfile
) -> tuple[date, date | None]:
    """Return the real ``(start_date, end_date)`` for a tailored work entry.

    Looked up by ``entry.source_entry_id`` against ``profile.work`` -- never
    read from ``entry`` itself, which has nowhere to carry a date at all. By
    the time a resume reaches rendering it has already passed the
    truthfulness gate, which blocks a ``source_entry_id`` absent from the
    profile as ``employer_mismatch``, so the ``KeyError`` below should never
    fire in practice; it is not silently tolerated here either.
    """
    for work in profile.work:
        if work.id == entry.source_entry_id:
            return work.start_date, work.end_date
    raise KeyError(
        f"no WorkEntry with id={entry.source_entry_id!r} in profile "
        f"version={profile.version!r}"
    )
