# ADR-0090: Role Taxonomy Search Expansion + Résumé Public Links

- **Status:** Accepted
- **Date:** 2026-07-14
- **References:** [ADR-0088](0088-search-relevance-and-paste-fix.md) (Phase
  70's original literal-keyword relevance filter, `domain/job_relevance.py`
  -- this phase widens it, in the same file), [ADR-0034](0034-ats-score-gate.md)
  (the deterministic-gate + advisory-LLM-layer pattern this phase's
  optional `RoleExpander` fallback mirrors), [ADR-0089](0089-web-resume-upload-and-signed-resume-links.md)
  (the résumé-generation pipeline this phase adds a links section to)

## Context

The owner asked for two things: (1) a search for "junior software
developer" should be understood as a role, not four literal words --
matching "SWE"/"SDE"/"entry level" postings too -- and should also
surface *related* sub-roles (backend, cloud, DevOps, ...) that "software
developer" genuinely contains, as a distinct, labeled section; (2) a
generated résumé should carry a proper links section under the
applicant's name -- LinkedIn, GitHub, portfolio, project links -- built
from real ATS/resume conventions.

One part of the request could not be honored as literally asked: "you can
analyze the company or company employees' LinkedIn resumes, which are
freely accessible." Scraping named individuals' LinkedIn profiles --
"freely accessible" or not -- violates LinkedIn's own ToS and this
project's own standing rule against collecting personal data on named
individuals (`domain/company_research.py`'s docstring, reaffirmed in
ADR-0087's Context: "the owner's choice was public company channels
only"). This phase does not do it, and builds the résumé-links feature
from public, well-established resume-writing conventions instead --
flagged to the owner rather than silently dropped or silently done anyway.

Two things were found true on inspection, not assumed:

- `domain/job_relevance.py` (Phase 70/ADR-0088) already existed and was
  exactly the right place to extend -- a pure, deterministic bag-of-words
  matcher over the caller's configured `preferred_titles`/
  `alternative_titles`. It had zero synonym/taxonomy awareness: a
  "Software Engineer" search would not match a posting titled "Developer"
  at all.
- `MasterProfile.basics` (`domain/models.py`) had **no link fields
  whatsoever** -- no LinkedIn, no GitHub, no website, and `ProjectEntry`
  had no `url` field. `agents/resume/file_renderer.py`'s contact line was
  literally `email | phone | location`, nothing else. This was a real,
  confirmed gap, not a perception.

## Decision

### Curated role taxonomy (`domain/role_taxonomy.py`)

A new module, deliberately hand-curated data plus pure-Python phrase
matching -- the same reasoning `domain/skills_taxonomy.py` already
established for ATS keyword extraction (ADR-0034): a "related roles"
feature whose vocabulary depends on a downloaded model artifact is only
deterministic *conditional on* that artifact's version. `ROLE_FAMILIES`
covers ~15 common tech roles (software/backend/frontend/full-stack/mobile
developer, cloud/DevOps/SRE engineer, data engineer/scientist, ML
engineer, QA/security/database engineer, UX), each with its own
interchangeable-spelling `synonyms` (widen an exact match only) and
`related` sub-role family names (a distinct, separate bucket).
`SENIORITY_SYNONYMS` (junior/mid/senior, purely additive) means "junior
software developer" also matches postings titled "entry level" or
"associate," never hiding a posting that omits a seniority word (most
do). `expand_role(query)` is pure and deterministic: no I/O, no model
calls, same input -> same output forever at this code version.

### `job_relevance.py`: exact vs. related tiers, phrase-matched not token-bagged

`relevance_tier(opportunity, preferences)` classifies each opportunity as
`"exact"`, `"related"`, or `"none"`. The first, naive implementation
merged taxonomy synonyms into the existing flat token-bag `role_terms()`
and immediately produced two real false positives caught by this phase's
own tests before shipping:

- "Data Entry Typist" matched a "Software Developer" search as
  **related**, because "data" alone (shared with the unrelated "data
  engineer"/"data scientist" families) is a shared *token*, even though
  neither title shares a real *phrase*.
- "Backend Developer" matched a "Software Developer" search as
  **exact** (not the intended "related"), because the single generic
  word "developer" is shared between the two families' names.

Both share one root cause: single generic words ("data", "developer") are
exactly what makes two *different* role families nameable, so decomposing
a multi-word family name into a token bag destroys the distinction the
taxonomy exists to draw. The fix: `relevance_tier` phrase-matches (word-
boundary, not token-set overlap) taxonomy synonyms against the opportunity
title, and checks the more specific `related` families *before* the
caller's own broader `exact` family -- so a title naming a more specific
adjacent role is never absorbed into the coarser exact match. `role_terms()`
itself is unchanged from Phase 70 (still the caller's literal words only);
taxonomy widening lives entirely in `relevance_tier`.

`matches_search` (the existing discovery-pipeline filter) now returns
`True` for both `"exact"` and `"related"` -- an adjacent-role posting is
still worth discovering, never silently dropped, same "narrows, never
blocks" Phase 70 discipline. `GET /discover/opportunities` (`api/routers/
discover.py`) now returns `ClassifiedOpportunity` (`{opportunity,
relevance_tier}`) instead of a bare `Opportunity` list, computed once per
request against the caller's own `JobPreferences` -- a shared,
deduplicated catalog classified per-caller. The Search Jobs page renders
exact matches, then a separately labeled "Related roles" section.

### Optional LLM fallback, advisory-only (`agents/research/role_expansion.py`)

A new `RoleExpander` protocol (`core/interfaces.py`) and Groq-backed
implementation (`llm/groq_role_expander.py`) suggest related role titles
for a query the curated taxonomy has **no entry for at all** -- e.g. a
role outside this project's core tech-role domain. Consulted only in that
one case (a taxonomy hit never calls the LLM: zero cost, the common case,
fully deterministic). Its suggestions become tokenized `extra_related_terms`
folded into `relevance_tier`'s `"related"` check -- they can never widen
an `"exact"` match, gate, or filter anything, the same advisory-only
contract `SemanticKeywordMatcher` already follows for the ATS gate
(ADR-0034): a bad suggestion costs at most one harmless extra related-role
term, never a wrong decision. `None` (no Groq key) degrades to "no extra
suggestions," never breaks a search. No Anthropic branch, unlike this
project's other three LLM ports -- the value of a paid fallback for an
already-degrades-to-nothing optional feature doesn't clear this project's
free-tier-first bar the way resume-tailoring or truthfulness-verification
does.

### Résumé public links (`domain/models.py`, `file_renderer.py`)

`BasicsSection` gains `linkedin_url`/`github_url`/`website_url`/
`other_links` (all optional, additive -- an existing profile with none
set is unaffected); `ProjectEntry` gains `url`. Always exactly what the
user themselves entered (onboarding wizard, or JSON Resume's own
`basics.url`/`basics.profiles[]`/`projects[].url` fields via the CLI
loader) -- never scraped, never inferred, never sourced from anyone
else's LinkedIn. `file_renderer.py` adds a second contact line under the
name for non-empty links, and renders a project's `url` next to its name.
No DB migration: `MasterProfile` is stored as a single JSON payload
column (`SqliteMasterProfileStore`), so Pydantic's own additive-field
default handles old rows.

## Consequences

- A search for "junior software developer" now also matches "SWE"/"SDE"/
  "entry level"/"associate" postings without the user spelling out every
  variant, and surfaces backend/cloud/DevOps/etc. postings in a clearly
  separate "Related roles" section -- both the literal request and its
  own worked example are satisfied deterministically and for free.
- The taxonomy covers ~15 common tech-role families; a role genuinely
  outside this project's domain (this project is a tech-career agent)
  gets no related-role suggestions unless a Groq key is configured, in
  which case the LLM fallback tries once, best-effort.
- A generated résumé can now carry a real, user-entered links section
  (LinkedIn, GitHub, portfolio, project links) -- closing a real, previously
  unaddressed gap in the résumé schema/renderer.
- "Analyze other people's LinkedIn resumes" was declined, not silently
  dropped: flagged to the owner with the reasoning (ToS + this project's
  own no-scraping-of-individuals rule), and the résumé-quality goal was
  met a different way (public conventions, not scraped personal data).
- `role_terms()`'s Phase 70 contract (bag-of-words over literal user
  input) is completely unchanged; every existing caller/test of it keeps
  working exactly as before.

## Limitations (honest)

- The curated taxonomy is scoped to common tech roles -- this project's
  own domain. A search for a role entirely outside tech (with no Groq key
  configured) gets no related-role suggestions at all, same as before
  this phase (Phase 70's literal-only behavior).
- The LLM fallback is Groq-only; no Anthropic branch (see Decision).
- Résumé links are always the user's own explicit entries -- there is no
  mechanism (and none is planned) to infer, guess, or look up a
  candidate's LinkedIn/GitHub from their name or résumé text.
