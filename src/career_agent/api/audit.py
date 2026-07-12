"""Audit-log recording helper for the dashboard API (Phase 60, ADR-0078).

One place every organization-mutating route calls into -- never inlines
its own ``AuditLogEntry`` construction -- so "user, organization, action,
timestamp, IP, result" is always captured the same way. Recording is
best-effort: a failure to write the audit row must never fail the real
action it's describing (the same "notify, never gate" precedent ADR-0005
already established for notifications, applied here to observability
instead of delivery).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import Request

from career_agent.domain.audit import AuditLogEntry
from career_agent.storage.audit_store import SqliteAuditLogStore

logger = logging.getLogger(__name__)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def record_audit(
    *,
    request: Request,
    organization_id: str,
    user_id: str,
    action: str,
    result: str,
    audit_log_store: SqliteAuditLogStore,
    now: datetime | None = None,
) -> None:
    """Record one real mutation.

    Swallows storage errors -- never fails the caller's real action.
    """
    entry = AuditLogEntry(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
        user_id=user_id,
        action=action,
        result=result,
        ip_address=_client_ip(request),
        created_at=now or datetime.now(UTC),
    )
    try:
        audit_log_store.record(entry)
    except Exception:  # noqa: BLE001 -- observability must never gate the real action
        logger.warning("Failed to record audit-log entry for action=%s", action)
