"""Billing composition helpers (Phase 60, ADR-0078).

Top-level, same reasoning as ``organizations.py``/``invitations.py``:
composes domain construction with storage and (for plan changes) the
``BillingService`` port. The one real, enforced behavior a billing stub
can still deliver without any real payment: seat limits actually gate
invitations (:func:`seat_limit_exceeded`), so "Pro plan, 15 seats" is a
real constraint, not just a number shown on a pricing page.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from career_agent.domain.billing import PLANS, PlanId, Subscription
from career_agent.storage.billing_store import SqliteSubscriptionStore
from career_agent.storage.team_store import SqliteMembershipStore

#: A stub "period" length -- long enough that nothing here ever expires
#: in practice (no real billing cycle exists to renew against).
_PERIOD_LENGTH = timedelta(days=365)


def get_or_create_subscription(
    *,
    organization_id: str,
    subscription_store: SqliteSubscriptionStore,
    now: datetime,
) -> Subscription:
    """Every organization's subscription -- auto-provisioned on the Free plan.

    Mirrors ``organizations.create_personal_organization``'s own "every
    org gets a real row, not a null/missing state a caller has to
    special-case" discipline.
    """
    existing = subscription_store.get(organization_id)
    if existing is not None:
        return existing
    subscription = Subscription(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
        plan_id="free",
        status="ACTIVE",
        current_period_end=now + _PERIOD_LENGTH,
        created_at=now,
    )
    subscription_store.save(subscription)
    return subscription


def set_plan(
    *,
    organization_id: str,
    plan_id: PlanId,
    subscription_store: SqliteSubscriptionStore,
    now: datetime,
) -> Subscription:
    """Change ``organization_id``'s plan.

    A real provider would only do this after a webhook confirms payment;
    the fake provider has no payment to wait for, so this applies
    immediately -- the one place this stub's behavior differs from a real
    integration, named in ``integrations/billing.py``'s own docstring.
    """
    subscription = Subscription(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
        plan_id=plan_id,
        status="ACTIVE",
        current_period_end=now + _PERIOD_LENGTH,
        created_at=now,
    )
    subscription_store.save(subscription)
    return subscription


def seat_limit_exceeded(
    *,
    organization_id: str,
    subscription_store: SqliteSubscriptionStore,
    membership_store: SqliteMembershipStore,
    now: datetime,
) -> bool:
    """Whether ``organization_id`` is already at (or over) its plan's seat limit.

    The one real, enforced consequence of a plan choice in this stub --
    checked before creating an invitation, so "upgrade to invite more
    people" is a genuine constraint, not a number on a pricing page no
    code ever reads.
    """
    subscription = get_or_create_subscription(
        organization_id=organization_id,
        subscription_store=subscription_store,
        now=now,
    )
    plan = PLANS[subscription.plan_id]
    current_members = len(membership_store.by_organization(organization_id))
    return current_members >= plan.max_seats
