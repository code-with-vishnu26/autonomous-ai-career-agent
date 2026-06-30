# ADR-0001: Agent-oriented architecture (not a fixed pipeline)

- **Status:** Accepted
- **Date:** 2026-06-30
- **References:** [ADR-0000](0000-project-philosophy.md) (root philosophy)

## Context

The Autonomous AI Career Agent must deliver four capabilities — **Discover →
Decide → Apply → Learn** — for a single self-hosted user. The naive design is a
linear pipeline: discover jobs, score them, apply, record outcomes, repeat.

A fixed pipeline is a poor fit for this problem:

- **The work is non-linear.** Real job-seeking interleaves activities: a
  rejection should trigger re-prioritization; a promising lead should jump the
  queue; a failed application should be retried through a different channel.
- **The capability surface keeps growing.** New ATS adapters, sources (YC, Hacker
  News, career pages), and search providers (Exa, Google CSE) will be added
  continuously. In a pipeline, each addition risks editing shared, brittle
  orchestration code.
- **Failure handling and prioritization are first-class.** Retries, backoff,
  throttling, human-in-the-loop pauses, and a cost budget (the Claude
  Haiku→Sonnet→Opus cascade) benefit from a reasoning layer, not scattered `if`s.
- **Truthfulness must be enforceable centrally.** A fabrication-detection gate is
  easier to guarantee at a coordinator-owned boundary than sprinkled through
  pipeline stages.

## Problem

How do we structure the system so that capabilities can be added without rewiring
the core, the flow can adapt and recover instead of running a fixed order, and
cross-cutting guarantees (truthfulness, supervision, cost) are enforced in one
place?

## Decision

Adopt an **agent-oriented architecture** centered on a **Planner Agent** (the
brain) that decides what to do next and dispatches work to specialized agents:

- **Planner Agent** — plans, routes, prioritizes, retries, and owns the cost
  budget. Built on **LangGraph** so its decision loop is inspectable and
  resumable. (Detailed in [ADR-0007](0007-planner-agent.md).)
- **Specialized capability agents** — **Discovery**, **Resume**, **Apply**,
  **Learning** — each owning one capability.
- **Supporting concerns** — analytics (a read model over stored outcomes) and
  notifications (a plugin sink) are treated as cross-cutting concerns, not
  first-class agents, until complexity justifies promoting them. Recorded so the
  boundary is easy to revisit.

Agents do **not** call each other directly. They communicate through:

1. A **plugin registry** ([ADR-0004](0004-plugin-architecture.md)) — capabilities
   self-register against well-known extension points.
2. An **event bus** ([ADR-0005](0005-event-bus.md)) — agents publish and subscribe
   to events (e.g. `OpportunityDiscovered`, `ResumeTailored`,
   `ApplicationSubmitted`, `OutcomeRecorded`).

### Design principles for all agents

Every current and future agent **must** be designed to these rules:

- **Single responsibility** — one agent owns exactly one capability.
- **Stateless whenever possible** — state lives in storage/events, not in agent
  instances; this keeps agents resumable and independently testable.
- **Event-driven communication** — agents react to and emit events.
- **No direct dependencies between agents** — an agent never imports or calls
  another agent.
- **Planner coordinates only** — orchestration logic lives in the Planner; the
  Planner does not embed capability logic.
- **Every agent exposes a public interface** — a typed contract (Phase 2) is the
  only way the Planner interacts with it; internals stay private.

If a change requires breaking one of these, stop and record a superseding ADR.

### Agent lifecycle

The Planner drives every delegated unit of work through one consistent lifecycle,
so all agents behave predictably:

```
Plan      →  Planner decides the next goal from current state
  ↓
Delegate  →  Planner dispatches a typed task to one capability agent
  ↓
Monitor   →  Planner observes events/results, enforces timeouts & budget
  ↓
Recover   →  on failure: retry / backoff / reroute (e.g. API → browser → email)
  ↓
Complete  →  result persisted, outcome event emitted, Planner re-plans
```

This makes every future agent consistent: it receives a typed task, does its one
job, emits an outcome event, and never decides what happens next.

## Alternatives considered

- **Fixed linear pipeline.** Simplest to build, but brittle under a growing
  capability surface and unable to express non-linear prioritization/retry.
  Rejected.
- **Monolithic single agent.** One LLM agent doing everything. Hard to test, hard
  to bound costs, conflates concerns. Rejected.
- **Pure workflow engine without a reasoning planner.** Deterministic and
  inspectable, but pushes prioritization/retry into static config that can't
  adapt. Rejected in favor of a LangGraph Planner with explicit guardrails.
- **Maximal agent roster (separate Decision/Analytics/Notification agents).**
  More "pure," but premature proliferation. Prioritization stays in the Planner
  as a swappable step; analytics/notifications stay cross-cutting until justified.

## Trade-offs

- **(+)** New capabilities are plugins, not core edits; agents are independently
  testable; reasoning-based recovery; centrally enforced guarantees.
- **(−)** More upfront machinery (registry + bus) than a pipeline; event
  indirection can obscure end-to-end traces (mitigated by structured logging +
  LangGraph's inspectable state); a reasoning Planner is nondeterministic
  (constrained by explicit policy, the cost cascade, and promptfoo evals).

## Consequences

- Establishes the contract: adding a capability requires only a plugin plus event
  wiring. If it ever requires editing core orchestration, that is a design smell
  to be corrected via a follow-up ADR.
- The agent lifecycle and design principles above become the review checklist for
  every new agent PR.

## Future revisit criteria

Revisit this decision if:

- The Planner's coordination logic itself becomes a God Object (a sign a capability
  leaked into it).
- Multiple users / multi-tenancy is ever required (out of scope today).
- Cross-cutting analytics or notifications grow enough logic to justify promotion
  to first-class agents.
- The plugin count exceeds ~100 and registry/bus throughput becomes a bottleneck.
- An agent legitimately needs to depend on another agent's behavior synchronously
  (would indicate the capability boundaries are wrong).
