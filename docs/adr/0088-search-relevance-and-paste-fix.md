# ADR-0088: Search Relevance Filter + Paste-a-Job Fix

- **Status:** Accepted
- **Date:** 2026-07-13
- **References:** [ADR-0081](0081-web-triggered-discover-review-submit.md)
  (the web Search Jobs discovery this fixes), [ADR-0086](0086-assisted-apply-pasted-jobs.md)
  (the paste-a-job flow whose "Opportunity not found" regression is fixed
  here)

## Context

Two real bugs surfaced by an owner running the dashboard end to end:

1. **Irrelevant search results.** A search for "software engineer" in
   India returned baristas, nannies, and data-entry roles from all over
   the world. Root cause: the free firehose sources
   (RemoteOK/Remotive/Arbeitnow/TheMuse) return *every* recent remote
   posting regardless of the query -- only the keyed sources
   (Adzuna/Reed/USAJobs/Jooble, none configured for this user) filter by
   keyword server-side. Discovery stored every posting a source returned,
   with no client-side relevance gate, so the sources that ignore the
   query drowned out any that honor it.
2. **"Opportunity not found" on paste.** The paste-a-job flow
   (`POST /prepare/pasted`) built an ad-hoc `Opportunity`, `add`-ed it to
   the repository, then re-fetched it by id in the background task. The
   repository's dedup-by-fingerprint (`add` returns `False` and does not
   insert on a fingerprint collision) meant a pasted posting could never
   be re-fetchable by id, so the background task failed with "Opportunity
   ... not found."

## Decision

**Role-relevance filter (new `domain/job_relevance.py`).** A pure,
deterministic keyword matcher over the user's configured role titles
(`preferred_titles` + `alternative_titles`): an opportunity matches if its
title shares any discriminating token with the role terms (stopwords and
sub-3-char tokens dropped), and its company is not blacklisted. It is
deliberately literal -- it matches the user's own words, not a synonym
model -- so results are predictable ("software engineer" keys on
{software, engineer}; add "developer" as an alternative title to widen).
**Empty role config matches everything**, so a user who never set a role
sees discovery's prior behavior unchanged.

`run_discover_command` gains an optional `relevance_filter` predicate
(default `None` = no filtering, so the CLI and existing tests are
unchanged); the web discover router builds it from the caller's
`JobPreferences` and passes it, so off-role postings are dropped before
they ever reach storage.

**Paste fix.** `_run_prepare` now accepts the `Opportunity` object
directly, not just its id. The pasted endpoint hands the object through
in memory (still `add`-ing it best-effort for the Review Queue/Excel), so
tailoring no longer depends on re-fetching a posting that dedup may have
declined to insert. The frontend `PasteJobCard` also stops clearing the
form on submit, so a user does not lose their pasted text while it tailors
(and can re-run on failure).

## Consequences

- A "software engineer" search now returns software-engineering roles;
  unrelated postings from the keyword-agnostic sources are filtered out.
  For precise country-specific results (e.g. India), the keyed Adzuna
  source (country=IN) remains the right tool -- it needs an API key, and
  fuzzy client-side country-string matching was deliberately *not* added
  (it would risk the very inaccuracy this fixes, e.g. wrongly excluding an
  India-eligible remote role).
- Paste-a-job works regardless of repository dedup outcome.
- The relevance filter is opt-in per call; nothing about the CLI's
  discovery or any existing test changes. The dedup and truthfulness
  gates are untouched.
