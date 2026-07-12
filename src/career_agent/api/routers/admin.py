"""Platform-superadmin endpoints (Phase 60, ADR-0078).

Gated by ``api.security.require_admin`` -- ``User.role == "admin"``, the
account-level flag Phase 56 declared ("forward compatibility... nothing
in this phase actually grants a route admin-only access yet") and left
unused ever since. This is its first real caller. Deliberately distinct
from organization roles (``owner``/``admin``/etc., ``domain/roles.py``):
this is a platform operator looking across every organization, not a
member of any particular one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from career_agent.api.dependencies import (
    get_membership_store,
    get_organization_store,
    get_user_store,
)
from career_agent.api.security import require_admin
from career_agent.domain.user import User

router = APIRouter(prefix="/api/admin", tags=["admin"])


class AdminOrganizationOut(BaseModel):
    """One organization, as seen by a platform admin."""

    id: str
    name: str
    slug: str
    member_count: int


class AdminMemberOut(BaseModel):
    """One organization member, as seen by a platform admin."""

    user_id: str
    email: str
    role: str


@router.get("/organizations", response_model=list[AdminOrganizationOut])
def list_all_organizations(
    _admin: User = Depends(require_admin),
    organization_store=Depends(get_organization_store),
    membership_store=Depends(get_membership_store),
) -> list[AdminOrganizationOut]:
    """Every organization on the platform -- a real, minimal admin surface.

    No pagination/search -- kept intentionally simple rather than adding
    scope this phase's brief never asked for.
    """
    return [
        AdminOrganizationOut(
            id=organization.id,
            name=organization.name,
            slug=organization.slug,
            member_count=len(membership_store.by_organization(organization.id)),
        )
        for organization in organization_store.all_organizations()
    ]


@router.get(
    "/organizations/{organization_id}/members", response_model=list[AdminMemberOut]
)
def list_organization_members(
    organization_id: str,
    _admin: User = Depends(require_admin),
    membership_store=Depends(get_membership_store),
    user_store=Depends(get_user_store),
) -> list[AdminMemberOut]:
    """Any organization's members -- support/ops visibility, not a member action."""
    members = []
    for membership in membership_store.by_organization(organization_id):
        user = user_store.by_id(membership.user_id)
        if user is None:
            continue
        members.append(
            AdminMemberOut(user_id=user.id, email=user.email, role=membership.role)
        )
    return members
