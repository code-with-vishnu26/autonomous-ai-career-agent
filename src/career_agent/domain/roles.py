"""Organization roles and permissions (Phase 60, ADR-0078).

Pure data -- a fixed ``Role -> frozenset[Permission]`` mapping, not a
database-configurable table. Every organization uses the exact same five
roles; there is no per-organization custom-role feature in this phase
(not requested, and would be real, unrequested complexity). Kept in
``domain/`` because it is exactly what ``domain/user.py``'s own
``UserRole`` already is: a closed set of labels with no I/O, no bcrypt,
no JWT -- the same purity `import-linter`'s "domain depends on nothing
else" contract already enforces for every other domain module.

This is deliberately a *second*, separate role concept from
``domain.user.UserRole`` (``"user" | "admin"``): that one is a
platform-wide account flag (unused today beyond `require_admin`
scaffolding); this one is scoped to one ``Organization`` at a time via
``Membership.role`` (``domain/team.py``) -- the same "account profile vs.
per-context role" distinction most real multi-tenant systems draw.
"""

from __future__ import annotations

from typing import Literal, get_args

#: - ``owner``: created the organization (or was transferred ownership).
#:   Exactly one owner per organization at any time.
#: - ``admin``: full management access except deleting the organization
#:   or transferring ownership.
#: - ``recruiter``: day-to-day pipeline access (search/prepare/review/
#:   submit) plus analytics, no user/billing management.
#: - ``member``: day-to-day pipeline access only.
#: - ``viewer``: read-only.
Role = Literal["owner", "admin", "recruiter", "member", "viewer"]

ROLES: tuple[Role, ...] = get_args(Role)

Permission = Literal[
    "view_dashboard",
    "run_searches",
    "prepare_resume",
    "review",
    "submit",
    "manage_users",
    "manage_billing",
    "view_analytics",
    "manage_notification_settings",
    "delete_organization",
    "transfer_ownership",
    "invite_users",
    "suspend_users",
]

_MEMBER_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        "view_dashboard",
        "run_searches",
        "prepare_resume",
        "review",
        "submit",
        "manage_notification_settings",
    }
)
_RECRUITER_PERMISSIONS: frozenset[Permission] = _MEMBER_PERMISSIONS | {
    "view_analytics",
}
_ADMIN_PERMISSIONS: frozenset[Permission] = _RECRUITER_PERMISSIONS | {
    "manage_users",
    "manage_billing",
    "invite_users",
    "suspend_users",
}
_OWNER_PERMISSIONS: frozenset[Permission] = _ADMIN_PERMISSIONS | {
    "delete_organization",
    "transfer_ownership",
}

#: The single source of truth every ``PermissionRequired``/``RoleRequired``
#: check reads from -- never duplicated inline at a call site.
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    "owner": _OWNER_PERMISSIONS,
    "admin": _ADMIN_PERMISSIONS,
    "recruiter": _RECRUITER_PERMISSIONS,
    "member": _MEMBER_PERMISSIONS,
    "viewer": frozenset({"view_dashboard", "view_analytics"}),
}


def has_permission(role: Role, permission: Permission) -> bool:
    """Whether ``role`` carries ``permission``, per the fixed mapping above."""
    return permission in ROLE_PERMISSIONS[role]
