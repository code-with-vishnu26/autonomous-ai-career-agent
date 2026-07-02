# ADR-0002: Search provider abstraction

- **Status:** Accepted
- **Date:** 2026-06-30
- **References:** [ADR-0000](0000-project-philosophy.md),
  [ADR-0004](0004-plugin-architecture.md)

## Context

Open-ended discovery ([ROADMAP](../../ROADMAP.md) Phase 4) reaches a point where
structured sources (ATS APIs, YC, Hacker News) run out and the agent must fall
back to **web search** to find career pages and postings. There are several search
providers (Exa for semantic search, Google Custom Search Engine for keyword/site
search, Brave, etc.), each with different capabilities, costs, latency, and rate
limits — and any one of them can be down or quota-exhausted at a given moment.

## Problem

How do we use web search without hardcoding a single provider, so that providers
can be added/removed freely, the system fails over when one is unavailable, and
the "best" provider for a given query is chosen on the merits rather than a fixed
preference order?

## Decision

Define a **provider-abstracted search layer**. Every provider is a plugin
([ADR-0004](0004-plugin-architecture.md)) implementing a common `SearchProvider`
interface and **advertising its capabilities** and live **health**. The Planner
(or a search skill) selects a provider dynamically per query.

### Capability discovery

Each provider declares what it supports, so callers can match a query to a capable
provider instead of assuming:

```
ProviderCapabilities
  supports_site_search       # restrict to a domain (e.g. site:company.com careers)
  supports_freshness         # recency filtering / date ranges
  supports_news              # news vertical
  supports_semantic_search   # meaning-based (e.g. Exa)
  supports_images            # image results
```

A query carries its requirements (e.g. "needs semantic + freshness"); only
providers whose capabilities satisfy them are eligible.

### Dynamic, health-based ranking

Rather than a static `Google → Exa → Brave` order, eligible providers are scored
and the best one wins **dynamically**:

```
score = f(
  Health Score,    # is it up? recent error rate
  Latency,         # rolling p50/p95 response time
  Cost,            # $ per query (favor cheaper when quality is equal)
  Success Rate,    # rolling fraction of useful, non-empty responses
  Capabilities     # how well it matches the query's requirements
)
```

The top-scored provider is tried first; on failure the next eligible provider is
used (failover), and the result updates the rolling health/latency/success stats
that feed the next decision. This mirrors the resilience pattern used elsewhere
(the tiered applicator, [ADR-0010](0010-hybrid-application-strategy.md)).

## Alternatives considered

- **Single hardcoded provider.** Simplest, but a single point of failure and
  violates Golden Rule #4 (never hardcode providers). Rejected.
- **Static priority list with failover.** Better, but ignores live health/cost and
  can't route a semantic query to a semantic provider. Rejected in favor of
  capability-aware dynamic ranking.
- **Always query all providers and merge.** Highest quality, but multiplies cost
  and rate-limit pressure for a single user. Rejected as default; may be offered
  as an opt-in "thorough" mode.

## Trade-offs

- **(+)** Providers are swappable plugins; resilient to outages/quotas; queries go
  to genuinely capable providers; cost-aware by default.
- **(−)** A scoring layer plus rolling health stats is more complex than a static
  list; scoring weights need tuning and could mis-rank early before stats warm up
  (mitigated by sane defaults and capability gating).

## Consequences

- Adding Brave/Bing/etc. is a new plugin advertising its capabilities — no core
  change.
- The Learning engine ([ADR-0009](0009-learning-engine.md)) can later feed search
  result quality back into the success-rate term.

## Future revisit criteria

Revisit if:

- Provider count grows large enough that per-query scoring becomes a hotspot.
- A single provider proves clearly dominant across all query types (static routing
  might then be simpler).
- Cost structure changes such that "query-all-and-merge" becomes affordable.
- Search quality stops correlating with the chosen scoring terms.

## Amendment (2026-07-02): the ranking formula, implemented (4c slice-3)

This amendment records the concrete implementation of the abstract formula
above, not a new decision — the same pattern as the ADR-0005 "events notify,
they do not gate" amendment: a slice makes an already-decided principle
concrete, so it is recorded here rather than under a new ADR number.

- **Two pure functions** in `core/ranking.py`: `is_eligible(capabilities,
  query) -> bool` and `score_provider(health) -> float`, composed by
  `select_provider(providers, query) -> SearchProvider`.
- **Eligibility is a gate, not a scoring term.** A query's requirements
  (`requires_semantic`, `requires_freshness`, `site`) are a floor: a provider
  missing a required capability is excluded entirely, never merely scored
  lower. A semantic query never even considers a keyword-only provider, no
  matter how healthy that provider is.
- **Score** among eligible providers: `10·success_rate − 1·(latency_ms/1000) −
  5·cost_per_query`. Weights favor reliability first, then speed, then cost;
  they are relative (only their ratios matter for comparison), not calibrated
  to any absolute quality scale.
- **`select_provider` raises `NoEligibleProviderError`** when no registered
  provider satisfies a query's requirements — it never silently falls back to
  an ineligible provider. A silent fallback would mean a semantic query gets
  quietly answered by a keyword-only provider with nobody told the result is
  structurally worse: the discovery-side equivalent of presenting an unverified
  result as confident. Same fail-loud instinct as duplicate plugin registration
  raising immediately (ADR-0004) rather than silently overwriting.
- Google CSE (`plugins/search/google_cse.py`) is the second provider — deliberately
  keyword-only (`supports_semantic_search=False`), the direct capability contrast
  to Exa, so the eligibility gate has a real difference to exercise rather than
  ranking between two providers that do the same thing.

### Explicitly deferred (not built in this slice)

- **Who calls `select_provider`, and when.** These are pure functions with no
  dependency on the Planner or any scheduling story; wiring them into a live
  discovery flow is a Planner-phase decision, made when the Planner is designed
  — not guessed at here.
- **Persistent rolling health across process restarts.** `health()` is
  in-memory per provider instance today (true for both Exa and Google CSE); a
  durable store is a storage-phase concern.
- **Failover-on-failure orchestration** (try the top-ranked provider, catch a
  failure, retry the next-best). `select_provider` picks one provider; retry
  policy belongs to whatever calls `search()` in a loop, not to ranking itself.
