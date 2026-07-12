"""Team endpoints: membership, invitations (Phase 60, ADR-0078).

Every organization-scoped route depends on ``api.rbac``'s
``require_permission``/``require_membership`` -- never an inline role
check. ``POST /team/invite/accept`` is deliberately the one flat,
non-organization-scoped route here: the caller isn't a member of the
organization *yet* -- accepting is how they become one.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from career_agent.api.audit import record_audit
from career_agent.api.dependencies import (
    get_audit_log_store,
    get_delivery_attempt_store,
    get_invitation_store,
    get_membership_store,
    get_notification_preferences_store,
    get_notification_store,
    get_organization_store,
    get_settings,
    get_subscription_store,
    get_user_store,
    get_webhook_subscription_store,
)
from career_agent.api.rbac import require_membership, require_permission
from career_agent.api.security import get_current_user
from career_agent.billing import seat_limit_exceeded
from career_agent.core.config import Settings
from career_agent.domain.roles import Role
from career_agent.domain.team import Invitation, Membership
from career_agent.domain.user import User
from career_agent.invitations import (
    InvitationError,
    accept_invitation,
    create_invitation,
    send_invitation,
)
from career_agent.scheduler import build_email_sender

router = APIRouter(prefix="/team", tags=["team"])


class MemberOut(BaseModel):
    """One organization member."""

    user_id: str
    email: str
    display_name: str | None
    role: Role


class UpdateRoleRequest(BaseModel):
    """Body for ``PATCH /team/{organization_id}/members/{user_id}``."""

    role: Role


class InviteRequest(BaseModel):
    """Body for ``POST /team/{organization_id}/invite``."""

    email: str
    role: Role


class InvitationOut(BaseModel):
    """One invitation, safe to show the inviting organization -- never the raw token."""

    id: str
    email: str
    role: Role
    status: str
    created_at: str
    expires_at: str


class AcceptInvitationRequest(BaseModel):
    """Body for ``POST /team/invite/accept``."""

    token: str


@router.get("/{organization_id}", response_model=list[MemberOut])
def list_members(
    organization_id: str,
    membership_store=Depends(get_membership_store),
    user_store=Depends(get_user_store),
    _membership: Membership = Depends(require_membership),
) -> list[MemberOut]:
    """Every member of one organization."""
    members = []
    for membership in membership_store.by_organization(organization_id):
        user = user_store.by_id(membership.user_id)
        if user is None:
            continue
        members.append(
            MemberOut(
                user_id=user.id,
                email=user.email,
                display_name=user.display_name,
                role=membership.role,
            )
        )
    return members


@router.patch("/{organization_id}/members/{user_id}", response_model=MemberOut)
def update_member_role(
    organization_id: str,
    user_id: str,
    body: UpdateRoleRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    membership_store=Depends(get_membership_store),
    user_store=Depends(get_user_store),
    audit_log_store=Depends(get_audit_log_store),
    _membership: Membership = Depends(require_permission("manage_users")),
) -> MemberOut:
    """Change a member's role -- requires ``manage_users``."""
    updated = membership_store.update_role(
        organization_id=organization_id, user_id=user_id, role=body.role
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Member not found."
        )
    target_user = user_store.by_id(user_id)
    record_audit(
        request=request,
        organization_id=organization_id,
        user_id=current_user.id,
        action=f"member_role_changed:{user_id}:{body.role}",
        result="ok",
        audit_log_store=audit_log_store,
    )
    return MemberOut(
        user_id=user_id,
        email=target_user.email if target_user else "",
        display_name=target_user.display_name if target_user else None,
        role=body.role,
    )


@router.delete(
    "/{organization_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_member(
    organization_id: str,
    user_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    membership_store=Depends(get_membership_store),
    audit_log_store=Depends(get_audit_log_store),
    _membership: Membership = Depends(require_permission("suspend_users")),
) -> None:
    """Remove (suspend) a member -- requires ``suspend_users``."""
    removed = membership_store.remove(organization_id=organization_id, user_id=user_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Member not found."
        )
    record_audit(
        request=request,
        organization_id=organization_id,
        user_id=current_user.id,
        action=f"member_removed:{user_id}",
        result="ok",
        audit_log_store=audit_log_store,
    )


@router.post(
    "/{organization_id}/invite",
    response_model=InvitationOut,
    status_code=status.HTTP_201_CREATED,
)
async def invite_member(
    organization_id: str,
    body: InviteRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    invitation_store=Depends(get_invitation_store),
    membership_store=Depends(get_membership_store),
    organization_store=Depends(get_organization_store),
    subscription_store=Depends(get_subscription_store),
    user_store=Depends(get_user_store),
    notification_store=Depends(get_notification_store),
    notification_preferences_store=Depends(get_notification_preferences_store),
    delivery_store=Depends(get_delivery_attempt_store),
    webhook_store=Depends(get_webhook_subscription_store),
    audit_log_store=Depends(get_audit_log_store),
    settings: Settings = Depends(get_settings),
    _membership: Membership = Depends(require_permission("invite_users")),
) -> InvitationOut:
    """Invite someone by email.

    Requires ``invite_users``; blocked past the plan's seat limit.
    """
    now = datetime.now(UTC)
    if seat_limit_exceeded(
        organization_id=organization_id,
        subscription_store=subscription_store,
        membership_store=membership_store,
        now=now,
    ):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                "This organization is at its plan's seat limit. "
                "Upgrade to invite more."
            ),
        )
    organization = organization_store.get(organization_id)
    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found."
        )
    invitation, raw_token = create_invitation(
        organization_id=organization_id,
        invited_by_user_id=current_user.id,
        email=body.email,
        role=body.role,
        invitation_store=invitation_store,
        now=now,
    )
    await send_invitation(
        invitation=invitation,
        raw_token=raw_token,
        organization=organization,
        invite_base_url=f"{settings.frontend_base_url}/accept-invite",
        email_sender=build_email_sender(settings),
        user_store=user_store,
        notification_store=notification_store,
        notification_preferences_store=notification_preferences_store,
        delivery_store=delivery_store,
        webhook_store=webhook_store,
        now=now,
    )
    record_audit(
        request=request,
        organization_id=organization_id,
        user_id=current_user.id,
        action=f"invitation_sent:{invitation.email}",
        result="ok",
        audit_log_store=audit_log_store,
        now=now,
    )
    return _invitation_out(invitation, now=now)


