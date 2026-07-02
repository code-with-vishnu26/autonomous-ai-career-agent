# ADR-0019: ATS-kind resolution and no cross-tier auto-retry

- **Status:** Accepted
- **Date:** 2026-07-02
- **References:** [ADR-0010](0010-hybrid-application-strategy.md) (the tiered
  applicator this ADR continues implementing), [ADR-0015](0015-web-search-classification.md)
  (the pattern-match-then-confirm technique reused here), [ADR-0018](0018-submission-safety.md)
  (`SubmittableApplication`, the `prepare`/`submit` split, and confirmation-
  token binding this ADR extends)

## Context

Phase 7a (ADR-0018) built the submission safety machinery — structural
approval and confirmation-token binding — against exactly one injected
`ATSAdapter`, with company/ATS-kind resolution and multi-tier fallback
explicitly deferred. Phase 7b has to resolve which real adapter applies to a
given opportunity, and decide what happens when the chosen tier fails and a
fallback tier might apply. Both are real design decisions, not mechanical
extensions of 7a's shape.

## Problem

How does `TieredApplicator` know which `ATSAdapter` applies to a given
`Application`'s opportunity, and does a tier-fallback attempt (once Tier 2/3
exist) get to reuse the human's original confirmation, or does it need its
own?

## Decision

### ATS-kind resolution: reuse the ADR-0015 pattern-match, don't build a repository

No `CompanyRepository` exists in this codebase, and nothing today needs to
*persist* company records — only to *resolve*, at prepare-time, which
adapter a given opportunity's ATS is. `Opportunity.source_url` already
carries that signal, and `SearchOpportunitySource` (ADR-0015) already
built and tested a pattern-match classifier for exactly this URL shape.
That classifier is extracted from `plugins/sources/web_search.py` into
`domain/ats_urls.py` (`match_ats_url`/`resolve_ats_kind`) — pure pattern
matching, no I/O, so it belongs in `domain` alongside the project's other
dependency-free business rules — and is now a shared source of truth used by
both the web-search classifier and `TieredApplicator.prepare()`, rather than
maintained as two independently-drifting copies of the same regex list.

`TieredApplicator` is constructed with `ats_adapters: dict[str, ATSAdapter]`
(keyed by `ats_kind`) and an `OpportunityRepository` (Phase 4a's existing
port — no new persistence interface). `prepare()` looks up the opportunity,
resolves its `ats_kind` via `resolve_ats_kind(opportunity.source_url)`, and
looks up the matching adapter. If the opportunity can't be found, its URL
matches no known ATS pattern, or the matched kind has no registered adapter,
`prepare()` raises `NoApplicableAdapterError` — explicit and typed, never a
silent no-op or a guessed default adapter.

**Building `CompanyRepository` is deferred, not rejected** — it becomes the
right call the moment something actually needs persisted company data (the
deferred Company Watchlist / Proactive Career Page Monitoring phase is the
most likely trigger), driven by a real requirement rather than speculated in
advance. Same YAGNI discipline as Phase 6's plain-function profile loader.

### No cross-tier auto-retry: each tier attempt gets its own confirmation

A `HumanConfirmation` (ADR-0018) names one exact `SubmissionPreview` — a
specific tier, target, and content shape. Falling back from a failed Tier 1
attempt to Tier 2 (browser) or Tier 3 (email) is not a retry of the same
action through a different transport; it is a **materially different
real-world action** — a different target, and for email, a fundamentally
different content shape than a form submission. Letting a Tier 1 failure
silently cascade into an unconfirmed Tier 2/3 attempt would mean the human
confirmed "submit via this ATS's API" and the system did something they
never actually approved — quietly hollowing out the exact guarantee ADR-0018
exists to provide, one phase later.

