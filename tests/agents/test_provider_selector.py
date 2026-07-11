"""Phase 49 (ADR-0067): provider priority ordering."""

from __future__ import annotations

from career_agent.agents.planner.provider_selector import order_providers


def test_preferred_providers_come_first_in_given_order() -> None:
    ordered = order_providers(
        ["lever", "greenhouse"],
        ["greenhouse", "lever", "ashby", "remoteok"],
    )
    assert ordered == ["lever", "greenhouse", "ashby", "remoteok"]


def test_no_preference_preserves_registration_order() -> None:
    registered = ["greenhouse", "lever", "ashby"]
    assert order_providers([], registered) == registered


def test_unregistered_preferred_provider_is_silently_ignored() -> None:
    ordered = order_providers(["workday"], ["greenhouse", "lever"])
    assert ordered == ["greenhouse", "lever"]


def test_no_provider_is_ever_dropped_only_reordered() -> None:
    registered = ["greenhouse", "lever", "ashby", "remoteok", "remotive"]
    ordered = order_providers(["remoteok"], registered)
    assert set(ordered) == set(registered)
    assert len(ordered) == len(registered)


def test_preferred_provider_not_duplicated_when_also_first_in_registered() -> None:
    ordered = order_providers(["greenhouse"], ["greenhouse", "lever"])
    assert ordered.count("greenhouse") == 1
