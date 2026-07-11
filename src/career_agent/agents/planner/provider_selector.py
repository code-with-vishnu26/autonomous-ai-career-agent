"""Provider priority ordering (Phase 49, ADR-0067).

Finally consumes ``JobPreferences.preferred_ats_providers`` -- captured in
Phase 46 (ADR-0064) but explicitly documented there as "not yet consumed
by the Decide layer." This is a different layer (pre-discovery planning,
not post-discovery ranking) consuming it for the first time, which is
exactly the kind of named, deferred gap that ADR was honest about, now
closed.

Pure, deterministic, no I/O: given the full list of registered provider
names (:meth:`~career_agent.integrations.adapters.registry.
AdapterRegistry.providers`) and a preference order, returns every provider
in priority order -- preferred providers first (in the order the user
gave), then every other registered provider, in registration order.
Nothing is ever excluded: a provider the user didn't name is simply
lower-priority, never dropped -- the brief's own example keeps RemoteOK
in the plan behind Greenhouse/Lever, not out of it.
"""

from __future__ import annotations


def order_providers(
    preferred: list[str], registered: list[str]
) -> list[str]:
    """Every ``registered`` provider, preferred ones first, in given order.

    A ``preferred`` entry not present in ``registered`` is silently
    ignored -- the caller may have configured a provider preference before
    that adapter existed or was wired in; that is not this function's
    error to raise.
    """
    registered_set = set(registered)
    ordered: list[str] = [p for p in preferred if p in registered_set]
    seen = set(ordered)
    for provider in registered:
        if provider not in seen:
            ordered.append(provider)
            seen.add(provider)
    return ordered
