"""Audit-log read endpoint (Phase 60, ADR-0078).

Named ``audit_log.py`` (not ``audit.py``) to avoid shadowing
``career_agent.api.audit`` -- the write-side recording helper every
mutating route already depends on. Read-only, gated by ``manage_users``
(the same permission that already gates seeing/managing the team --
"who did what to my team" is squarely that same oversight capability).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from career_agent.api.dependencies import get_audit_log_store
from career_agent.api.rbac import require_permission
from career_agent.domain.team import Membership

router = APIRouter(prefix="/api/audit", tags=["audit"])


class AuditLogEntryOut(BaseModel):
    """One recorded mutation."""

    id: str
    user_id: str
    action: str
    result: str
    ip_address: str | None
    created_at: str


@router.get("/{organization_id}", response_model=list[AuditLogEntryOut])
def list_audit_log(
    organization_id: str,
    audit_log_store=Depends(get_audit_log_store),
    _membership: Membership = Depends(require_permission("manage_users")),
) -> list[AuditLogEntryOut]:
    """The most recent audit-log entries for one organization, newest first."""
    return [
        AuditLogEntryOut(
            id=entry.id,
            user_id=entry.user_id,
            action=entry.action,
            result=entry.result,
            ip_address=entry.ip_address,
            created_at=entry.created_at.isoformat(),
        )
        for entry in audit_log_store.by_organization(organization_id)
    ]
