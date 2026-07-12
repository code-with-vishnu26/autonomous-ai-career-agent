"""Billing: a real, production-ready shape with no external payment calls.

Phase 60, ADR-0078. The brief is explicit: "Do NOT integrate Stripe...
Everything production-ready. No external payment calls." This module is
the data half of that -- ``Plan``/``Subscription``/``UsageCounter`` are
exactly what a real billing integration would eventually persist and
read; ``integrations/billing.py``'s ``BillingService`` protocol +
``FakeBillingProvider`` are the transport half. Swapping the fake
provider for a real Stripe-backed one later changes zero call sites,
the same "port + adapter" shape every other integration in this project
already uses (``EmailSender``/``SmtpEmailSender``,
``WebhookSender``/``HttpClient``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

#: Three fixed, hardcoded plans -- no pricing-table database, no
#: admin-configurable plan editor (not requested; would be real,
#: unrequested complexity for a stub billing layer).
PlanId = Literal["free", "pro", "enterprise"]

SubscriptionStatus = Literal["ACTIVE", "CANCELLED", "PAST_DUE", "TRIALING"]


class Plan(BaseModel):
    """One fixed plan's price, seat limit, and feature flags."""

    id: PlanId
    name: str
    monthly_price_cents: int
    max_seats: int
    features: frozenset[str] = Field(default_factory=frozenset)


#: The three plans this stub ships with -- looked up by id, never
#: constructed ad hoc, so "what features does the Pro plan have" has
#: exactly one answer.
PLANS: dict[PlanId, Plan] = {
    "free": Plan(
        id="free",
        name="Free",
        monthly_price_cents=0,
        max_seats=3,
        features=frozenset({"prepare_resume", "review", "submit"}),
    ),
    "pro": Plan(
        id="pro",
        name="Pro",
        monthly_price_cents=4900,
        max_seats=15,
        features=frozenset(
            {"prepare_resume", "review", "submit", "view_analytics", "webhooks"}
        ),
    ),
    "enterprise": Plan(
        id="enterprise",
        name="Enterprise",
        monthly_price_cents=19900,
        max_seats=250,
        features=frozenset(
            {
                "prepare_resume",
                "review",
                "submit",
                "view_analytics",
                "webhooks",
                "audit_log_export",
            }
        ),
    ),
}


class Subscription(BaseModel):
    """One organization's current plan and status."""

    id: str
    organization_id: str
    plan_id: PlanId
    status: SubscriptionStatus
    current_period_end: datetime
    created_at: datetime


class UsageCounter(BaseModel):
    """One organization's usage of one metric, for the current period."""

    organization_id: str
    metric: str
    count: int
    period_start: datetime
