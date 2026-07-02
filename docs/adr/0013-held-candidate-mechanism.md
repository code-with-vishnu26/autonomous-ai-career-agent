# ADR-0013: Held-candidate mechanism for freeform extraction sources

- **Status:** Accepted
- **Date:** 2026-07-01
- **References:** [ADR-0003](0003-truthfulness-gate.md) (don't let unverified
  content pass as clean), [ADR-0012](0012-opportunity-provenance-and-confidence.md)
  (the confidence channel), ROADMAP Phase 4 (4b-feeds-HN)

## Context

Hacker News "Who is Hiring" is the first *extraction* source (vs. *fetch*): its
input is a thread of freeform prose comments, and the source must decide what is
a job, what is not, and how confident it is. That decision is the discovery-side
analogue of the truthfulness gate. A confident-looking phantom -- a reply, a
"seeking work" post, or vague prose turned into a clean `Opportunity` -- is
fabrication upstream of where the gate normally catches it, and it would pollute
the truthfulness-gated apply path with jobs that may not exist. Low recall in
discovery is recoverable (you miss some jobs); low precision is corrosive (you
inject phantoms). So the source must be conservative *and* it must not throw away
what it rejects -- a quality system that cannot see its own discard pile cannot
improve.

## Problem

How does a freeform source (a) avoid emitting anything it is not confident is a
real posting, and (b) make everything it rejects visible and auditable -- without
changing the `OpportunitySource.fetch` contract every source binds to, and
without demoting non-jobs into low-confidence `Opportunity` objects?

## Decision

Introduce a **held-candidate mechanism**:

- **`HeldCandidate` is its own domain type**, not a low-confidence
  `Opportunity`. A reply or a candidate self-post is not a job we are merely
  unsure about -- it is often not a job at all. Demoting it to a low-confidence
  `Opportunity` would corrupt the meaning of that type (which must always mean "a
  job we vouch is real") and hand the gate things that were never postings. This
  is the same discipline as `TailoredResumeDraft` vs `TailoredResume`: model the
  uncertain thing as its own type, not a nullable field on the certain one.
  `HeldCandidate` carries `reason`, `reference` (the raw item, e.g. an HN comment
  permalink), `raw_excerpt`, and the sub-threshold `extraction_confidence` (the
  ADR-0012 channel).
- **`HeldCandidateSink` is a new, additive, optional port** injected into the
  source. Confident postings are returned via `fetch()`; everything else is
  written to the sink. `fetch(since) -> list[Opportunity]` does **not** change,
  and the sink imposes nothing on the structured sources (they never hold). The
  additivity test this passes -- and the test to apply to any future
  discovery-side port -- is: *optional collaborator, no change to existing
  sources, no change to the shared `Opportunity`/`fetch` contract.* A port that
  instead made every source implement something, or changed `fetch()`'s return to
  `tuple[list[Opportunity], list[HeldCandidate]]`, would cross the pin and be a
  stop-and-discuss.
- **Visibility via a bus-backed sink in production.** `InMemoryHeldCandidateSink`
  lets tests assert exactly which archetype produced which held reason;
  `BusHeldCandidateSink` publishes a `CandidateHeld` event so the discard pile
  lands on the event bus (the visibility spine) for a dashboard or the Learning
  engine. Held candidates are never silently dropped.
- **Thresholding lives in the source; confidence tracks format recognizability.**
  The pipe convention (`Company | Role | Location | ...`) that a large fraction of
  posts follow scores high because the format is *unambiguous*, not because the
  parser tried hard; freeform prose scores low. The source emits only at/above a
  configurable threshold and holds the rest. Errors therefore fall toward holding
  real jobs, not emitting phantoms.
- **Extraction is heuristic; the LLM is deferred.** A high-precision heuristic
  parser (with structural, script-agnostic field checks) is used now; LLM-based
  extraction is its own later phase that will raise recall against this
  honest-confidence scaffolding rather than drag nondeterminism into discovery.

### Documented behavior decisions (the "decide, don't leave undefined" cases)

The failure is not the choice; it is the *absence* of a choice. Both below are
tested to hold:

- **Multi-job comment (one comment, N pipe-delimited roles):** parsed **per
  posting-header line**; each qualifying line emits independently, and a bad line
  among good ones is held on its own. Never first-only, never fused.
- **Non-English / mixed-script post:** the classifier is **script-agnostic and
  must never crash**. Junk-role and missing-company checks are structural
  (sentence punctuation, empty fields, unicode word-character presence), not
  English-keyword allowlists, so a structurally valid CJK/RTL post emits.

### Held reasons

`below_threshold` (looked like a posting but a required field failed -- missing
company, junk role, or partial structure), `not_a_posting` (a reply, question, or
meta noise), `seeking_work` (a candidate advertising themselves), `ambiguous_parse`
(job-adjacent prose with no parseable structure).

## Alternatives considered

- **Low-confidence `Opportunity` for held items (no separate type).** Rejected:
  corrupts the meaning of `Opportunity` and feeds the gate non-jobs.
- **Threshold-and-drop (no record).** Rejected: honest downstream but blind; the
  discard pile must be visible ([ADR-0012](0012-opportunity-provenance-and-confidence.md)
  rejected the same for the same reason).
- **Return `tuple[list[Opportunity], list[HeldCandidate]]` from `fetch`.**
  Rejected: changes the shared Protocol every source binds to -- crosses the pin.

## Trade-offs

- **(+)** Phantoms cannot escape; the discard pile is visible and auditable; the
  `Opportunity` type stays honest; the Protocol is unchanged.
- **(−)** Conservative heuristics hold some real jobs (accepted -- recoverable,
  the safe direction); the heuristic is HN-format-specific and will mis-handle
  posts that ignore the convention (mitigated later by LLM extraction); the
  `BusHeldCandidateSink` currently binds a correlation id at construction, so a
  per-run correlation is a composition-root wiring detail.

## Consequences

- The HN source is validated against a reviewer-defined 12-archetype adversarial
  matrix; the load-bearing test is "ambiguous comments are held with the correct
  reason, never emitted."
- HN opportunities key their id on the `canonical_fingerprint` (no ATS ref), so
  re-posts dedup through the *same* path structured sources use -- reinforcing the
  4c company-identity / dedup checkpoint already logged.
- The Learning engine (Phase 8) can consume `CandidateHeld` to see what discovery
  discards and tune the threshold from evidence.

## Future revisit criteria

Revisit if:

- LLM-based extraction lands (its own ADR) and changes how confidence is scored.
- A freeform source genuinely cannot be served without changing the
  `OpportunitySource` **Protocol** (not just adding a sibling port) -- stop and
  discuss.
- Held-candidate volume or review needs warrant a durable held store rather than
  an event/in-memory sink.
