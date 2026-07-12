"""Phase 60 (ADR-0078): SqliteOrganizationStore."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from career_agent.domain.organization import Organization
from career_agent.storage.organization_store import SqliteOrganizationStore

_FIXED_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _organization(**overrides: object) -> Organization:
    fields: dict[object, object] = {
        "id": "o1",
        "name": "Acme Corp",
        "slug": "acme-corp",
        "created_by_user_id": "u1",
        "created_at": _FIXED_NOW,
    }
    fields.update(overrides)
    return Organization(**fields)


def test_create_and_get_round_trip(tmp_path: Path) -> None:
    store = SqliteOrganizationStore(tmp_path / "db.sqlite")
    store.create(_organization())
    assert store.get("o1") == _organization()


def test_get_returns_none_for_unknown_id(tmp_path: Path) -> None:
    store = SqliteOrganizationStore(tmp_path / "db.sqlite")
    assert store.get("missing") is None


def test_get_by_slug(tmp_path: Path) -> None:
    store = SqliteOrganizationStore(tmp_path / "db.sqlite")
    store.create(_organization())
    assert store.get_by_slug("acme-corp") == _organization()
    assert store.get_by_slug("unknown") is None


def test_rename_updates_name_and_preserves_slug(tmp_path: Path) -> None:
    store = SqliteOrganizationStore(tmp_path / "db.sqlite")
    store.create(_organization())
    updated = store.rename("o1", name="Acme Corporation")
    assert updated is not None
    assert updated.name == "Acme Corporation"
    assert updated.slug == "acme-corp"
    assert store.get("o1").name == "Acme Corporation"


def test_rename_unknown_returns_none(tmp_path: Path) -> None:
    store = SqliteOrganizationStore(tmp_path / "db.sqlite")
    assert store.rename("missing", name="x") is None


def test_delete_removes_the_organization(tmp_path: Path) -> None:
    store = SqliteOrganizationStore(tmp_path / "db.sqlite")
    store.create(_organization())
    store.delete("o1")
    assert store.get("o1") is None


def test_all_organizations(tmp_path: Path) -> None:
    store = SqliteOrganizationStore(tmp_path / "db.sqlite")
    store.create(_organization(id="o1", slug="one"))
    store.create(_organization(id="o2", slug="two"))
    ids = {org.id for org in store.all_organizations()}
    assert ids == {"o1", "o2"}
