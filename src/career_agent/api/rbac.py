"""Organization authorization for the dashboard API (Phase 60, ADR-0078).

Deliberately separate from ``api/security.py``: that module answers "who
is the caller" (authentication); this one answers "may the caller act
within this organization, with this role/permission" (authorization) --
the same distinction ``PermissionRequired``/``OrganizationRequired``/
``RoleRequired`` from the brief name directly. Every organization-scoped
route depends on exactly one of these, never re-implementing the
membership/role check inline -- "never duplicate route authorization."

No JWT claim carries an organization id (deliberately -- adding one would
touch every caller of ``core.security.create_access_token``/
``decode_access_token`` for a single new phase, see ADR-0078's audit
section). Instead every organization-scoped route takes
``organization_id`` as a path parameter, and authorization is a real
``SqliteMembershipStore`` lookup per request -- cheap (one indexed query,
the same cost every other per-request store lookup in this API already
pays) and always reflects the current membership/role, never a stale
claim from a 15-minute-old access token.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from career_agent.api.dependencies import get_membership_store
from career_agent.api.security import get_current_user
from career_agent.domain.roles import Permission, Role, has_permission
from career_agent.domain.team import Membership
from career_agent.domain.user import User


def require_membership(
    organization_id: str,
    current_user: User = Depends(get_current_user),
    membership_store=Depends(get_membership_store),
) -> Membership:
    """``OrganizationRequired``: the caller's own membership, or a 404.

    A 404 (not 403) for "not a member" -- the same "don't reveal whether
    the resource exists to a caller who can't see it" discipline Phase 58
    already applies to cross-user notification access.
    """
    membership = membership_store.get(
        organization_id=organization_id, user_id=current_user.id
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found.",
        )
    return membership


def require_permission(permission: Permission):
    """``PermissionRequired(permission)``: a dependency factory.

    Requires organization membership (via :func:`require_membership`)
    *and* that the member's role carries ``permission`` -- a 403 if the
    caller is a real member but their role doesn't have it.
    """

    def _dependency(
        membership: Membership = Depends(require_membership),
    ) -> Membership:
        if not has_permission(membership.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires the '{permission}' permission.",
            )
        return membership

    return _dependency


def require_role(*roles: Role):
    """``RoleRequired(*roles)``: a dependency factory.

    Requires organization membership *and* that the member's role is one
    of ``roles`` exactly -- used for the two role-gated-not-permission-
    gated actions (delete/transfer are ``owner``-only, checked by role
    directly rather than by adding a permission only one role would ever
    carry).
    """

    def _dependency(
        membership: Membership = Depends(require_membership),
    ) -> Membership:
        if membership.role not in roles:
            allowed = ", ".join(roles)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of these roles: {allowed}.",
            )
        return membership

    return _dependency
