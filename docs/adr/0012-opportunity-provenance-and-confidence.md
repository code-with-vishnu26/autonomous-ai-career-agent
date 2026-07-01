# ADR-0012: Opportunity provenance and extraction confidence

- **Status:** Accepted
- **Date:** 2026-07-01
- **References:** [ADR-0003](0003-truthfulness-gate.md) (don't let unverified
  content flow as if clean), [ADR-0001](0001-agent-oriented-architecture.md),
  ROADMAP Phase 4 (discovery sub-slices)

## Context

Discovery began with ATS-shaped sources (Greenhouse, Lever, Ashby, then the YC
feed): structured APIs returning discrete job objects, where the source *is* the
ground truth. The next sources are fundamentally different — Hacker News "Who's
Hiring" is a single thread of freeform prose comments, with no structured job
object, no per-company boundary, and no clean title/location fields. Opportunities
must be *extracted from text* rather than fetched, and that extraction is
sometimes ambiguous (a comment might be a reply, or prose with no clear role).

Everything discovery emits eventually feeds the truthfulness-gated apply path. A
source that emits confident-looking `Opportunity` objects from ambiguous prose is
the discovery-side analogue of fabrication — it pollutes the funnel with jobs
that may not exist or are mis-parsed. The current `Opportunity` model gives a
source no honest way to say "I'm not sure this is a real posting."

## Problem

How does a freeform source represent *uncertainty* about what it extracted, such
that low-confidence extractions cannot silently flow downstream as confident
opportunities — without bolting an HN-only afterthought onto the model, and
without changing the `OpportunitySource` contract every source binds to?

## Decision

Add a **required** `provenance: Provenance` field to `Opportunity`. `Provenance`
records how an opportunity was derived and how confidently:

```
Provenance:
  method: "structured_api" | "structured_feed" | "text_extraction"
  reference: str                       # stable pointer to the RAW source item
  extraction_confidence: float (0..1)
```

- **The Protocol does not change.** `OpportunitySource.fetch(since) ->
  list[Opportunity]`, `HttpClient`, and `OpportunityRepository` are untouched.
  The change lives entirely in the `Opportunity` *payload* (`domain/models.py`).
  This is what makes this a principled contract *evolution*, not a seam leak: the
  interface every source binds to is stable; the domain object gains an honest
  field. If a freeform source ever forced the Protocol itself to change, that
  would be a different and more serious decision.
- **`provenance` is required (no default).** This is the enforcement mechanism,
  not decoration: a source physically cannot construct an `Opportunity` and leave
  provenance blank, so structured sources *must* set `method="structured_api"`/
  `"structured_feed"` and `extraction_confidence=1.0`, and the three already-built
  ATS sources plus the YC feed were updated to do so in the same change.
  Universality is therefore compiler-enforced and visible in the diff, not
  promised — the opposite of a nullable field only the messy sources populate.
- **`extraction_confidence` lives inside `Provenance`, beside `method`.**
  Confidence is a property of *how* an opportunity was derived, not of the
  opportunity itself: a `0.4` from `text_extraction` and a `1.0` from
  `structured_api` are the same field but are claims about the parsing, not the
  job. Nesting keeps `method` and `extraction_confidence` lexically adjacent so a
  reader cannot threshold on the number without the method right beside it.
- **`reference` is distinct from `source_url`.** `source_url` is the human
  apply/view page; `reference` is the audit pointer to the *raw item parsed* (an
  ATS API item; later, an HN comment permalink, which is not the apply link
  buried in the prose). It is the trail back to exactly what was read, which is
  what makes a low-confidence extraction reviewable.

Freeform sources (HN, a later slice) will emit an `Opportunity` only above a
confidence threshold; ambiguous extractions are held/counted, never emitted as
confident opportunities. This ADR lands the *model* that makes that possible; it
rides in with the YC source — the trivial-confidence end (`1.0`) — so the change
is designed as a clean universal addition on calm ground before HN exercises the
`< 1.0` path.

## Alternatives considered

- **Separate `OpportunityCandidate` staging type** (keep `Opportunity` pristine;
  promote confident candidates). Rejected: provenance and confidence are useful
  for *every* source (apply-path traceability; the Learning engine's later
  source-weighting), so they belong on the type, not on a parallel staging shape
  that taxes every source's code path to serve only the freeform ones. That is
  "Option B wearing Option A's clothes."
- **Threshold-and-drop, no model change** (freeform sources silently emit only
  high-confidence opportunities). Rejected: honest downstream but *blind* — a
  quality system that cannot see its own discard pile cannot improve, and an
  `Opportunity` could not even record that it came from prose.
- **`extraction_confidence` top-level on `Opportunity`.** Rejected: it silently
  asserts confidence is an intrinsic attribute of the job and invites reasoning
  about the number without the extraction method beside it.

## Trade-offs

- **(+)** Uncertainty is representable honestly; the truthfulness philosophy
  (don't let unverified content pass as clean) extends to discovery; provenance
  gives every opportunity an audit trail; universality is enforced by the type
  system.
- **(−)** A required field touches every `Opportunity` construction site (four
  sources + test helpers) — intentional churn that *proves* universality. A
  structured source's `reference` sometimes closely mirrors `source_url` (minor
  redundancy), accepted for the freeform case where they genuinely diverge.

## Consequences

- The three merged ATS sources and the new YC source all populate `provenance`
  with `extraction_confidence=1.0`; the diff shows universality directly.
- The HN slice can now emit real `< 1.0` confidences and gate emission on a
  threshold, with the adversarial "ambiguous comments stay held" test as its
  load-bearing deliverable.
- The Learning engine (Phase 8) may later weight or filter by
  `provenance.method` / `extraction_confidence`.

## Future revisit criteria

Revisit if:

- A freeform source genuinely cannot be represented without changing the
  `OpportunitySource` **Protocol** (not just the payload) — a stop-and-discuss.
- Confidence needs to become multi-dimensional (e.g. separate company vs. role
  confidence) rather than a single scalar.
- Downstream consumers need a richer provenance (raw captured text, extractor
  version) than method + reference + confidence.
