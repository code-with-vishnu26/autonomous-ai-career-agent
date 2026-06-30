# ADR-0010: Hybrid (tiered) application strategy

- **Status:** Accepted
- **Date:** 2026-06-30
- **References:** [ADR-0003](0003-truthfulness-gate.md),
  [ADR-0008](0008-human-in-the-loop.md), [ADR-0004](0004-plugin-architecture.md)

## Context

Employers receive applications through many channels: structured ATS APIs
(sometimes), web forms (often), and plain email (sometimes). No single submission
mechanism works everywhere — an API-only approach can't apply to most postings, and
a browser-only approach is fragile and wasteful where a clean API exists.

## Problem

How do we submit applications reliably across a heterogeneous landscape, preferring
the most robust mechanism available for each posting while staying truthful and
supervised?

## Decision

Use a **hybrid, tiered applicator** that selects the best available submission
mechanism per opportunity and falls back down the tiers on failure — the same
resilience pattern as dynamic search-provider selection
([ADR-0002](0002-search-provider-abstraction.md)).

```
Tier 1  Direct ATS API        most robust; structured; least fragile
   ↓ (unavailable / fails)
Tier 2  Driven browser        Playwright + Browser-Use, supervised
   ↓ (unavailable / fails)
Tier 3  Email-to-apply        via the Gmail connector
```

- **Prefer the most robust tier** the opportunity supports; degrade gracefully.
- **Tiers are plugins.** ATS adapters and connectors register via the plugin
  registry ([ADR-0004](0004-plugin-architecture.md)); adding Workday or a new email
  path is additive, not a core change.
- **Truthfulness gate first, always.** No tier may submit content that has not
  passed [ADR-0003](0003-truthfulness-gate.md).
- **Supervised at every tier.** Each tier honors human-in-the-loop pauses,
  throttling, and user-defined confirmation ([ADR-0008](0008-human-in-the-loop.md)).
  Tier 2 reuses a manually established session and never automates OAuth.
- **Outcome-emitting.** Every attempt (success/failure/paused) emits events so the
  Learning engine ([ADR-0009](0009-learning-engine.md)) can improve tier selection.

## Alternatives considered

- **API-only.** Cleanest, but only a minority of postings expose a usable API —
  would leave most opportunities unreachable. Rejected as sole strategy.
- **Browser-only.** Universal-ish, but fragile, slower, and wasteful where a clean
  API exists; more anti-bot friction. Rejected as sole strategy.
- **Email-only.** Broadly possible, but bypasses structured ATS data, hurts
  trackability, and isn't accepted everywhere. Rejected as sole strategy.
- **Single configurable mechanism (no fallback).** Loses resilience; one failure
  mode blocks the application. Rejected in favor of tiered fallback.

## Trade-offs

- **(+)** Broad reach with best-available robustness per posting; resilient via
  fallback; extensible via plugins; consistent truthfulness/supervision guarantees
  across channels.
- **(−)** Three code paths to build and maintain; tier selection and fallback add
  complexity; Tier 2/3 reliability varies by site (mitigated by emitting outcomes
  and letting Learning bias tier choice).

## Consequences

- Phase 7 implements the applicator with the gate as a mandatory precondition and
  human-in-the-loop pauses wired in.
- ATS adapters (Phase 6) provide Tier 1; the browser and Gmail connectors provide
  Tiers 2–3.
- Per-tier success rates become a Learning signal feeding future tier selection.

## Future revisit criteria

Revisit if:

- A dominant standard submission API emerges that makes lower tiers rarely needed.
- Browser automation reliability degrades enough (anti-bot escalation) to reconsider
  Tier 2's role.
- A new submission channel (e.g. a sanctioned partner API) warrants a new tier.
- Tier-selection logic grows complex enough to warrant its own component/ADR.
