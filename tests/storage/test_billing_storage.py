"""Phase 60 (ADR-0078): SqliteSubscriptionStore + SqliteUsageCounterStore."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from career_agent.domain.billing import Subscription
from career_agent.storage.billing_store import (
    SqliteSubscriptionStore,
    SqliteUsageCounterStore,
)

_FIXED_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _subscription(**overrides: object) -> Subscription:
    fields: dict[object, object] = {
        "id": "s1",
        "organization_id": "o1",
        "plan_id": "free",
        "status": "ACTIVE",
        "current_period_end": _FIXED_NOW,
        "created_at": _FIXED_NOW,
    }
    fields.update(overrides)
    return Subscription(**fields)


def test_subscription_get_returns_none_before_save(tmp_path: Path) -> None:
    store = SqliteSubscriptionStore(tmp_path / "db.sqlite")
    assert store.get("o1") is None


def test_subscription_save_and_get(tmp_path: Path) -> None:
    store = SqliteSubscriptionStore(tmp_path / "db.sqlite")
    store.save(_subscription())
    assert store.get("o1") == _subscription()


def test_subscription_save_upserts(tmp_path: Path) -> None:
    store = SqliteSubscriptionStore(tmp_path / "db.sqlite")
    store.save(_subscription(plan_id="free"))
    store.save(_subscription(plan_id="pro"))
    assert store.get("o1").plan_id == "pro"


def test_usage_counter_increment_starts_at_the_increment_value(tmp_path: Path) -> None:
    store = SqliteUsageCounterStore(tmp_path / "db.sqlite")
    now = datetime.now(UTC)
    counter = store.increment(organization_id="o1", metric="seats", now=now)
    assert counter.count == 1


def test_usage_counter_increment_accumulates(tmp_path: Path) -> None:
    store = SqliteUsageCounterStore(tmp_path / "db.sqlite")
    now = datetime.now(UTC)
    store.increment(organization_id="o1", metric="seats", now=now)
    counter = store.increment(organization_id="o1", metric="seats", now=now, by=3)
    assert counter.count == 4


def test_usage_counter_get_returns_none_before_increment(tmp_path: Path) -> None:
    store = SqliteUsageCounterStore(tmp_path / "db.sqlite")
    assert store.get(organization_id="o1", metric="seats") is None


def test_usage_counter_by_organization(tmp_path: Path) -> None:
    store = SqliteUsageCounterStore(tmp_path / "db.sqlite")
    now = datetime.now(UTC)
    store.increment(organization_id="o1", metric="seats", now=now)
    store.increment(organization_id="o1", metric="submissions", now=now)
    metrics = {c.metric for c in store.by_organization("o1")}
    assert metrics == {"seats", "submissions"}
