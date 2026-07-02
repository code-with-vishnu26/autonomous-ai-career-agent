"""Read-only rendering helpers for tailored content (ADR-0016 correction, ADR-0025).

``TailoredWorkEntry`` has no date field, so the generator can never write a
fabricated one -- that structural guarantee is unchanged. But a resume with no
employment dates is not one a recruiter or ATS parser will accept, so the real
dates still have to reach the rendered output. They do, from here: resolved
downstream, directly from the linked :class:`~career_agent.domain.models.
WorkEntry`, never from a field the generator controls. This is the "generator
cannot write it, but a real value still reaches the resume" shape the earlier
field-removal alone did not provide -- see ADR-0016's "Case #6 revisited" note.

``render_tailored_resume`` (ADR-0025) is the actual plain-text renderer
:class:`~career_agent.domain.models.TailoredContent`'s own docstring names as
future work ("rendering this to plain text... is a downstream renderer's job,
not this model's"). It is a **second, independent consumer** of
``source_entry_id`` references -- it must not assume the truthfulness gate
already ran and already blocked an unresolvable entry. It raises loudly
(``KeyError``, via :func:`resolve_work_dates` for work entries and its own
check for projects) rather than silently omitting a work/project entry it
cannot resolve: a silently-dropped entry would produce a resume that is
quietly *incomplete*, with no signal to anyone that something was missing --
worse than a loud crash, and the same "never trust that upstream already
verified this" discipline as ``HeldCandidateSink`` and the gate itself.
"""

from __future__ import annotations

from datetime import date

from .models import MasterProfile, TailoredContent, TailoredWorkEntry


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


def _format_date_range(start: date, end: date | None) -> str:
    end_label = end.isoformat() if end is not None else "Present"
    return f"{start.isoformat()} - {end_label}"


def render_tailored_resume(content: TailoredContent, profile: MasterProfile) -> str:
    """Render ``content`` to plain text, resolving real dates from ``profile``.

    Raises :class:`KeyError` if any work or project entry's
    ``source_entry_id`` cannot be resolved against ``profile`` -- never
    silently drops the entry. This function does not assume the
    truthfulness gate already ran; it independently verifies every
    reference it renders.
    """
    lines: list[str] = [content.summary, ""]

    if content.work:
        lines.append("Experience")
        lines.append("-" * len("Experience"))
        for entry in content.work:
            start, end = resolve_work_dates(entry, profile)
            lines.append(f"{entry.position} ({_format_date_range(start, end)})")
            lines.extend(f"- {highlight}" for highlight in entry.highlights)
            lines.append("")

    if content.skills:
        lines.append("Skills")
        lines.append("-" * len("Skills"))
        lines.append(", ".join(content.skills))
        lines.append("")

    if content.projects:
        lines.append("Projects")
        lines.append("-" * len("Projects"))
        project_ids = {project.id for project in profile.projects}
        for entry in content.projects:
            if entry.source_entry_id not in project_ids:
                raise KeyError(
                    f"no ProjectEntry with id={entry.source_entry_id!r} in "
                    f"profile version={profile.version!r}"
                )
            lines.append(entry.name)
            lines.extend(f"- {highlight}" for highlight in entry.highlights)
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"
