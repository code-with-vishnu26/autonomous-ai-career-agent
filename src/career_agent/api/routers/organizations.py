"""Organization endpoints (Phase 60, ADR-0078).

``GET``/``POST /organizations`` need no organization-scoped authorization
(there's nothing to scope to yet, or the caller is listing their own
memberships); every other route requires real membership via
``api.rbac``'s dependencies -- never an inline check.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from career_agent.api.audit import record_audit
from career_agent.api.dependencies import (
    get_audit_log_store,
    get_membership_store,
    get_organization_store,
)
from career_agent.api.rbac import require_membership, require_permission
from career_agent.api.security import get_current_user
from career_agent.domain.organization import Organization
from career_agent.domain.team import Membership
from career_agent.domain.user import User
from career_agent.organizations import slugify, unique_slug

router = APIRouter(prefix="/organizations", tags=["organizations"])


class OrganizationOut(BaseModel):
    """One organization plus the caller's own role in it."""

    id: str
    name: str
    slug: str
    role: str


class CreateOrganizationRequest(BaseModel):
    """Body for ``POST /organizations``."""

    name: str


class RenameOrganizationRequest(BaseModel):
    """Body for ``PATCH /organizations/{organization_id}``."""

    name: str


@router.get("", response_model=list[OrganizationOut])
def list_my_organizations(
    current_user: User = Depends(get_current_user),
    organization_store=Depends(get_organization_store),
    membership_store=Depends(get_membership_store),
) -> list[OrganizationOut]:
    """Every organization the caller belongs to, with their role in each."""
    memberships = membership_store.by_user(current_user.id)
    result = []
    for membership in memberships:
        organization = organization_store.get(membership.organization_id)
        if organization is None:
            continue
        result.append(
            OrganizationOut(
                id=organization.id,
                name=organization.name,
                slug=organization.slug,
                role=membership.role,
            )
        )
    return result


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def create_organization(
    body: CreateOrganizationRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    organization_store=Depends(get_organization_store),
    membership_store=Depends(get_membership_store),
    audit_log_store=Depends(get_audit_log_store),
) -> OrganizationOut:
    """Create a brand-new organization -- the caller becomes its owner."""
    now = datetime.now(UTC)
    organization = Organization(
        id=str(uuid.uuid4()),
        name=body.name,
        slug=unique_slug(slugify(body.name), organization_store=organization_store),
        created_by_user_id=current_user.id,
        created_at=now,
    )
    organization_store.create(organization)
    membership_store.create(
        Membership(
            id=str(uuid.uuid4()),
            organization_id=organization.id,
            user_id=current_user.id,
            role="owner",
            joined_at=now,
        )
    )
    record_audit(
        request=request,
        organization_id=organization.id,
        user_id=current_user.id,
        action="organization_created",
        result="ok",
        audit_log_store=audit_log_store,
        now=now,
    )
    return OrganizationOut(
        id=organization.id, name=organization.name, slug=organization.slug, role="owner"
    )


@router.get("/{organization_id}", response_model=OrganizationOut)
def get_organization(
    organization_id: str,
    organization_store=Depends(get_organization_store),
    membership: Membership = Depends(require_membership),
) -> OrganizationOut:
    """One organization the caller is a member of."""
    organization = organization_store.get(organization_id)
    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found."
        )
    return OrganizationOut(
        id=organization.id,
        name=organization.name,
        slug=organization.slug,
        role=membership.role,
    )


@router.patch("/{organization_id}", response_model=OrganizationOut)
def rename_organization(
    organization_id: str,
    body: RenameOrganizationRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    organization_store=Depends(get_organization_store),
    audit_log_store=Depends(get_audit_log_store),
    membership: Membership = Depends(require_permission("manage_users")),
) -> OrganizationOut:
    """Rename an organization -- requires ``manage_users`` (admin/owner)."""
    updated = organization_store.rename(organization_id, name=body.name)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found."
        )
    record_audit(
        request=request,
        organization_id=organization_id,
        user_id=current_user.id,
        action="organization_renamed",
        result="ok",
        audit_log_store=audit_log_store,
    )
    return OrganizationOut(
        id=updated.id, name=updated.name, slug=updated.slug, role=membership.role
    )


@router.delete("/{organization_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization(
    organization_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    organization_store=Depends(get_organization_store),
    audit_log_store=Depends(get_audit_log_store),
    _membership: Membership = Depends(require_permission("delete_organization")),
) -> None:
    """Delete an organization outright -- requires ``delete_organization`` (owner)."""
    organization_store.delete(organization_id)
    record_audit(
        request=request,
        organization_id=organization_id,
        user_id=current_user.id,
        action="organization_deleted",
        result="ok",
        audit_log_store=audit_log_store,
    )
