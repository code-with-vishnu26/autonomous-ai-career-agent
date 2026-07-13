"""Phase 64 (ADR-0082): SqliteMasterProfileStore -- a real upsert, mirroring
SqliteUserPreferencesStore's exact shape, plus id-validation/version-hash
reuse from storage.profile."""

from __future__ import annotations

from pathlib import Path

import pytest

from career_agent.domain.models import BasicsSection, MasterProfile, WorkEntry
from career_agent.storage.profile import ProfileValidationError
from career_agent.storage.sqlite import SqliteMasterProfileStore


def _profile(**overrides: object) -> MasterProfile:
    fields = {
        "version": "pending",
        "basics": BasicsSection(name="Ada Lovelace", email="ada@example.com"),
    }
    fields.update(overrides)
    return MasterProfile(**fields)


def test_save_then_get_round_trips(tmp_path: Path) -> None:
    store = SqliteMasterProfileStore(tmp_path / "db.sqlite")
    saved = store.save("u1", _profile())
    assert store.get("u1") == saved


def test_save_recomputes_version_server_side(tmp_path: Path) -> None:
    """A client-supplied version is never trusted -- always overwritten."""
    store = SqliteMasterProfileStore(tmp_path / "db.sqlite")
    saved = store.save("u1", _profile(version="totally-fabricated"))
    assert saved.version != "totally-fabricated"
    assert saved.version.startswith("sha256:")


def test_get_scoped_to_owning_user_only(tmp_path: Path) -> None:
    store = SqliteMasterProfileStore(tmp_path / "db.sqlite")
    store.save("u1", _profile())
    assert store.get("someone-else") is None


def test_get_unknown_user_returns_none(tmp_path: Path) -> None:
    store = SqliteMasterProfileStore(tmp_path / "db.sqlite")
    assert store.get("nonexistent") is None


def test_save_is_a_real_upsert_not_append_only(tmp_path: Path) -> None:
    store = SqliteMasterProfileStore(tmp_path / "db.sqlite")
    store.save("u1", _profile())
    updated = store.save(
        "u1", _profile(basics=BasicsSection(name="Ada Byron", email="ada@example.com"))
    )
    assert store.get("u1") == updated
    assert store.get("u1").basics.name == "Ada Byron"


def test_save_rejects_duplicate_ids_across_sections(tmp_path: Path) -> None:
    store = SqliteMasterProfileStore(tmp_path / "db.sqlite")
    profile = _profile(
        work=[
            WorkEntry(
                id="dup", name="Acme", position="Engineer", start_date="2020-01-01"
            ),
        ],
        projects=[],
    )
    # Reuse the same id across sections -- the exact cross-section check
    # storage.profile._validate_ids already enforces for the file loader.
    from career_agent.domain.models import ProjectEntry

    profile = profile.model_copy(
        update={"projects": [ProjectEntry(id="dup", name="Side Project")]}
    )
    with pytest.raises(ProfileValidationError):
        store.save("u1", profile)


def test_survives_close_and_reopen(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite"
    SqliteMasterProfileStore(path).save("u1", _profile())
    reopened = SqliteMasterProfileStore(path)
    assert reopened.get("u1") is not None
