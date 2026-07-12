"""Billing endpoints (Phase 60, ADR-0078).

No Stripe -- see ``integrations/billing.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from career_agent.api.audit import record_audit
from career_agent.api.dependencies import (
    get_audit_log_store,
    get_membership_store,
    get_subscription_store,
    get_usage_counter_store,
)
from career_agent.api.rbac import require_membership, require_permission
from career_agent.api.security import get_current_user
from career_agent.billing import get_or_create_subscription, set_plan
from career_agent.domain.billing import PLANS, PlanId
from career_agent.domain.team import Membership
from career_agent.domain.user import User
from career_agent.integrations.billing import FakeBillingProvider

router = APIRouter(prefix="/billing", tags=["billing"])

_provider = FakeBillingProvider()


class PlanOut(BaseModel):
    """One available plan."""

    id: str
    name: str
    monthly_price_cents: int
    max_seats: int
    features: list[str]


class SubscriptionOut(BaseModel):
    """One organization's current plan and status."""

    organization_id: str
    plan_id: str
    status: str
    current_period_end: str


class UsageOut(BaseModel):
    """One metric's current usage for an organization."""

    metric: str
    count: int


class ChangePlanRequest(BaseModel):
    """Body for ``POST /billing/{organization_id}/checkout``."""

    plan_id: PlanId


class CheckoutResult(BaseModel):
    """The stub checkout's result -- activates immediately, no real payment step."""

    checkout_url: str
    subscription: SubscriptionOut


@router.get("/plans", response_model=list[PlanOut])
def list_plans() -> list[PlanOut]:
    """Every plan this stub offers -- public reference data, no auth required."""
    return [
        PlanOut(
            id=plan.id,
            name=plan.name,
            monthly_price_cents=plan.monthly_price_cents,
            max_seats=plan.max_seats,
            features=sorted(plan.features),
        )
        for plan in PLANS.values()
    ]


@router.get("/{organization_id}", response_model=SubscriptionOut)
def get_subscription(
    organization_id: str,
    subscription_store=Depends(get_subscription_store),
    _membership: Membership = Depends(require_membership),
) -> SubscriptionOut:
    """One organization's current subscription -- any member may view it."""
    subscription = get_or_create_subscription(
        organization_id=organization_id,
        subscription_store=subscription_store,
        now=datetime.now(UTC),
    )
    return _subscription_out(subscription)


@router.post("/{organization_id}/checkout", response_model=CheckoutResult)
async def checkout(
    organization_id: str,
    body: ChangePlanRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    subscription_store=Depends(get_subscription_store),
    audit_log_store=Depends(get_audit_log_store),
    _membership: Membership = Depends(require_permission("manage_billing")),
) -> CheckoutResult:
    """Change plan -- requires ``manage_billing``.

    Activates immediately (stub, no Stripe).
    """
    checkout_url = await _provider.create_checkout_session(
        organization_id=organization_id, plan_id=body.plan_id
    )
    subscription = set_plan(
        organization_id=organization_id,
        plan_id=body.plan_id,
        subscription_store=subscription_store,
        now=datetime.now(UTC),
    )
    record_audit(
        request=request,
        organization_id=organization_id,
        user_id=current_user.id,
        action=f"plan_changed:{body.plan_id}",
        result="ok",
        audit_log_store=audit_log_store,
    )
    return CheckoutResult(
        checkout_url=checkout_url, subscription=_subscription_out(subscription)
    )


@router.get("/{organization_id}/usage", response_model=list[UsageOut])
def get_usage(
    organization_id: str,
    membership_store=Depends(get_membership_store),
    usage_counter_store=Depends(get_usage_counter_store),
    _membership: Membership = Depends(require_membership),
) -> list[UsageOut]:
    """Usage against the plan's limits.

    ``seats`` is always live (a real ``COUNT`` of memberships, the same
    number :func:`career_agent.billing.seat_limit_exceeded` enforces
    before an invite). Anything in ``SqliteUsageCounterStore`` is
    included too, but nothing increments it yet in this phase -- the
    store exists so a real metered feature (e.g. per-submission billing)
    has a real place to record usage without a schema change, not because
    one is wired today; see ADR-0078.
    """
    counters = [
        UsageOut(metric=counter.metric, count=counter.count)
        for counter in usage_counter_store.by_organization(organization_id)
    ]
    counters.append(
        UsageOut(
            metric="seats", count=len(membership_store.by_organization(organization_id))
        )
    )
    return counters


def _subscription_out(subscription) -> SubscriptionOut:
    return SubscriptionOut(
        organization_id=subscription.organization_id,
        plan_id=subscription.plan_id,
        status=subscription.status,
        current_period_end=subscription.current_period_end.isoformat(),
    )
