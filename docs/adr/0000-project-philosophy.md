# ADR-0000: Project philosophy

- **Status:** Accepted; the "Multi-tenancy or a hosted SaaS" non-goal below is
  **partially superseded by [ADR-0078](0078-saas-multi-tenant-platform.md)**
  (Phase 60) -- see that ADR and the "Future revisit criteria" note at the
  bottom of this document for what changed and why. Every other non-goal
  and golden rule on this page is unchanged and still binding.
- **Date:** 2026-06-30

> This is the root ADR. Every other ADR is made in service of this one and may
> reference it. When two decisions conflict, the one more aligned with this
> philosophy wins.

## Context

We are building an **Autonomous AI Career Agent**: a single-user, self-hosted
"career operating system" that a person runs on their own machine with their own
accounts and data. It is **not** a job-application bot, **not** a browser-automation
script, **not** a résumé generator, and **not** a multi-tenant SaaS. Without a
written philosophy, a project like this drifts toward volume, cleverness, and
feature sprawl. This ADR fixes the north star so every later decision and pull
request can be checked against it.

## Problem

What is the system optimizing for, what will it deliberately **not** do, and what
non-negotiable rules govern engineering and behavior — such that contributors
years from now make consistent choices without re-litigating fundamentals?

## Decision

Adopt the following as the project's constitution.

### Mission

Build the most capable open-source Autonomous AI Career Agent: continuously
discover high-quality opportunities, prepare **truthful** personalized
applications, submit them under user-defined controls, track the hiring
lifecycle, and improve over time from real outcomes.

### Optimization objective

**Maximize interview rate per application** — *not* the number of applications.

```
Quality      over  Volume
Truthfulness over  Optimization
Maintainability over Cleverness
```

### Goals

- High-signal discovery from open, ToS-respecting sources.
- Truthful, evidence-grounded tailoring of applications.
- Supervised, human-in-the-loop submission the user stays in control of.
- A learning loop driven by real outcomes (responses, interviews, offers).
- A codebase maintainable for many years by a small team.

### Non-goals

- Mass / spray-and-pray applying.
- Multi-tenancy or a hosted SaaS.
- Bypassing CAPTCHAs, verification, or platform policies.
- Automating Google OAuth or any login the provider intends a human to perform.
- Fabricating, embellishing, or "optimizing" résumé content beyond the user's facts.

### Engineering principles

SOLID · Clean Architecture · composition over inheritance · dependency injection ·
interface-first design · plugin-first architecture · event-driven communication ·
configuration over hardcoding · testability first · simplicity over complexity ·
small reusable modules. Dependencies point **downward** only
(Presentation → Planner → Agents → Skills → Connectors → Infrastructure); no
circular dependencies.

### Golden rules (never violate without a superseding ADR)

1. Never rewrite major architecture without discussion.
2. Never introduce breaking changes silently.
3. Never create God Objects.
4. Never hardcode providers (search, ATS, model, storage, notifications).
5. **Never fabricate application content** ([ADR-0003](0003-truthfulness-gate.md)).
6. Never bypass CAPTCHA or violate platform policies
   ([ADR-0008](0008-human-in-the-loop.md)).
7. Never optimize for application quantity.
8. Every architectural decision must improve maintainability.

## Alternatives considered

- **No written philosophy** (let conventions emerge). Rejected: invites drift
  toward volume and feature sprawl, and forces every debate to restart from zero.
- **Optimize for application throughput.** Rejected: directly contradicts the
  quality-and-truthfulness thesis and produces low-signal spam.
- **General multi-purpose automation platform.** Rejected: scope explosion;
  single-user career focus is the entire value proposition.

## Trade-offs

- **(+)** A durable contract: PRs and ADRs are checkable against it; onboarding is
  faster; the product stays coherent.
- **(−)** Some attractive features (mass apply, multi-tenant) are ruled out by
  fiat; contributors must internalize the rules rather than chase local wins.

## Consequences

- Every other ADR cites or conforms to this one.
- "Does this improve interview-rate-per-application and maintainability, without
  violating a golden rule?" becomes the standard review question.

## Future revisit criteria

Revisit this philosophy if:

- The project's intended audience changes from single self-hosted user to a hosted
  / multi-user product (would invalidate several non-goals). **Triggered by
  ADR-0078 (Phase 60):** the audit for that phase found this exact trigger had
  occurred -- the brief asked for a real Organizations/RBAC/billing platform,
  which is precisely "hosted / multi-user product." The user confirmed the
  change explicitly rather than it being assumed. Only the multi-tenancy
  non-goal is affected; every other non-goal (mass-apply, CAPTCHA-bypass,
  automating provider-intended-human logins, fabricating résumé content)
  is untouched and still absolute. The CLI remains the single-operator,
  self-hosted power-user tool it always was (ADR-0078's own scoping) --
  multi-tenancy applies to the dashboard/API only.
- The legal/ToS landscape changes such that current source strategies are no longer
  viable.
- Evidence shows the interview-rate objective is being gamed and needs refinement.
