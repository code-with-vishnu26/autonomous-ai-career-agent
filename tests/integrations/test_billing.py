"""Phase 60 (ADR-0078): FakeBillingProvider -- no real payment calls."""

from __future__ import annotations

from career_agent.integrations.billing import BillingService, FakeBillingProvider


async def test_create_checkout_session_returns_a_deterministic_placeholder_url():
    provider = FakeBillingProvider()
    url = await provider.create_checkout_session(organization_id="o1", plan_id="pro")
    assert "o1" in url
    assert "pro" in url
    assert url.startswith("https://")


async def test_current_status_is_always_active():
    provider = FakeBillingProvider()
    status = await provider.current_status(organization_id="o1")
    assert status == "ACTIVE"


def test_fake_provider_satisfies_the_billing_service_protocol():
    assert isinstance(FakeBillingProvider(), BillingService)
