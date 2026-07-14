# ADR-0087: Enriched Excel Export + Web-Search Company Research

- **Status:** Accepted
- **Date:** 2026-07-13
- **References:** [ADR-0083](0083-web-excel-export.md) (the web Excel export
  this enriches), [ADR-0036](0036-tier-c-manual-only-sources.md) (no
  scraping of people/ToS-restricted platforms), [ADR-0002](0002-search-provider-abstraction.md)
  (the `SearchProvider` protocol reused for research), [ADR-0075](0075-career-coach.md)
  (the deferred "Company Research" coach feature this finally gives a real
  data source)

## Context

The owner asked for the applications Excel to hold accurate job details,
company links, and AI research about the company (careers/contact),
explicitly wanting the details to be **accurate**. Two tensions had to be
resolved before building:

- **Accuracy vs. AI.** Details from the real posting are accurate; an
  LLM-*generated* company brief is not reliably so. Asked, the owner chose
  **web-search-backed research with real source links** over a
  convenient-but-approximate AI summary.
- **"Info about HR / employees."** Scraping named individuals' contact
  data violates the very platforms' ToS this project already refuses to
  scrape (ADR-0036, invariant 7) and is a privacy line. Asked, the owner
  chose **public company channels only** (careers page), no individuals.

**A repository-reality audit found:**

- The Phase 65 export read only the `ApplicationSession`; the accurate
  posting details (location, remote, source, posted date, job URL) live on
  the `Opportunity`, joinable by `opportunity_id`.
- A `SearchProvider` protocol (ADR-0002) with Exa and Google CSE adapters
  already exists; the "Company Research" coach page (ADR-0075) was a
  deferred stub precisely because nothing gave it a data source.
- A private résumé/cover-letter *link* inside a downloaded Excel can't
  carry the browser's in-memory access token, so it would 401. Public
  URLs (job posting, careers page, sources) have no such problem.

## Decision

Enrich the applications export by joining the `Opportunity` and adding
real, source-backed company research.

- `domain/company_research.py`: a `CompanyResearch` model
  (`available`/`summary`/`careers_url`/`sources`), with an explicit
  `unavailable()` factory -- the honest "no search key, we didn't look"
  signal, distinct from "we looked, found nothing". Carries no personal
  data by design.
- `agents/research/company_research.py::research_company(company,
  provider, ...)`: takes the `SearchProvider` *protocol* (never a concrete
  plugin -- the composition root injects it, preserving the layers
  contract), runs one company-overview search, keeps the top results as
  linked sources, and picks a careers/jobs URL. `provider is None` returns
  `unavailable()`; a provider error degrades to empty-but-available. It
  **never** asks an LLM to invent facts.
- `api/dependencies.py::get_search_provider()`: builds Exa (preferred) or
  Google CSE from configured keys, or `None`.
- `storage/excel.py`: `_build_workbook` gains `link_keys` (public-URL
  columns become real clickable hyperlinks); a new
  `enriched_applications_xlsx_bytes` for the richer column set (Prepared,
  Company, Role, Location, Remote, Source, Posted, Status, Job URL,
  Careers Page, Company Research, Research Sources, Cover Letter).
- `GET /export/applications.xlsx` (now `async`): joins each session to its
  `Opportunity`, looks up company research once per distinct company
  (cached; none at all with no key), inlines the caller's own cover
  letter, and streams the enriched workbook. Still read-only, still off
  `/api`, still per-user scoped.

## Consequences

- The applications Excel now carries accurate posting details, clickable
  public links (job posting, careers page, source links), source-backed
  company research, and the tailored cover letter -- what the owner asked
  for, with accuracy preserved.
- Company research is honest about its own absence: with no Exa/Google CSE
  key it says so in the cell rather than inventing a summary. Adding a key
  in Settings enables it with no code change (dependencies are built fresh
  per request).
- No personal data about individuals is ever collected -- public company
  channels only, upholding ADR-0036.
- The résumé is not linked in the Excel (a private link can't authenticate
  from a downloaded file); the tailored résumé remains viewable in the
  Review Queue. A dedicated résumé/cover-letter download endpoint is named
  follow-up work.
- The submissions export is unchanged this phase; enriching it the same
  way is a straightforward follow-up.
