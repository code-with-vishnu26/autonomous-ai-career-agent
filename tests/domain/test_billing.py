"""Phase 60 (ADR-0078): billing domain models -- fixed plans, no Stripe."""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.domain.billing import PLANS, Subscription, UsageCounter


def test_every_plan_id_matches_its_own_key():
    for plan_id, plan in PLANS.items():
        assert plan.id == plan_id


def test_free_plan_has_the_smallest_seat_limit():
    assert PLANS["free"].max_seats < PLANS["pro"].max_seats
    assert PLANS["pro"].max_seats < PLANS["enterprise"].max_seats


def test_free_plan_is_actually_free():
    assert PLANS["free"].monthly_price_cents == 0


def test_paid_plans_cost_more_than_free():
    assert PLANS["pro"].monthly_price_cents > 0
    assert PLANS["enterprise"].monthly_price_cents > PLANS["pro"].monthly_price_cents


def test_subscription_round_trips():
    now = datetime.now(UTC)
    subscription = Subscription(
        id="s1",
        organization_id="o1",
        plan_id="pro",
        status="ACTIVE",
        current_period_end=now,
        created_at=now,
    )
    assert subscription.plan_id == "pro"


def test_usage_counter_round_trips():
    now = datetime.now(UTC)
    counter = UsageCounter(
        organization_id="o1", metric="seats", count=3, period_start=now
    )
    assert counter.count == 3
