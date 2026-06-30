# ADR-0009: Learning engine

- **Status:** Accepted
- **Date:** 2026-06-30
- **References:** [ADR-0000](0000-project-philosophy.md) (objective),
  [ADR-0005](0005-event-bus.md)

## Context

The objective is to **maximize interview rate per application**
([ADR-0000](0000-project-philosophy.md)), which is only achievable if the system
improves from what actually happens: which applications got responses, which
résumé framings landed interviews, which sources yield quality, where automation
fails. Without a learning loop the agent repeats the same mistakes.

## Problem

How does the system improve over time using **evidence** (real outcomes) rather
than assumptions, without compromising truthfulness or maintainability?

## Decision

Add a **Learning engine** (Learning Agent) that closes the Discover → Decide →
Apply → **Learn** loop by consuming outcome events and feeding insights back into
earlier stages.

- **Evidence over assumptions.** Decisions are adjusted from recorded outcomes, not
  hand-wavy heuristics.
- **Signals tracked:** interview rate, response rate, résumé/framing performance,
  search/source quality, automation failure modes, and recruiter feedback.
- **Feedback targets:**
  - **Decide** — scoring/prioritization weights ([ADR-0007](0007-planner-agent.md))
    learn which opportunity traits convert.
  - **Search** — provider success-rate term ([ADR-0002](0002-search-provider-abstraction.md))
    reflects which providers/queries find quality.
  - **Resume** — which truthful framings perform (never *what* facts — truthfulness
    is fixed; [ADR-0003](0003-truthfulness-gate.md) is not negotiable by learning).
  - **Apply** — automation reliability and tier-selection
    ([ADR-0010](0010-hybrid-application-strategy.md)).
- **Event-sourced.** It subscribes to `OutcomeRecorded` and related events
  ([ADR-0005](0005-event-bus.md)); SQLite is the durable record analytics read from.
- **Transparent.** Adjustments are inspectable and attributable to the evidence
  that drove them — no opaque global "score."

### Guardrail

Learning may tune **targeting, ranking, phrasing, and routing**. It may **never**
weaken the truthfulness gate, relax human-in-the-loop controls, or optimize for
volume. Those are constitution-level ([ADR-0000](0000-project-philosophy.md)) and
out of the loop's reach.

## Alternatives considered

- **No learning (static heuristics).** Simple, but can't improve and abandons the
  core objective. Rejected.
- **End-to-end ML model trained to maximize a single reward.** Powerful but
  data-hungry (a single user generates little data), opaque, and risks gaming the
  metric or pushing toward volume. Rejected for now in favor of transparent,
  evidence-attributable adjustments.
- **Manual periodic tuning by the user.** A useful fallback, but doesn't scale with
  attention. Kept as an override, not the mechanism.

## Trade-offs

- **(+)** Directly serves the objective; transparent and auditable; reuses the event
  bus and SQLite already in place.
- **(−)** Single-user data is sparse, so signals are noisy early (mitigated by
  conservative updates and confidence thresholds); risk of feedback loops/overfitting
  to a few outcomes (mitigated by guardrails and slow adjustment).

## Consequences

- Phase 8 implements outcome capture and the first feedback into scoring.
- The dashboard (Phase 9) surfaces learned insights and lets the user inspect/override.
- Requires durable, well-modeled outcome data from the start of the Apply phase.

## Future revisit criteria

Revisit if:

- Accumulated data is rich enough to justify a learned model behind the same
  interface.
- Feedback loops are observed degrading rather than improving outcomes.
- New signals (e.g. interview-stage feedback) warrant new feedback targets.
- The single-user data sparsity assumption changes.
