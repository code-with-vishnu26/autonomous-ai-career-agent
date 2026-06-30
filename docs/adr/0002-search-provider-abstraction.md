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
