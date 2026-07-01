# ADR-0004: Plugin architecture

- **Status:** Accepted
- **Date:** 2026-06-30
- **References:** [ADR-0000](0000-project-philosophy.md) (Golden Rule #4),
  [ADR-0001](0001-agent-oriented-architecture.md), [ADR-0005](0005-event-bus.md)

## Context

The system's value grows by integrating more of the outside world: ATS adapters
(Greenhouse, Lever, Ashby, Workday), opportunity sources (YC, Hacker News, career
pages), search providers (Exa, Google CSE, Brave), AI models, document exporters,
storage backends, and notification sinks. If any of these are referenced directly
by core code, every addition becomes a core edit and the project ossifies.

## Problem

How do we make every external capability **replaceable** and additive, so a
contributor can add (or swap) a provider without modifying — or even reading —
core orchestration code?

## Decision

Adopt a **plugin-first architecture**. Everything external is a **plugin** behind a
typed interface, discovered through a central **plugin registry**.

- **Self-registration.** Plugins register themselves against a well-known extension
  point (e.g. via an entry-point/decorator mechanism) at startup. Core code asks
  the registry "what `ATSAdapter`s exist?" — it never names a concrete one.
- **Interface-based.** Plugins communicate only through interfaces (Phase 2) and
  the event bus ([ADR-0005](0005-event-bus.md)); callers depend on the abstraction,
  never the implementation (dependency inversion).
- **No hardcoded names.** Selection is by capability/health/config
  ([ADR-0002](0002-search-provider-abstraction.md) is the canonical example), never
  by `if provider == "google"`.
- **Extension points (initial):** `SearchProvider`, `ATSAdapter`,
  `OpportunitySource`, `ModelProvider`, `DocumentExporter`, `StorageBackend`,
  `NotificationSink`.

The contract from [ADR-0001](0001-agent-oriented-architecture.md) holds: adding a
capability requires **only** a plugin registration plus event wiring. If it ever
requires editing core orchestration, that is a design smell to be corrected.

## Alternatives considered

- **Direct imports / factory `if/elif` chains.** Simple at first, but every new
  provider edits the factory; violates open/closed and Golden Rule #4. Rejected.
- **Configuration-only (no registry), instantiate from class paths.** Works, but
  loses capability/health introspection and a single discovery point. Rejected as
  the primary mechanism (class-path config may still configure *which* registered
  plugins are enabled).
- **A heavyweight third-party plugin framework.** Overkill for a single-user app;
  adds a dependency and concepts we don't need. Rejected in favor of a thin
  registry + Python entry points.

## Trade-offs

- **(+)** Open/closed by construction; providers are swappable and testable in
  isolation (register a fake); core stays small and stable.
- **(−)** A layer of indirection (registry + interfaces) that can feel like
  ceremony for a one-off; misconfigured/duplicate registrations need clear errors
  (mitigated with validation at registration time).

## Consequences

- The registry + event bus are built first (Phase 3) before any capability agent.
- Tests register lightweight fake plugins instead of hitting real services.
- Documentation must keep an up-to-date catalog of extension points and registered
  plugins.

## Future revisit criteria

Revisit if:

- Plugin count exceeds ~100 and registry lookup/validation becomes a hotspot.
- We need third-party (out-of-tree) plugins with versioned compatibility
  guarantees, which would warrant a more formal plugin SDK/ABI.
- Security isolation between plugins becomes a requirement (e.g. untrusted plugins).
