# ADR-0007: Planner Agent

- **Status:** Accepted
- **Date:** 2026-06-30
- **References:** [ADR-0001](0001-agent-oriented-architecture.md),
  [ADR-0005](0005-event-bus.md)

## Context

[ADR-0001](0001-agent-oriented-architecture.md) establishes an agent-oriented
architecture with a central Planner. This ADR fixes what the Planner *is* and,
crucially, what it is **not**, so it doesn't accumulate capability logic and become
a God Object (Golden Rule #3).

## Problem

Where does orchestration, prioritization, retry, and budget logic live, and how do
we keep that coordinator from absorbing capability logic over time?

## Decision

The **Planner Agent is the coordinator and only the coordinator.** It owns *when*
and *in what order* things happen; it never owns *how* a capability is performed.

- **Built on LangGraph** so its decision loop is an inspectable, resumable state
  machine rather than opaque control flow.
- **Drives the [ADR-0001] lifecycle:** Plan → Delegate → Monitor → Recover →
  Complete, for every unit of work.
- **Responsibilities (coordination only):**
  - decide the next goal from current state (what to discover/score/apply next);
  - dispatch typed tasks to capability agents via the event bus;
  - prioritize the queue;
  - enforce retry/backoff, throttling, and human-in-the-loop pauses
    ([ADR-0008](0008-human-in-the-loop.md));
  - own the **cost-cascade budget** (Haiku → Sonnet → Opus): start cheap, escalate
    only when a task demands it.
- **Explicitly NOT the Planner's job:** discovering jobs, tailoring résumés, running
  the truthfulness gate, scoring rubric internals, talking to ATS/browser/Gmail.
  These belong to capability agents/skills/connectors.

### Prioritization / "Decide" boundary

The **Decide** capability (scoring and ranking opportunities) is owned by the
Planner as a **delegated, swappable scoring step**, not embedded rubric code: the
Planner asks a scoring component "rank these" and orders work by the result. This
keeps prioritization policy in the coordinator while letting the *scoring logic*
evolve (or be promoted to a standalone Decision Agent later) without rewriting the
Planner. We deliberately did **not** mint a separate Decision Agent now — that would
be premature proliferation (see [ADR-0001](0001-agent-oriented-architecture.md)
alternatives). The seam is drawn so promotion is cheap if justified.

## Alternatives considered

- **Planner embeds capability logic ("smart pipeline").** Fast initially, but grows
  into a God Object and recreates the brittleness [ADR-0001] rejects. Rejected.
- **Separate Decision Agent from day one.** Cleaner on paper, but extra moving parts
  before there's evidence the scoring logic is heavy enough to warrant it. Deferred
  behind the swappable scoring seam.
- **Static rule-based scheduler (no reasoning).** Predictable but can't adapt
  prioritization to outcomes. Rejected; LangGraph Planner with explicit guardrails
  chosen instead.

## Trade-offs

- **(+)** Clear, enforceable boundary keeps the core small; inspectable/resumable
  decisions; one place for budget, retry, and supervision policy.
- **(−)** A reasoning coordinator is nondeterministic (constrained by explicit
  policy + promptfoo evals); the Planner is critical-path and must be especially
  well-tested; the Decide seam adds one indirection.

## Consequences

- Phase 2 specifies the Planner's typed task/decision contract and the scoring
  component interface.
- Reviews check that no capability logic has leaked into the Planner.
- Cost-cascade policy and human-in-the-loop pause points are configured here.

## Future revisit criteria

Revisit if:

- Scoring/Decide logic grows complex or independently valuable enough to promote to
  a first-class Decision Agent.
- The Planner graph itself becomes hard to reason about (split into sub-graphs).
- Budget/cascade policy needs per-capability autonomy beyond a central owner.
- A non-LLM scheduler proves sufficient and cheaper for the coordination role.
