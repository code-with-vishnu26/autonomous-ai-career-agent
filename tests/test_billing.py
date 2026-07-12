"""Phase 60 (ADR-0078): billing.py composition helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from career_agent.billing import (
    get_or_create_subscription,
    seat_limit_exceeded,
    set_plan,
)
from career_agent.domain.team import Membership
from career_agent.storage.billing_store import SqliteSubscriptionStore
from career_agent.storage.team_store import SqliteMembershipStore

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_get_or_create_subscription_defaults_to_free(tmp_path: Path) -> None:
    store = SqliteSubscriptionStore(tmp_path / "db.sqlite")
    subscription = get_or_create_subscription(
        organization_id="o1", subscription_store=store, now=_NOW
    )
    assert subscription.plan_id == "free"


def test_get_or_create_subscription_returns_existing(tmp_path: Path) -> None:
    store = SqliteSubscriptionStore(tmp_path / "db.sqlite")
    first = get_or_create_subscription(
        organization_id="o1", subscription_store=store, now=_NOW
    )
    second = get_or_create_subscription(
        organization_id="o1", subscription_store=store, now=_NOW
    )
    assert first.id == second.id


def test_set_plan_changes_the_stored_plan(tmp_path: Path) -> None:
    store = SqliteSubscriptionStore(tmp_path / "db.sqlite")
    get_or_create_subscription(organization_id="o1", subscription_store=store, now=_NOW)
    updated = set_plan(
        organization_id="o1", plan_id="pro", subscription_store=store, now=_NOW
    )
    assert updated.plan_id == "pro"
    assert store.get("o1").plan_id == "pro"


def test_seat_limit_not_exceeded_when_under_the_plan_limit(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    subscription_store = SqliteSubscriptionStore(db)
    membership_store = SqliteMembershipStore(db)
    membership_store.create(
        Membership(
            id="m1", organization_id="o1", user_id="u1", role="owner", joined_at=_NOW
        )
    )
    assert (
        seat_limit_exceeded(
            organization_id="o1",
            subscription_store=subscription_store,
            membership_store=membership_store,
            now=_NOW,
        )
        is False
    )


def test_seat_limit_exceeded_once_free_plans_limit_is_reached(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    subscription_store = SqliteSubscriptionStore(db)
    membership_store = SqliteMembershipStore(db)
    # Free plan's max_seats is 3 (domain/billing.py's PLANS["free"]).
    for i in range(3):
        membership_store.create(
            Membership(
                id=f"m{i}",
                organization_id="o1",
                user_id=f"u{i}",
                role="member",
                joined_at=_NOW,
            )
        )
    assert (
        seat_limit_exceeded(
            organization_id="o1",
            subscription_store=subscription_store,
            membership_store=membership_store,
            now=_NOW,
        )
        is True
    )


def test_seat_limit_raised_after_upgrading_plan(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    subscription_store = SqliteSubscriptionStore(db)
    membership_store = SqliteMembershipStore(db)
    for i in range(3):
        membership_store.create(
            Membership(
                id=f"m{i}",
                organization_id="o1",
                user_id=f"u{i}",
                role="member",
                joined_at=_NOW,
            )
        )
    set_plan(
        organization_id="o1",
        plan_id="pro",
        subscription_store=subscription_store,
        now=_NOW,
    )
    assert (
        seat_limit_exceeded(
            organization_id="o1",
            subscription_store=subscription_store,
            membership_store=membership_store,
            now=_NOW,
        )
        is False
    )
