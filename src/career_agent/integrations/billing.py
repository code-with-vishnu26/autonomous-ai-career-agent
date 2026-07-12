"""BillingService port + FakeBillingProvider adapter (Phase 60, ADR-0078).

The brief is explicit: no Stripe integration, no external payment calls,
but a "production-ready" shape. This is exactly the same port+adapter
split every other real integration in this project already uses
(:class:`~career_agent.integrations.email.EmailSender`/
``SmtpEmailSender``, :class:`~career_agent.integrations.webhook.WebhookSender`
over :class:`~career_agent.core.interfaces.HttpClient`): swapping
``FakeBillingProvider`` for a real Stripe-backed one later means writing
one new class against this exact protocol, not touching any call site.

A real provider's ``create_checkout_session`` would return a Stripe
Checkout URL and activation would happen asynchronously via a webhook
after the customer pays; the fake provider activates immediately (there
is no external payment step to wait for), which is the one place this
stub's behavior visibly differs from a real integration -- named here,
not hidden.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from career_agent.domain.billing import PlanId, SubscriptionStatus


@runtime_checkable
class BillingService(Protocol):
    """What any billing provider (fake today, Stripe or similar later) must do."""

    async def create_checkout_session(
        self, *, organization_id: str, plan_id: PlanId
    ) -> str:
        """A URL the caller should be sent to in order to subscribe to ``plan_id``."""
        ...

    async def current_status(self, *, organization_id: str) -> SubscriptionStatus:
        """The provider's own view of ``organization_id``'s subscription status."""
        ...


class FakeBillingProvider:
    """A real :class:`BillingService` that never calls out to a real payment processor.

    Every organization is always ``ACTIVE`` from this provider's point of
    view -- plan changes are applied immediately by the caller
    (``career_agent.billing.set_plan``), not gated on this provider ever
    confirming payment, since there is no real payment to confirm.
    """

    async def create_checkout_session(
        self, *, organization_id: str, plan_id: PlanId
    ) -> str:
        """A deterministic, non-functional placeholder URL -- never a real link."""
        return f"https://billing.example.invalid/checkout/{organization_id}/{plan_id}"

    async def current_status(self, *, organization_id: str) -> SubscriptionStatus:
        """Always ``ACTIVE`` -- this provider never actually bills anyone."""
        return "ACTIVE"
