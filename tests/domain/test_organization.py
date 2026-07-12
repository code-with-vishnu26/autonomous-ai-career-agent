"""Phase 60 (ADR-0078): Organization domain model."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from career_agent.domain.organization import Organization


def _organization(**overrides: object) -> Organization:
    fields: dict[object, object] = {
        "id": "o1",
        "name": "Acme Corp",
        "slug": "acme-corp",
        "created_by_user_id": "u1",
        "created_at": datetime.now(UTC),
    }
    fields.update(overrides)
    return Organization(**fields)


def test_slug_is_normalized_lowercase():
    organization = _organization(slug="ACME-Corp")
    assert organization.slug == "acme-corp"


def test_invalid_slug_rejected():
    with pytest.raises(ValidationError):
        _organization(slug="not a valid slug!")


def test_valid_slug_accepted():
    organization = _organization(slug="acme-corp-2")
    assert organization.slug == "acme-corp-2"
