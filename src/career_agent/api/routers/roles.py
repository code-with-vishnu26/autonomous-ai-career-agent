"""Role/permission reference endpoints (Phase 60, ADR-0078).

Pure reference data -- the fixed ``ROLE_PERMISSIONS`` mapping, exposed
read-only so the frontend's roles editor never hardcodes its own copy of
what each role can do. Requires authentication only (any logged-in
caller), never organization membership -- this is the same static
information regardless of which organization asks for it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from career_agent.api.security import get_current_user
from career_agent.domain.roles import ROLE_PERMISSIONS, ROLES
from career_agent.domain.user import User

router = APIRouter(prefix="/api/roles", tags=["roles"])


class RolePermissions(BaseModel):
    """One role and the exact permissions it carries."""

    role: str
    permissions: list[str]


@router.get("", response_model=list[RolePermissions])
def list_roles(
    _current_user: User = Depends(get_current_user),
) -> list[RolePermissions]:
    """Every organization role and its fixed permission set."""
    return [
        RolePermissions(role=role, permissions=sorted(ROLE_PERMISSIONS[role]))
        for role in ROLES
    ]


@router.get("/permissions", response_model=list[str])
def list_permissions(_current_user: User = Depends(get_current_user)) -> list[str]:
    """Every permission that exists, regardless of which role carries it."""
    all_permissions: set[str] = set()
    for permissions in ROLE_PERMISSIONS.values():
        all_permissions |= permissions
    return sorted(all_permissions)
