"""Stable, source-independent identity for discovered opportunities.

Pure functions, zero I/O -- lives in ``domain`` and is enforced dependency-free
by import-linter. These are the backbone of deduplication: the same real job
must resolve to the same identity no matter which source discovered it, so that
a re-poll (or, later, the same role arriving from a web search) collapses to one
:class:`~career_agent.domain.models.Opportunity` rather than many.

Two distinct notions, deliberately separated:

- :func:`opportunity_id` -- an *exact* idempotency key. When an ATS-native
  identity is available (e.g. ``greenhouse:{board}:{job_id}``) it is used, since
  that is the source's own ground truth and distinguishes two genuinely
  different reqs that happen to share a title. This is what makes re-polling a
  source safe.
- :func:`canonical_fingerprint` -- a *source-independent* match key derived only
  from company + normalized title + normalized location. It carries no
  ATS-specific data, so a Greenhouse posting and the same role found later on a
  company career page (Phase 4c) produce the *same* fingerprint. This is the
  cross-source backbone; it is defined now, with one source, precisely so it is
  proven not to be Greenhouse-shaped before 4b/4c depend on it.
"""

from __future__ import annotations

import hashlib
import re

_WHITESPACE = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")


def normalize(text: str) -> str:
    """Lower-case, strip punctuation, and collapse whitespace.

    Deterministic and stable: the unit of normalization every identity key is
    built from. Empty/whitespace input normalizes to the empty string.
    """
    lowered = text.casefold().strip()
    without_punct = _NON_ALNUM.sub(" ", lowered)
    return _WHITESPACE.sub(" ", without_punct).strip()


def canonical_fingerprint(
    company: str, title: str, location: str | None
) -> str:
    """Return a source-independent fingerprint for a role.

    Built only from company, title, and location -- never from any ATS's
    internal job id -- so every representation of the same posting (ATS API,
    career page, web search) collapses to one value. Location is optional; a
    missing location contributes an empty component rather than changing the
    other fields' positions.
    """
    parts = [normalize(company), normalize(title), normalize(location or "")]
    return "|".join(parts)


def opportunity_id(
    *,
    ats_kind: str | None,
    board_token: str | None,
    ats_ref: str | None,
    company: str,
    title: str,
    location: str | None,
) -> str:
    """Return a stable idempotency id for an opportunity.

    Prefers the ATS-native identity (``{ats_kind}:{board_token}:{ats_ref}``)
    when all three are present, because it is the source's ground truth and
    will not over-merge two distinct reqs that share a title. Falls back to the
    :func:`canonical_fingerprint` when there is no ATS identity (e.g. a raw
    career-page find). The basis string is hashed so the id is fixed-width and
    opaque, but always deterministic for the same inputs.
    """
    if ats_kind and board_token and ats_ref:
        basis = f"{ats_kind}:{board_token}:{ats_ref}"
    else:
        basis = canonical_fingerprint(company, title, location)
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
