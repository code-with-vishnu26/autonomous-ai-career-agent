"""AuditLogEntry: an append-only record of every organization mutation.

Phase 60, ADR-0078. Pure data, mirroring ``domain/notification.py``'s own
"the fact, not the trigger, lives here" discipline. Never updated once
written -- the same append-only precedent ``SqliteDeliveryAttemptStore``
already established for delivery attempts, applied here to authorization-
relevant actions instead of notification-delivery ones.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AuditLogEntry(BaseModel):
    """One real mutation: who did what, in which organization, and how it went."""

    id: str
    organization_id: str
    user_id: str
    action: str
    result: str
    ip_address: str | None = None
    created_at: datetime