@router.get("/{organization_id}/invitations", response_model=list[InvitationOut])
def list_invitations(
    organization_id: str,
    invitation_store=Depends(get_invitation_store),
    _membership: Membership = Depends(require_permission("invite_users")),
) -> list[InvitationOut]:
    """Every invitation ever sent for one organization -- requires ``invite_users``."""
    now = datetime.now(UTC)
    return [
        _invitation_out(invitation, now=now)
        for invitation in invitation_store.by_organization(organization_id)
    ]


@router.delete(
    "/{organization_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_invitation(
    organization_id: str,
    invitation_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    invitation_store=Depends(get_invitation_store),
    audit_log_store=Depends(get_audit_log_store),
    _membership: Membership = Depends(require_permission("invite_users")),
) -> None:
    """Revoke a pending invitation -- requires ``invite_users``."""
    revoked = invitation_store.revoke(invitation_id, revoked_at=datetime.now(UTC))
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found."
        )
    record_audit(
        request=request,
        organization_id=organization_id,
        user_id=current_user.id,
        action=f"invitation_revoked:{invitation_id}",
        result="ok",
        audit_log_store=audit_log_store,
    )


@router.post(
    "/{organization_id}/invitations/{invitation_id}/resend",
    response_model=InvitationOut,
)
async def resend_invitation(
    organization_id: str,
    invitation_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    invitation_store=Depends(get_invitation_store),
    organization_store=Depends(get_organization_store),
    user_store=Depends(get_user_store),
    notification_store=Depends(get_notification_store),
    notification_preferences_store=Depends(get_notification_preferences_store),
    delivery_store=Depends(get_delivery_attempt_store),
    webhook_store=Depends(get_webhook_subscription_store),
    audit_log_store=Depends(get_audit_log_store),
    settings: Settings = Depends(get_settings),
    _membership: Membership = Depends(require_permission("invite_users")),
) -> InvitationOut:
    """Revoke a still-pending invitation and send a brand new one in its place."""
    now = datetime.now(UTC)
    old = invitation_store.get(invitation_id)
    if old is None or old.status(now=now) != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending invitation with that id.",
        )
    organization = organization_store.get(organization_id)
    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found."
        )
    invitation_store.revoke(invitation_id, revoked_at=now)
    invitation, raw_token = create_invitation(
        organization_id=organization_id,
        invited_by_user_id=old.invited_by_user_id,
        email=old.email,
        role=old.role,
        invitation_store=invitation_store,
        now=now,
    )
    await send_invitation(
        invitation=invitation,
        raw_token=raw_token,
        organization=organization,
        invite_base_url=f"{settings.frontend_base_url}/accept-invite",
        email_sender=build_email_sender(settings),
        user_store=user_store,
        notification_store=notification_store,
        notification_preferences_store=notification_preferences_store,
        delivery_store=delivery_store,
        webhook_store=webhook_store,
        now=now,
    )
    record_audit(
        request=request,
        organization_id=organization_id,
        user_id=current_user.id,
        action=f"invitation_resent:{invitation.email}",
        result="ok",
        audit_log_store=audit_log_store,
        now=now,
    )
    return _invitation_out(invitation, now=now)


@router.post("/invite/accept", response_model=MemberOut)
def accept_invite(
    body: AcceptInvitationRequest,
    current_user: User = Depends(get_current_user),
    invitation_store=Depends(get_invitation_store),
    membership_store=Depends(get_membership_store),
) -> MemberOut:
    """Redeem an invitation token into real organization membership."""
    try:
        membership = accept_invitation(
            token=body.token,
            user_id=current_user.id,
            user_email=current_user.email,
            invitation_store=invitation_store,
            membership_store=membership_store,
            now=datetime.now(UTC),
        )
    except InvitationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_INVITATION_ERROR_DETAIL[exc.reason],
        ) from exc
    return MemberOut(
        user_id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        role=membership.role,
    )


_INVITATION_ERROR_DETAIL = {
    "not_found": "Invalid or unknown invitation token.",
    "not_pending": "This invitation is no longer pending.",
    "email_mismatch": "This invitation was sent to a different email address.",
    "already_member": "You are already a member of this organization.",
}


def _invitation_out(invitation: Invitation, *, now: datetime) -> InvitationOut:
    return InvitationOut(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        status=invitation.status(now=now),
        created_at=invitation.created_at.isoformat(),
        expires_at=invitation.expires_at.isoformat(),
    )
