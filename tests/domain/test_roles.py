"""Phase 60 (ADR-0078): fixed Role -> Permission mapping."""

from __future__ import annotations

from career_agent.domain.roles import ROLE_PERMISSIONS, ROLES, has_permission


def test_every_role_has_a_permission_set():
    for role in ROLES:
        assert role in ROLE_PERMISSIONS
        assert isinstance(ROLE_PERMISSIONS[role], frozenset)


def test_owner_has_every_permission_admin_has():
    assert ROLE_PERMISSIONS["admin"] <= ROLE_PERMISSIONS["owner"]


def test_admin_has_every_permission_recruiter_has():
    assert ROLE_PERMISSIONS["recruiter"] <= ROLE_PERMISSIONS["admin"]


def test_recruiter_has_every_permission_member_has():
    assert ROLE_PERMISSIONS["member"] <= ROLE_PERMISSIONS["recruiter"]


def test_only_owner_can_delete_organization():
    for role in ROLES:
        expected = role == "owner"
        assert has_permission(role, "delete_organization") == expected


def test_only_owner_can_transfer_ownership():
    for role in ROLES:
        expected = role == "owner"
        assert has_permission(role, "transfer_ownership") == expected


def test_viewer_cannot_submit():
    assert has_permission("viewer", "submit") is False


def test_member_can_submit():
    assert has_permission("member", "submit") is True


def test_owner_and_admin_can_manage_billing():
    assert has_permission("owner", "manage_billing") is True
    assert has_permission("admin", "manage_billing") is True
    assert has_permission("recruiter", "manage_billing") is False
    assert has_permission("member", "manage_billing") is False
    assert has_permission("viewer", "manage_billing") is False
