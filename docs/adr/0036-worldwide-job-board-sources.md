# ADR-0036: Worldwide job-board sources — eight Tier A APIs, Tier C recorded manual-only

- **Status:** Accepted
- **Date:** 2026-07-04
- **References:** [ADR-0004](0004-plugin-architecture.md) (plugin extension
  points), [ADR-0012](0012-opportunity-provenance-and-confidence.md)
  (required provenance), [ADR-0014](0014-cross-source-opportunity-identity.md)
  (canonical company + dedup these sources feed unchanged)

## Context

Phase 12 of the standing master brief: worldwide + regional discovery
expansion. All new sources are `OpportunitySource` plugins behind the
existing, unchanged Protocol — `interfaces.py`'s `fetch(since)` contract
survives its ninth through sixteenth implementations exactly as ADR-0004
promised.

## Decision

**Tier A — eight free, permitted JSON APIs built** (`plugins/sources/
job_boards.py`): Adzuna (multi-country incl. India, app_id/app_key), Reed
(UK, key via Basic auth), USAJobs (US gov, Authorization-Key header +
registered user-agent), Arbeitnow (Europe, keyless), The Muse (keyless),
Remotive (remote-global, keyless), RemoteOK (remote-global, keyless,
**attribution obligation carried in every emitted provenance reference**
per their API terms), Jooble (multi-country aggregator, free key, POST).
One shared `_build` normalization path so all eight emit identical
`Opportunity` shape: required provenance (`structured_api`, confidence
1.0), `canonical_company` from the normalized company name (aggregator
URLs must never become company identities — every posting would collapse
onto the board's domain), `source="job_board"` (one additive Literal
value), client-side `since` filtering with the keep-when-undated rule
(Greenhouse's precedent). `HttpClient.get_json` gained an optional
`headers` param — additive, the exact precedent of `post_json` gaining
`headers` in 4c-slice-2 — because Reed and USAJobs authenticate GETs.

**Jooble's key never enters stored data**: the API puts the key in the
URL path by design, so the recorded provenance reference is the base URL
with a `<key>` placeholder — injection-verified (recording the real URL
was caught by the dedicated test).

**Tier B — JSearch/RapidAPI: evaluated, not built.** Its value is
Google-for-Jobs aggregation, but it is paid beyond trivial volume and its
core coverage substantially overlaps Adzuna's (which is free and already
covers the priority countries including India). Revisit criterion: real
usage shows a coverage hole Adzuna+Jooble don't fill.

**Tier C — manual-only, a deliberate boundary, not a gap:** Naukri,
Foundit, LinkedIn, Indeed, Seek have no permitted programmatic path — no
public applicant-facing APIs, ToS prohibiting scraping. **No scrapers
will be built for them** (standing invariant 7). They work today as
manual sources: the user pastes a posting into the opportunity-file
handoff `apply` already consumes, which is source-agnostic by design
(ADR-0026).

## Trade-offs

- **(+)** Worldwide + India coverage through clean, free, ToS-respecting
  APIs; zero interface churn; dedup and provenance guarantees inherited.
- **(−)** Page-1-only fetching per source this slice (50-ish newest
  postings per poll) — honest for a personal-scale poller; pagination is
  a revisit criterion if real polling shows misses.
- **(−)** Reed dates are day-granular (DD/MM/YYYY); same-day re-polls may
  re-fetch — dedup absorbs this.

## Future revisit criteria

- A real coverage hole Adzuna+Jooble don't fill → re-evaluate JSearch
  with its real pricing.
- Any Tier C platform ships a permitted API → build it as a plugin then.
- Polling shows page-1 misses → add pagination per source.
