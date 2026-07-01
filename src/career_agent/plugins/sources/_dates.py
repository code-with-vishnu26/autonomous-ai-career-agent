"""Shapeless datetime helpers shared across opportunity sources.

Only source-*agnostic* datetime coercion lives here -- deliberately NOT a shared
normalization base. Field mapping (which JSON key holds the title, the location,
the timestamp, and in what shape) stays private to each source, so sources
remain independent and one ATS's assumptions can never leak into another. If
this module ever grows anything that knows about a specific source's payload,
that logic belongs back in that source.
"""

from __future__ import annotations

from datetime import UTC, datetime


def as_utc(value: datetime) -> datetime:
    """Return ``value`` as an aware UTC datetime (assume UTC if naive)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
