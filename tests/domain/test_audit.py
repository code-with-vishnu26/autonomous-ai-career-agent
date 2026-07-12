"""Phase 60 (ADR-0078): AuditLogEntry domain model."""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.domain.audit import AuditLogEntry


def test_audit_log_entry_round_trips():
    entry = AuditLogEntry(
        id="a1",
        organization_id="o1",
        user_id="u1",
        action="member_removed:u2",
        result="ok",
        ip_address="127.0.0.1",
        created_at=datetime.now(UTC),
    )
    assert entry.action == "member_removed:u2"
    assert entry.ip_address == "127.0.0.1"


def test_ip_address_optional():
    entry = AuditLogEntry(
        id="a1",
        organization_id="o1",
        user_id="u1",
        action="organization_created",
        result="ok",
        created_at=datetime.now(UTC),
    )
    assert entry.ip_address is None
