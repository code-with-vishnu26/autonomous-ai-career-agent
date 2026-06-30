# ADR-0001: Agent-oriented architecture (not a fixed pipeline)

- **Status:** Accepted
- **Date:** 2026-06-30

## Context

The Autonomous AI Career Agent must deliver four capabilities — **Discover →
Decide → Apply → Learn** — for a single self-hosted user. The naive design is a
linear pipeline: discover jobs, score them, apply, record outcomes, repeat.

A fixed pipeline is a poor fit for this problem:

- **The work is non-linear.** Real job-seeking interleaves activities: a
  rejection should trigger re-prioritization; a promising lead should jump the
  queue; a failed application should be retried through a different channel. A
  hard-coded order can't express this.
- **The capability surface keeps growing.** New ATS adapters, new opportunity
  sources (YC, Hacker News, career pages), and new search providers (Exa, Google
  CSE) will be added continuously. In a pipeline, each addition risks editing
  shared, brittle orchestration code.
- **Failure handling and prioritization are first-class.** Retries, backoff,
  throttling, human-in-the-loop pauses, and a cost budget (the Claude
  Haiku→Sonnet→Opus cascade) are decisions that benefit from a reasoning layer,
  not scattered `if` statements.
- **Truthfulness must be enforceable centrally.** A fabrication-detection gate is
  easier to guarantee when a coordinator owns the flow than when checks are
  sprinkled through pipeline stages.

## Decision

Adopt an **agent-oriented architecture** centered on a **Planner Agent** (the
brain) that decides what to do next and dispatches work to specialized agents:

- **Planner Agent** — plans, routes, prioritizes, retries, and owns the cost
  budget. Built on **LangGraph** so its decision loop is inspectable and
  resumable.
- **Specialized agents** — **Discovery**, **Resume**, **Apply**, **Learning** —
  each owning one capability.

Agents do **not** call each other directly. They communicate through:

1. A **plugin registry** — ATS adapters, opportunity sources, and search
   providers self-register against well-known extension points.
2. An **event bus** — agents publish and subscribe to events (e.g.
   `OpportunityDiscovered`, `ResumeTailored`, `ApplicationSubmitted`,
   `OutcomeRecorded`).

This is the mechanism that lets new capabilities register **without core
rewrites**, and it is built in Phase 3 before any capability agent.

## Consequences

**Positive**

- New ATS adapters / sources / providers are added as plugins, not core edits.
- The Planner can reprioritize and recover from failures with real reasoning.
- Decoupled agents are independently testable.
- Truthfulness and human-in-the-loop policy are enforced at coordinator-owned
  boundaries.

**Negative / costs**

- More upfront machinery (registry + event bus) than a straight pipeline.
- Indirection via events can make end-to-end traces harder to follow; we mitigate
  with structured logging and LangGraph's inspectable state.
- A reasoning Planner introduces nondeterminism; we constrain it with explicit
  policies, the cost cascade, and promptfoo regression tests.

**Neutral**

- Establishes a contract: adding a capability should require only a plugin plus
  event wiring. If it ever requires editing core orchestration, that is a design
  smell to be corrected via a follow-up ADR.

## Alternatives considered

- **Fixed linear pipeline.** Simplest to build, but brittle under the project's
  growing capability surface and unable to express non-linear prioritization and
  retry. Rejected.
- **Monolithic single agent.** One LLM agent doing everything. Hard to test, hard
  to bound costs, and conflates concerns (discovery vs. truthful tailoring vs.
  supervised applying). Rejected.
- **Pure workflow engine without a reasoning planner.** Deterministic and
  inspectable, but pushes prioritization/retry logic into static configuration
  that can't adapt. Rejected in favor of a LangGraph-based reasoning Planner with
  explicit guardrails.
