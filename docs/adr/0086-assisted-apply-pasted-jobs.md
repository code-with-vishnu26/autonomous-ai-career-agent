# ADR-0086: Assisted Apply for Pasted Jobs (LinkedIn/Indeed/Naukri)

- **Status:** Accepted
- **Date:** 2026-07-13
- **References:** [ADR-0036](0036-tier-c-manual-only-sources.md) (standing
  invariant 7: LinkedIn/Indeed/Naukri/Foundit/Seek are manual-only, no
  scraper ever), [ADR-0085](0085-web-triggered-prepare.md) (the
  web-triggered tailoring this reuses unchanged), [ADR-0071](0071-human-approved-submission-engine.md)
  (the submission engine that already refuses an unknown-ATS URL)

## Context

The owner asked the agent to help apply to jobs on LinkedIn, Indeed, and
Naukri. This project has a standing, deliberate rule (ADR-0036, invariant
7): it never scrapes or auto-applies on those platforms -- their Terms of
Service prohibit it and they ban accounts that do. That rule is not
reopened here. But a user who finds a job on LinkedIn still deserves the
agent's real value -- a tailored résumé + cover letter for that specific
posting.

**A repository-reality audit found:**

- Phase 67's `prepare_application_for_review` (ADR-0085) already tailors a
  résumé + cover letter for any `Opportunity` from the stored Master
  Profile, running the truthfulness + ATS gates -- with no browser. It
  only needs an `Opportunity` object; it does not care whether that
  opportunity was auto-discovered or hand-entered.
- A LinkedIn/Indeed/Naukri posting URL resolves to **no known ATS**
  (`resolve_ats_kind` returns `None`), so the submission engine already
  refuses to auto-submit it (`UNSUPPORTED_PROVIDER`, ADR-0071). The
  "never auto-apply on these platforms" guarantee is therefore already
  enforced by existing code -- nothing new is needed to uphold it.

## Decision

Add an **assisted-apply** path: paste a posting, get tailored materials,
apply on the platform yourself.

- `POST /prepare/pasted` (new, in the Phase 67 `prepare_actions` router):
  takes `{ title, company, description, url? }`, builds an ad-hoc
  `Opportunity` (`source="job_board"`, `provenance.method="text_extraction"`,
  `extraction_confidence=1.0` -- a human curated it, not a heuristic
  scrape), **persists it** to the opportunity repository (so the résumé
  variant and Review Queue reference it like any other), then delegates to
  the *exact same* `_run_prepare` the discovered-job path uses. One
  tailoring path, two ways in.
- No auto-submit, by construction: the pasted URL resolves to no ATS, so
  the existing submission engine refuses it. The user downloads/copies the
  tailored materials and applies on LinkedIn/Indeed/Naukri themselves --
  the assisted-apply model, not automation of a site that forbids it.
- Frontend: a `PasteJobCard` on the Search Jobs page (title, company,
  description, optional URL) that triggers `POST /prepare/pasted`, polls
  the same way discovered-job prepare does, and links to the Review Queue.

## Consequences

- A user can now get a tailored résumé + cover letter for a LinkedIn,
  Indeed, or Naukri posting -- the platforms the owner explicitly named --
  entirely from the dashboard, without the project ever scraping or
  auto-submitting on them. Standing invariant 7 (ADR-0036) is upheld, not
  reopened.
- Assisted-apply and discovered-job prepare share one code path
  (`_run_prepare` / `prepare_application_for_review`); the pasted endpoint
  is only an alternate constructor for the `Opportunity`.
- The pasted opportunity is real data in the repository, so it flows into
  Review, the Excel export, and analytics like any other -- the user's
  LinkedIn applications are tracked alongside the auto-discovered ones.
- The "no auto-submit on these platforms" guarantee rests on
  `resolve_ats_kind` returning `None` for their URLs; if a real,
  permitted ATS integration for one of them ever existed, that decision
  would be revisited under ADR-0036, not silently changed here.