**Decision: `TieredApplicator` never auto-cascades across tiers, and never
will.** Each tier attempt is its own `prepare()` → human confirms →
`submit()` cycle, requiring its own `HumanConfirmation`. With only Tier 1
built, this ADR doesn't yet implement fallback logic — there is nothing to
fall back to — but it fixes the shape fallback must take once Tier 2/3
exist: a future orchestration layer (the not-yet-built Apply Agent) decides
whether and how to retry a failed tier, and does so by calling `prepare()`
again for the next tier, never by `TieredApplicator` retrying internally
under the original confirmation.

## Alternatives considered

- **Build `CompanyRepository` now.** Rejected: no actual persistence need
  exists yet; the ADR-0015 pattern-match already resolves what's needed
  without a new interface or storage commitment.
- **Resolve `ats_kind` by re-parsing the full posting via each ATS source in
  turn (like `SearchOpportunitySource._confirm_via_ats_parse` does for
  unconfirmed search hits).** Rejected as unnecessary here: the opportunity
  is already a confirmed, stored record (it passed through discovery and the
  repository), unlike a raw search hit — pattern-matching its already-known
  `source_url` is sufficient; there is nothing left to "confirm" that
  storing it didn't already establish.
- **Let `TieredApplicator.submit()` internally retry the next tier on
  failure, under the same confirmation.** Rejected: this is the core
  decision of this ADR — it would silently authorize an action (e.g. an
  email submission) the human never specifically confirmed, undermining
  ADR-0018's token-binding guarantee one layer up.
- **A confirmation that names a *set* of acceptable tiers instead of one
  exact preview, so one confirmation covers a fallback chain.** Rejected:
  weakens the binding from "the human saw and approved exactly this" to "the
  human pre-approved a family of possible actions," which is a materially
  weaker guarantee and not what ADR-0018 committed to.

## Trade-offs

- **(+)** No new persistence layer; reuses an already-tested classifier
  instead of a second copy; the confirmation guarantee holds across tiers,
  not just within one; an unresolvable opportunity fails loudly and
  specifically rather than silently or ambiguously.
- **(−)** Once Tier 2/3 exist, a failed Tier 1 attempt requires a second
  round of human attention (a new confirmation) rather than one approval
  covering an automatic cascade — slower, but the cost of the guarantee
  ADR-0018 exists to provide; a fully autonomous fallback is explicitly not
  what this project wants for its one irreversible action.

## Consequences

- `domain/ats_urls.py` is new; `plugins/sources/web_search.py` now imports
  from it instead of maintaining its own copy of the pattern list.
- `TieredApplicator.__init__` signature changes from a single `ATSAdapter` to
  `dict[str, ATSAdapter]` + `OpportunityRepository` (Phase 7a had no external
  caller yet, so no migration cost beyond this repo's own tests).
- `NoApplicableAdapterError` is new; any future orchestration layer calling
  `prepare()` must handle it explicitly as "no applicable tier right now,"
  not treat it as equivalent to `ApplicationFailed`.
- Any future Apply Agent/orchestration layer implementing real tier fallback
  must call `prepare()`/obtain a fresh `HumanConfirmation`/call `submit()`
  once per tier attempt — this is now a load-bearing contract, not an
  implementation detail left open.

## Future revisit criteria

Revisit if:

- A real persisted-company-data need emerges (most likely: the Company
  Watchlist phase), at which point `CompanyRepository` should be built and
  `TieredApplicator` should resolve through it instead of (or in addition
  to) URL pattern-matching.
- Tier 2 (browser) or Tier 3 (email) are built and a real Apply Agent needs
  to implement fallback orchestration — this ADR's "each tier its own
  confirmation" rule is the contract that orchestration must honor.
- User feedback shows the "confirm every tier attempt separately" cost is
  too high in practice for how this system is actually used, at which point
  a deliberately-scoped, explicitly-approved relaxation (e.g. "pre-approve
  fallback to Tier 2 only, never Tier 3, for this one application") could be
  designed — not a silent default.
