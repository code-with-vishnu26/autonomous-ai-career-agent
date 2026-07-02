# ADR-0014: Cross-source opportunity identity (two-key dedup + canonical company)

- **Status:** Accepted
- **Date:** 2026-07-01
- **References:** [ADR-0012](0012-opportunity-provenance-and-confidence.md)
  (payload-evolution pattern), ROADMAP Phase 4c decision checkpoint

## Context

Discovery now has five sources of two kinds: structured sources with an
authoritative native id (Greenhouse / Lever / Ashby `{kind}:{board}:{ref}`, YC
role ids) and a freeform source (Hacker News) whose opportunities are keyed on a
`canonical_fingerprint(company, title, location)`. Phase 4c adds web search,
where a result can be *the same job* an ATS API already returned. So "when are
two opportunities the same?" stops being deferrable -- the checkpoint logged in
the ROADMAP against 4c. Two sub-decisions were deferred *to here* precisely so
they could be decided against a real multi-source case (Greenhouse and HN already
key differently today), not guessed early.

## Problem

How does an opportunity discovered by one source dedup against the same job
discovered by another, **without** over-merging two genuinely-different reqs at
one company that happen to share a title+location -- a guarantee we already test
(`test_two_reqs_sharing_a_title_do_not_over_merge`)?

## Decision

### Two-key identity (not fingerprint-primary)

- **Primary id** stays as-is: the ATS-native id where available (exact
  idempotency, no over-merge), else the fingerprint. This is what keeps two
  distinct same-title reqs *within a source* separate.
- **Match key** is the `canonical_fingerprint`, and the repository dedups on
  **primary id OR a fingerprint match** -- but a fingerprint match only merges
  when the incoming opportunity is **non-authoritative** (has no native source
  id). Concretely, `authoritative = ats_ref is not None`:
  - Two *authoritative* opportunities with the same fingerprint but distinct
    native ids are **kept separate** (the ATS itself says they are different
    reqs). No over-merge.
  - A *non-authoritative* opportunity (HN today; web search / career pages in
    4c) whose fingerprint matches any stored opportunity is a **duplicate**. This
    is the common case -- an ATS job discovered first, then the same job found
    via search.
- **Why not fingerprint-primary:** making `Opportunity.id` the fingerprint for
  everyone would over-merge two distinct reqs sharing title+location, breaking a
  guarantee we deliberately test. Rejected.

### Canonical company (computed in the source, not the repository)

Cross-source fingerprint matching only works if "company" is canonical, not a
per-source token (a Greenhouse board slug, an HN apply-email domain, and a search
result's domain are three different kinds of evidence about one employer).

- **`canonical_company` is a required field on `Opportunity`**, computed by each
  source where the knowledge lives -- the same pattern and rationale as
  `provenance` (ADR-0012). The repository is source-agnostic by construction
  (`add`/`get` over `Opportunity`); it *cannot* canonicalize per-source company
  without learning every source's quirks, which is the leak we have prevented for
  nine phases. Required-ness enforces universality: a source cannot emit an
  opportunity without declaring a canonical company.
- Sources populate it best-effort: HN from the apply email/URL **domain** when
  present, else the normalized company text; ATS/YC from the normalized board
  token / slug (no domain available to them).

### Protocol unchanged (the pin)

`OpportunitySource.fetch`, `HttpClient`, and `OpportunityRepository`'s `add`/`get`
signatures do **not** change. `canonical_company` is `Opportunity`-payload
evolution (`domain/models.py`); the repository's dedup *logic* is enriched
internally. Same pin as ADR-0012.

## Alternatives considered

- **Fingerprint-primary** (id = fingerprint for all sources). Rejected: over-merges
  distinct same-title reqs; breaks an existing guarantee.
- **Id-only, no fingerprint match.** Rejected: no cross-source dedup at all -- the
  entire point of 4c.
- **Canonicalize company in the repository.** Rejected: the repo is
  source-agnostic and would have to learn every source's company quirks (the
  exact coupling the architecture prevents), or fall back to a lossy
  lowest-common-denominator.

## Trade-offs (two bounded, documented gaps -- both biased to the safe direction)

- **ATS-has-no-domain under-merge.** An ATS job (`canonical_company="acme"`) and a
  domain-based hit (`"acme.com"`) for the same employer may not match until a
  board→domain mapping exists. This fails toward *missing a dedup* (a duplicate
  record), never toward wrongly merging distinct jobs. A board→domain mapping is a
  future enhancement, not faked now.
- **Rare cross-source over-merge.** Two truly-different jobs with identical
  canonical company + title + location, at least one non-authoritative, would
  merge. Accepted as rare and safe: a quality-over-volume system prefers
  occasionally collapsing two identical-looking postings to spamming duplicates.
- **Reverse-order under-merge.** If a non-authoritative hit is stored *before* the
  authoritative job (uncommon -- ATS sources run first), the later authoritative
  job is deduped by its own native id only and may be added as a second record.
  Safe direction (a duplicate, not a corruption).

## Consequences

- All five existing sources populate `canonical_company`; the repository's two-key
  dedup is validated on known data before 4c's web-search source arrives.
- The negative guarantee (two authoritative same-fingerprint reqs stay separate)
  is tested at the repository level, not only at `opportunity_id`.
- 4c's `SearchProvider`-derived opportunities will be non-authoritative
  (`ats_ref=None`), so they dedup against known ATS jobs by fingerprint for free.

## Future revisit criteria

Revisit if:

- A reliable board→domain (or company→domain) mapping becomes available, closing
  the ATS under-merge gap.
- Fingerprint collisions (rare over-merge) are observed often enough to warrant a
  stronger match key (e.g. incorporating a normalized description hash).
- A future source needs an authority notion richer than "has a native id".
