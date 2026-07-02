"""ATS URL pattern classification (ADR-0015, ADR-0019).

A single, shared source of truth for "does this URL look like a Greenhouse /
Lever / Ashby posting" -- originally built for ``SearchOpportunitySource``
(ADR-0015: a matched URL is a strong signal, confirmed by re-parsing, never
trusted on shape alone) and reused as-is here for ATS-kind resolution
(``agents/apply/applicator.py``, ADR-0019) rather than re-implemented. Pure
pattern matching, no I/O -- belongs in ``domain`` alongside the project's
other dependency-free business rules.
"""

from __future__ import annotations

import re

# (ats_kind, pattern) -- pattern captures (board_or_company, job_id)
ATS_URL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("greenhouse", re.compile(r"boards\.greenhouse\.io/([^/]+)/jobs/([^/?#]+)")),
    ("lever", re.compile(r"jobs\.lever\.co/([^/]+)/([^/?#]+)")),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([^/]+)/([^/?#]+)")),
]


def match_ats_url(url: str) -> tuple[str, str, str] | None:
    """Match ``url`` against a known ATS pattern.

    Returns ``(ats_kind, board_or_company, job_id)``, or ``None`` if nothing
    matches. A match is a strong signal, not a confirmed posting or a
    confirmed submission target -- callers that need a stronger guarantee
    (a real posting exists, a real submission endpoint exists) must confirm
    it themselves, the same way ``SearchOpportunitySource`` re-parses via the
    real ATS source rather than trusting the URL shape alone.
    """
    for ats_kind, pattern in ATS_URL_PATTERNS:
        match = pattern.search(url)
        if match:
            return ats_kind, match.group(1), match.group(2)
    return None


def resolve_ats_kind(url: str) -> str | None:
    """Return just the ``ats_kind`` component of :func:`match_ats_url`."""
    match = match_ats_url(url)
    return match[0] if match else None
