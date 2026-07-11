"""User account (Phase 56, ADR-0074): pure data, no hashing/JWT logic here.

Mirrors every prior domain model's discipline (``ApplicationSession``,
``ReviewSession``, ``SubmissionResult``): a plain, storage-agnostic
Pydantic model. Password hashing and token creation/verification are pure
functions in :mod:`career_agent.core.security`, kept separate so this module
can be imported (e.g. by the API's response schemas) without ever pulling
in ``bcrypt``/``jwt``.

``hashed_password`` intentionally lives on this model (not split into a
separate "credentials" type) -- the same "the object carries what it is"
pattern this project already uses elsewhere -- but every FastAPI response
model built from a ``User`` excludes it explicitly (see ``api/schemas.py``),
never by accident of a missing field list.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

#: Deliberately simple (not RFC 5322-complete) -- good enough to reject
#: obvious garbage without adding an ``email-validator`` dependency this
#: project didn't otherwise need. The only thing that actually proves an
#: email address works is receiving mail at it, which this phase doesn't
#: attempt (Phase 58 Notifications is where real delivery lives).
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

#: - ``user``: default role. Can only ever see their own data.
#: - ``admin``: no elevated data access is wired yet (every route still
#:   filters by the caller's own ``user_id``) -- this exists so the schema
#:   doesn't need a breaking change when an admin capability is actually
#:   built, the same "declared, not yet enforced" discipline
#:   ``JobPreferences`` used for its own not-yet-wired fields (ADR-0064).
UserRole = Literal["user", "admin"]


class User(BaseModel):
    """One account. ``email`` is the login identifier, unique per account."""

    id: str
    email: str
    hashed_password: str
    display_name: str | None = None
    role: UserRole = "user"
    created_at: datetime

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _EMAIL_PATTERN.match(normalized):
            raise ValueError(f"not a valid email address: {value!r}")
        return normalized
