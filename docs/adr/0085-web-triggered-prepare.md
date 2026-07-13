# ADR-0085: Web-Triggered Prepare (Guided Apply Flow)

- **Status:** Accepted
- **Date:** 2026-07-13
- **References:** [ADR-0069](0069-application-preparation-engine.md) (the
  `prepare` pipeline this exposes over the web), [ADR-0081](0081-web-triggered-discover-review-submit.md)
  (the web-triggered Discover/Review/Submit this completes the loop of, and
  whose background-task/poll pattern this mirrors), [ADR-0082](0082-per-user-master-profile-onboarding.md)
  (the stored Master Profile this tailors from), [ADR-0071](0071-human-approved-submission-engine.md)
  (the human-confirmation gate that still owns the real form fill + submit)

## Context

After ADR-0081, the dashboard could Discover, Review, and Submit from the
web, but **Prepare** (tailoring a résumé + cover letter for a specific
job) stayed CLI-only. The owner's direction was explicit: the whole loop
must run from the website -- "first the AI asks the details, searches
jobs, creates a CV/résumé/cover letter using the job description, fills
the form, and at last asks the user to review." Prepare was the missing
middle.

**A repository-reality audit found:**

- `run_prepare_command` (CLI) has two distinct halves: (1) tailoring --
  `ResumeVariantEngine.build_materials` runs the truthfulness gate, the
  ATS threshold, and cover-letter assembly, **no browser**; (2)
  `ApplicationPreparationEngine.build_session` opens a headed browser to
  *pre-fill* the live form for preview. The authoritative form fill and
  résumé upload happen later, at submit (`submit_prepared_application`,
  ADR-0071/0081), which re-tailors fresh and drives the browser itself.
  The submit path uses an `ApplicationSession` only for its metadata
  (company, opportunity_id, resume_variant_id) -- not its browser-detected
  fields.
- The existing web Submit flow (`submission_actions.py`, ADR-0081) still
  loads the candidate profile from `Path("profile.json")`, **not** the
  per-user Master Profile the onboarding wizard (Phase 64) writes to the
  database. So an onboarded dashboard user's stored profile did not
  actually drive tailoring.
- `submission_actions.py` already established the pattern for triggering a
  long CLI operation from the web: a `BackgroundTasks` job + an in-memory
  pending-entry dict + a poll endpoint.

## Decision

Add **web-triggered Prepare** that tailors from the stored Master Profile
and feeds the existing Review -> Submit loop, without a browser.

- `cli.py::prepare_application_for_review` (new): the web analogue of
  `run_prepare_command`, taking loaded objects (`Opportunity`,
  `MasterProfile`, `Settings`). Runs the *exact same*
  `build_materials` -- gate, ATS threshold, cover letter all unchanged --
  then constructs a `READY_FOR_REVIEW` `ApplicationSession` directly from
  the tailored materials. It deliberately does **not** open a browser: the
  pre-fill was only a preview, and skipping it keeps preparation
  deterministic and runnable anywhere (including a headless server). Raises
  the same errors the CLI surfaces, plus a new `TruthfulnessRejectedError`
  carrying the gate's rejection reasons.
- `api/routers/prepare_actions.py` (new): `POST /prepare` (background task
  + token) and `GET /prepare/{token}` (poll), mirroring
  `submission_actions`. The background task loads the caller's **stored
  Master Profile** (Phase 64) -- the bridge that makes "the AI builds your
  résumé from the details you entered" real -- 404-failing with an
  onboarding prompt if none exists, then tailors and saves the
  `ApplicationSession` under the caller's `user_id`. Fire-and-poll with no
  confirm step of its own: tailoring sends nothing outward, so the only
  human gate that matters (submit) is unchanged and still un-bypassable.
- Registered as a write-capable router (it triggers a real, costed LLM
  tailoring), off the `/api/` prefix, joining the ADR-0081 exceptions to
  the `/api/*`-GET-only structural proof.
- Frontend: `prepareApi` + `usePrepare` (poll every 2s while `PREPARING`,
  the same shape as discovery-run polling) and a `PrepareButton` on each
  Search Jobs result -- click tailors, then routes to the Review Queue.
  The old "Prepare via CLI" `CliOnlyAction` placeholder is removed; the
  Search Jobs help text is updated to describe the real web flow.

## Consequences

- The complete apply loop -- search -> **prepare** -> review -> submit --
  now runs from the browser, driven by the onboarded profile. The owner's
  "a normal user never opens a terminal" bar is met for the core journey.
- The authoritative form fill and résumé upload remain at submit, behind
  the human-confirmation gate (ADR-0071) -- exactly the owner's "AI fills
  the form, then asks the user to review" ordering. Nothing is ever sent
  without an explicit human confirm.
- Web prepare is browserless and so works in any environment; the CLI's
  browser-based `build_session` pre-fill is untouched for CLI operators.
- Web prepare uses the DB Master Profile; the web **submit** flow
  (`submission_actions.py`) still reads `profile.json`. Bridging submit to
  the DB profile too is named follow-up work, not done here -- but a
  session prepared from the DB profile already carries the tailored
  résumé variant submit needs.
- `prepare_application_for_review` requires an LLM provider + a validated
  promptfoo run (like every real tailoring path); with none configured it
  fails the poll with a clear message rather than a degraded result.
