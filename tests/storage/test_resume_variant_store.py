"""Phase 50 (ADR-0068): SqliteResumeVariantStore -- append-only, same
discipline as SqliteApplicationStore (ADR-0037)."""

from __future__ import annotations

from pathlib import Path

from career_agent.domain.models import TailoredContent
from career_agent.domain.resume_variants import ResumeVariant
from career_agent.storage.sqlite import SqliteResumeVariantStore


def _variant(id_: str, category: str = "backend") -> ResumeVariant:
    return ResumeVariant(
        id=id_,
        category=category,
        profile_version="profile-v1",
        content=TailoredContent(summary="Backend engineer.", skills=["Python"]),
        created_at="2026-01-01T00:00:00+00:00",
    )


def test_save_then_by_category_round_trips(tmp_path: Path) -> None:
    store = SqliteResumeVariantStore(tmp_path / "db.sqlite")
    variant = _variant("v1")
    store.save(variant, user_id="u1")
    result = store.by_category("backend")
    assert result == [variant]


def test_by_category_only_returns_matching_category(tmp_path: Path) -> None:
    store = SqliteResumeVariantStore(tmp_path / "db.sqlite")
    store.save(_variant("v1", category="backend"), user_id="u1")
    store.save(_variant("v2", category="frontend"), user_id="u1")
    assert [v.id for v in store.by_category("backend")] == ["v1"]
    assert [v.id for v in store.by_category("frontend")] == ["v2"]


def test_by_category_unknown_category_returns_empty(tmp_path: Path) -> None:
    store = SqliteResumeVariantStore(tmp_path / "db.sqlite")
    assert store.by_category("nonexistent") == []


def test_save_is_append_only_never_overwrites(tmp_path: Path) -> None:
    store = SqliteResumeVariantStore(tmp_path / "db.sqlite")
    original = _variant("v1")
    store.save(original, user_id="u1")
    mutated = original.model_copy(update={"category": "frontend"})
    store.save(mutated, user_id="u1")  # same id -- INSERT OR IGNORE must not overwrite
    result = store.by_category("backend")
    assert len(result) == 1
    assert result[0].category == "backend"


def test_all_variants_returns_every_category(tmp_path: Path) -> None:
    store = SqliteResumeVariantStore(tmp_path / "db.sqlite")
    store.save(_variant("v1", category="backend"), user_id="u1")
    store.save(_variant("v2", category="frontend"), user_id="u1")
    ids = {v.id for v in store.all_variants()}
    assert ids == {"v1", "v2"}


def test_survives_close_and_reopen(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite"
    SqliteResumeVariantStore(path).save(_variant("v1"), user_id="u1")
    reopened = SqliteResumeVariantStore(path)
    assert [v.id for v in reopened.by_category("backend")] == ["v1"]
