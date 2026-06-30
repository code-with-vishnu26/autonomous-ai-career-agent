# ADR-0005: Event bus

- **Status:** Accepted
- **Date:** 2026-06-30
- **References:** [ADR-0001](0001-agent-oriented-architecture.md),
  [ADR-0004](0004-plugin-architecture.md)

## Context

[ADR-0001](0001-agent-oriented-architecture.md) commits to agents that never call
each other directly. They still need to communicate: discovery produces
opportunities the Planner must consider; a tailored résumé must be picked up for
application; outcomes must reach the Learning engine. Something must carry these
signals without creating direct dependencies.

## Problem

How do agents and plugins communicate so that producers and consumers stay
decoupled, new subscribers can be added without touching producers, and the flow
remains inspectable?

## Decision

Provide a central **event bus** with **publish/subscribe** semantics as the sole
inter-agent communication channel.

- **Loose coupling.** Producers emit typed events and don't know who consumes
  them; consumers subscribe to event types and don't know who produced them.
- **No direct service-to-service calls** between agents. The bus is the contract.
- **Typed events.** Events are typed payloads (Pydantic, Phase 2), e.g.
  `OpportunityDiscovered`, `OpportunityScored`, `ResumeTailored`,
  `TruthfulnessRejected`, `ApplicationSubmitted`, `OutcomeRecorded`. The full
  catalog is defined in Phase 2 and documented.
- **Inspectable.** Every event flows through one place, enabling structured
  logging, tracing, and (later) replay for debugging — mitigating the visibility
  cost called out in [ADR-0001](0001-agent-oriented-architecture.md).
- **In-process first.** A single-user, single-process deployment starts with an
  in-process async bus; the interface is kept transport-agnostic so a durable/
  out-of-process backend can be slotted in later without changing publishers or
  subscribers.

## Alternatives considered

- **Direct method calls between agents.** Simple but creates exactly the coupling
  [ADR-0001](0001-agent-oriented-architecture.md) forbids; every new consumer edits
  the producer. Rejected.
- **Shared database polling.** Decoupled but laggy and wasteful; turns the DB into
  an ad-hoc queue. Rejected as the primary channel (DB remains the system of
  record, not the message path).
- **External broker (Redis/Kafka/RabbitMQ) from day one.** Robust and durable, but
  heavy operational burden for a single-user, self-hosted app. Rejected for now;
  the transport-agnostic interface leaves the door open.

## Trade-offs

- **(+)** Decoupled, extensible (add a subscriber freely), centrally observable,
  and aligned with the agent design principles.
- **(−)** Indirection makes call paths less obvious than direct calls; an in-process
  bus offers no durability/at-least-once delivery (acceptable for single-user MVP;
  revisit below); ordering/back-pressure need explicit thought.

## Consequences

- Built in Phase 3 alongside the plugin registry, before any capability agent.
- The event catalog becomes part of the public architecture and must be documented
  and versioned like an interface.
- Tests assert behavior by publishing events and observing emitted events.

## Future revisit criteria

Revisit if:

- We need durability / guaranteed delivery / replay across restarts (move to a
  persistent broker behind the same interface).
- Event volume or fan-out makes in-process dispatch a bottleneck.
- A future multi-process or distributed deployment is required.
- Event ordering or back-pressure guarantees become correctness-critical.
