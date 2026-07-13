"""Render a :class:`MasterProfile` to plain résumé text (Phase 66, ADR-0084).

The deterministic keyword-coverage scorer (`domain/coach_analysis.py`,
ADR-0075) works on a résumé *text* blob -- the Career Coach pages have
always fed it text the user pasted. This renders the same text from a
stored :class:`MasterProfile` instead, so a dashboard user who onboarded
(Phase 64) can score their profile against a job without re-typing it.

Pure and lossy by design: it flattens the structured profile into the
words a keyword scorer cares about (summaries, position titles,
highlights, skill names/keywords, project descriptions), not a formatted
document. It is *not* a résumé generator -- tailoring (`prepare`) remains
the real, LLM-backed artifact pipeline; this is only the input to a
keyword match.
"""

from __future__ import annotations

from career_agent.domain.models import MasterProfile


def master_profile_to_resume_text(profile: MasterProfile) -> str:
    """Flatten ``profile`` into the plain text a keyword scorer consumes.

    Sections are joined with blank lines and list items with newlines --
    the coverage scorer tokenizes on the whole blob, so structure only has
    to preserve the *words*, not any layout. Empty/absent fields are
    skipped so a sparse profile never injects blank noise.
    """
    lines: list[str] = []

    if profile.basics.summary:
        lines.append(profile.basics.summary)

    for work in profile.work:
        header = f"{work.position} at {work.name}".strip()
        if header:
            lines.append(header)
        lines.extend(work.highlights)

    for project in profile.projects:
        if project.name:
            lines.append(project.name)
        if project.description:
            lines.append(project.description)
        lines.extend(project.highlights)
        if project.keywords:
            lines.append(", ".join(project.keywords))

    for skill in profile.skills:
        parts = [skill.name, *skill.keywords]
        joined = ", ".join(part for part in parts if part)
        if joined:
            lines.append(joined)

    for education in profile.education:
        parts = [education.study_type, education.area, education.institution]
        joined = " ".join(part for part in parts if part)
        if joined:
            lines.append(joined)

    return "\n".join(lines)
