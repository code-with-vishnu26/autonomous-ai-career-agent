# ADR-0015: Web-search results are classified, not trusted (applying ADR-0013)

- **Status:** Accepted
- **Date:** 2026-07-02
- **References:** [ADR-0002](0002-search-provider-abstraction.md) (search
  provider abstraction), [ADR-0013](0013-held-candidate-mechanism.md)
  (held-candidate mechanism), [ADR-0014](0014-cross-source-opportunity-identity.md)
  (two-key identity)

## Context

4c slice-2 adds the first `SearchProvider` (Exa). A raw search result (a URL, a
title, a snippet) is not a confirmed job posting — the same uncertainty problem
Hacker News posed in ADR-0013, wearing a different hat. This is not a new
decision so much as the deliberate reapplication of an existing one: rather than
invent a parallel classification mechanism for search, this ADR states plainly
that search results go through the same held-candidate discipline.

A further wrinkle specific to search: a URL that *matches a known ATS pattern*
(e.g. `boards.greenhouse.io/acme/jobs/123`) looks authoritative by shape alone.
It is tempting to treat a URL-pattern match as confirmation and emit at
confidence 1.0. That temptation is rejected here explicitly, because it is the
same failure mode as trusting a clean-pipe HN post without checking its content
(ADR-0013's #8 case): a search index can be stale, a listing can be expired or
removed, the URL can 404. A pattern match is a strong *signal*, not proof.

## Decision

**`SearchOpportunitySource`** (the discovery-side consumer of `SearchProvider`
results, a separate component from the provider itself — same role split as
`HttpClient` vs. `HNSource`) classifies every search result:

1. **URL matches a known ATS pattern (Greenhouse/Lever/Ashby):** the hit is
   handed to the *real* ATS source (`GreenhouseSource`/`LeverSource`/
   `AshbySource`, reused as-is) to confirm by actually re-parsing the board.
   - **Confirmed** (the job id is found): the returned `Opportunity` *is* the
     ATS source's own record — same id, `method="structured_api"`,
     `extraction_confidence=1.0`. It naturally dedups against an already-known
     ATS-sourced record via ADR-0014's two-key identity, exactly as if the ATS
     source had found it directly. **Confidence 1.0 is earned by parsing, never
     by URL shape alone.**
   - **Not confirmed** (404, id not present, fetch error): held, not emitted,
     despite matching the pattern (`reason="below_threshold"`,
     confidence `0.4`, tunable).
2. **URL matches no known ATS pattern** (a career page, a blog post, a generic
   company site): held directly (`reason="ambiguous_parse"`, confidence `0.15`).
   Classifying arbitrary web content into a confident posting is out of scope
   for this slice — a future slice may add structured extraction for career
   pages, at which point it gets the same parse-or-hold discipline.

Held candidates use the existing `HeldCandidateSink` with `source="web_search"`
(already a valid `HeldCandidate.source` and `Opportunity.source` value — no
domain model change was needed for this ADR). `canonical_company` for confirmed
hits comes from the reused ATS source's own value; nothing new is needed there
either.

### A minor Protocol touch, disclosed

`HttpClient` gained `post_json` (additive; `get_json` unaffected) because Exa's
real search API is POST with a JSON body, not GET with query params — a
GET-only port could not honestly reach it once run against the real service.
This is a smaller category of change than a new port (ADR-0013's "new
discovery-side ports are stop-and-discuss" applies most directly to
`OpportunitySource`-adjacent ports), but it is called out explicitly rather than
folded in silently.

## Alternatives considered

- **Trust an ATS-pattern URL match as confirmation (confidence 1.0 on match).**
  Rejected: a stale or expired listing becomes a phantom confident job — the
  same failure mode ADR-0013 exists to prevent, via a different door.
- **A separate classification mechanism for search** (not reusing
  `HeldCandidateSink`). Rejected: search results are the same kind of
  uncertain signal HN comments are; a parallel mechanism would duplicate
  ADR-0013 for no reason.
- **Classify generic (non-ATS-pattern) URLs by content** (fetch and text-parse
  the page). Deferred, not rejected: out of scope for this slice; a future
  slice can add it once there is a real content-extraction design, and it must
  get the same parse-or-hold treatment as everything else.

## Trade-offs

- **(+)** No phantom jobs from a stale search index; the confirmed path reuses
  already-tested ATS parsing rather than duplicating it; zero domain-model
  changes were needed (`source="web_search"` already existed).
- **(−)** An extra network round-trip (or two) to confirm each ATS-pattern hit;
  generic (non-ATS) postings are never emitted by this slice, even genuinely
  real ones on a career page — a real recall gap, deliberately accepted (the
  same "low recall is recoverable, low precision is corrosive" trade-off as HN).

## Consequences

- `SearchOpportunitySource` depends on the already-built `GreenhouseSource`/
  `LeverSource`/`AshbySource` classes for confirmation — a real, tested
  dependency, not a new parsing implementation to maintain in parallel.
- The `interfaces.py` diff for this slice is exactly one additive method
  (`post_json`); `OpportunitySource`, `OpportunityRepository`, and
  `HeldCandidateSink` are unchanged.

## Future revisit criteria

Revisit if:

- A career-page/blog content-classification design is built, needing its own
  confidence calibration and adversarial test matrix (the HN pattern, a third
  time).
- Google CSE (the second provider) needs a shape `SearchProvider`/`SearchQuery`
  cannot express.
- The confirm-via-real-ATS-source approach proves too slow/expensive at volume,
  warranting a lighter-weight single-item confirmation endpoint per ATS.
