"""Organization: the tenant boundary for the dashboard (Phase 60, ADR-0078).

Every dashboard account belongs to at least one ``Organization`` --
usually a personal one auto-created at registration, so "every user
belongs to an organization" holds without a forced org-creation step.
Pure data, mirroring ``domain/user.py``'s own discipline: no bcrypt/JWT/
DB import, ``import-linter``'s "domain depends on nothing else" contract
enforced the same way.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, field_validator

#: Lowercase, hyphen-separated, URL-safe -- the same shape a personal
#: organization's auto-generated slug already produces from an email
#: local-part (see ``agents/organizations/organization_service.py``).
_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class Organization(BaseModel):
    """One tenant: a name, a unique slug, and who created it."""

    id: str
    name: str
    slug: str
    created_by_user_id: str
    created_at: datetime

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _SLUG_PATTERN.match(normalized):
            raise ValueError(f"not a valid organization slug: {value!r}")
        return normalized
