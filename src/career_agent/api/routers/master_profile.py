"""Per-user Master Profile endpoints (Phase 64, ADR-0082).

Mirrors ``/user/preferences``'s exact shape (``GET`` returns the caller's
own stored value or a sensible empty default; ``PUT`` replaces it wholesale)
for :class:`~career_agent.domain.models.MasterProfile` -- the JSON-Resume-
shaped source of truth `career-agent prepare`/`submit`/`apply`/`auto`
already build against, now given a real per-user database store
(:class:`~career_agent.storage.sqlite.SqliteMasterProfileStore`) alongside
the CLI's unmodified file-based loader (``storage.profile``, ADR-0000/
ADR-0078: the CLI itself stays single-operator).

Deliberately a separate router/file from ``user.py``, not folded into its
existing ``PUT /user/profile`` -- that endpoint's own docstring already
draws this exact distinction ("account profile" vs. "what is true about
the candidate") and this phase preserves it rather than reopening it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from career_agent.api.dependencies import get_master_profile_store
from career_agent.api.security import get_current_user
from career_agent.domain.models import (
    BasicsSection,
    EducationEntry,
    LegalStatusSection,
    MasterProfile,
    ProjectEntry,
    SkillEntry,
    WorkEntry,
)
from career_agent.domain.user import User

router = APIRouter(prefix="/user/master-profile", tags=["master-profile"])


class MasterProfileUpdate(BaseModel):
    """Body for ``PUT /user/master-profile``.

    Omits ``version`` deliberately -- it is always server-computed (the
    same content hash ``career-agent prepare``'s file loader has always
    used, :func:`~career_agent.storage.profile.compute_profile_version`),
    never client-supplied, so a stale or fabricated client-side version
    can never masquerade as the real one.
    """

    basics: BasicsSection
    work: list[WorkEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    skills: list[SkillEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    legal_status: LegalStatusSection = Field(default_factory=LegalStatusSection)


@router.get("", response_model=MasterProfile | None)
def get_master_profile(
    current_user: User = Depends(get_current_user),
    master_profile_store=Depends(get_master_profile_store),
) -> MasterProfile | None:
    """The caller's stored profile, or ``None`` if never onboarded.

    Never a fabricated empty-name placeholder, since ``basics.name``/
    ``basics.email`` are required, non-empty facts.
    """
    return master_profile_store.get(current_user.id)


@router.put("", response_model=MasterProfile)
def update_master_profile(
    body: MasterProfileUpdate,
    current_user: User = Depends(get_current_user),
    master_profile_store=Depends(get_master_profile_store),
) -> MasterProfile:
    """Replace the caller's stored Master Profile wholesale.

    Same id-stability guarantee the CLI's file loader has always enforced
    (every ``work``/``education``/``skills``/``projects`` entry needs a
    stable, unique ``id``) -- ``SqliteMasterProfileStore.save`` raises
    :class:`~career_agent.storage.profile.ProfileValidationError` (a 500,
    surfaced via the API's existing unhandled-exception handler) rather
    than silently accepting an invalid profile; the frontend wizard
    generates a real id per entry client-side so this is never actually
    hit in normal use.
    """
    profile = MasterProfile(version="pending", **body.model_dump(mode="json"))
    return master_profile_store.save(current_user.id, profile)
