# ADR-0082: Per-User Master Profile + Web Onboarding Wizard

- **Status:** Accepted
- **Date:** 2026-07-13
- **References:** [ADR-0017](0017-master-profile-loader.md)
  (named the exact trigger this phase executes: "If a second profile
  source appears ... that is the moment to extract `load_master_profile`
  behind a `Protocol`, not before"), [ADR-0078](0078-saas-multi-tenant-platform.md)
  and [ADR-0081](0081-web-triggered-discover-review-submit.md) (both
  independently name the same future-revisit trigger: *"If this project
  ever moves beyond a single-operator MasterProfile ... `Path("profile.json")`
  needs a real per-user store, mirroring `SqliteUserPreferencesStore`"*),
  [ADR-0074](0074-authentication-and-multi-user-platform.md) (the
  `SqliteUserPreferencesStore` structural precedent this phase mirrors
  exactly), [ADR-0081](0081-web-triggered-discover-review-submit.md)
  (write-capable-router precedent this phase follows)

## Context

Every dashboard user's `MasterProfile` -- name, work history, education,
skills, projects, legal/work-authorization status -- has only ever existed
as `profile.json` on disk, built by the CLI's `setup`/`import-cv`/
`promote-cv` commands. The dashboard has grown real accounts, real
per-user data isolation (Phase 56), and real organizations (Phase 60), but
"who is this candidate" itself was never migrated -- a dashboard user has
had no way to tell the system who they are without opening a terminal.

Three ADRs independently named this exact moment as the correct time to
revisit the single-operator assumption; this phase executes that trigger,
not reopens it.

**A repository-reality audit (mandatory before implementation) found:**

- `storage/profile.py`'s `load_master_profile` already separates its pure
  logic (`_validate_ids`, `_map_basics`/`_map_work`/etc., `_content_hash`)
  from its file I/O -- the pure functions were directly reusable by a
  second, DB-backed source with no duplication, once made independently
  callable. ADR-0017 suggested a `Protocol` as the resolution; this phase
  does not build one -- there is still exactly one call site per
  implementation (the CLI always uses the file loader, the API always
  uses the DB store), so no caller needs to be implementation-agnostic.
  A `Protocol` would add indirection with no current beneficiary.
- `SqliteUserPreferencesStore` (Phase 46/56) is the exact structural
  precedent: `user_id TEXT PRIMARY KEY, payload TEXT, updated_at TEXT`,
  upsert via `INSERT ... ON CONFLICT DO UPDATE`, `get()` returns `None`
  when absent. `SqliteMasterProfileStore` mirrors it field-for-field.
- `api/routers/user.py`'s `PUT /user/profile` already exists but is
  explicitly scoped to the *account* profile (display name only) -- its
  own docstring warns against conflating it with `MasterProfile` ("what a
  dashboard user can edit about their account" vs. "what is true about
  the candidate"). This phase adds a separate router
  (`master_profile.py`) rather than overloading that endpoint.
- No file-upload/multipart infrastructure exists anywhere in `api/`
  (confirmed by grep: zero hits for `UploadFile`/`multipart`/
  `python-multipart`). CV upload, and the `domain/ingestion.py`
  `FactProposal`/`promote()`/evidence-span review flow it implies, is
  real, separate infrastructure work and is explicitly deferred to a
  later phase -- not silently dropped, not crammed into this one.
- The onboarding wizard's step list in the originating request includes
  several sections `MasterProfile` has no field for at all
  (certifications, LinkedIn/GitHub/portfolio links) and two that already
  have working, separate pages: Job Preferences (`PUT /user/preferences`,
  Phase 46/56) and Notification Preferences (`NotificationSettingsPage`,
  Phase 58). The wizard covers exactly what `MasterProfile` models
  (basics/work/education/skills/projects/legal status) and links out to
  those existing pages from its final step, rather than duplicating them.

## Decision

Add a **per-user Master Profile store and API**, and a **web onboarding
wizard**, while leaving the CLI's file-based profile completely
untouched.

**Backend:**

- `storage/profile.py`: renamed `_content_hash` to public
  `compute_profile_version` (Phase 64/ADR-0082 is now a second caller),
  and added `validate_master_profile_ids(profile: MasterProfile)` which
  calls the existing `_validate_ids` on `profile.model_dump(mode="json")`
  -- the raw-JSON-Resume-file shape and the Pydantic dump share the same
  `"id"` key, so the identical loop validates both with no duplication.
  `load_master_profile`, `write_profile_scaffold`, `save_legal_status`,
  and every CLI `--profile` flag are unchanged.
- `storage/sqlite.py`: new `SqliteMasterProfileStore` with a
  `master_profiles` table (`user_id TEXT PRIMARY KEY, payload TEXT NOT
  NULL, updated_at TEXT NOT NULL`). `save()` validates ids, recomputes
  `version` server-side (never trusts a client-supplied version), and
  upserts. `get()` returns `None` for an unknown user rather than a
  fabricated empty profile.
- `api/routers/master_profile.py` (new, separate from `user.py` per the
  audit finding above): `GET /user/master-profile` (returns `None` before
  onboarding) and `PUT /user/master-profile` (whole-profile replace; the
  request body model omits `version` entirely so a stale or fabricated
  client value can never masquerade as real).
- Registered as a write-capable router in `api/app.py`, same pattern as
  every router added since ADR-0081.

**Frontend:**

- `services/masterProfileApi.ts` + `hooks/useMasterProfile.ts`
  (`useMasterProfile`/`useUpdateMasterProfile`, TanStack Query, matching
  every other API hook in this codebase).
- `pages/OnboardingWizardPage.tsx`: an 8-step wizard (Welcome / Personal /
  Work / Education / Skills / Projects / Legal / Review) using
  `react-hook-form` + `useFieldArray` for the repeatable work/education/
  skills/projects sections. Pre-fills from an existing stored profile if
  one exists (idempotent re-entry, not onboarding-only). The final step
  links to `/search` (Job Preferences) and `/notification-settings`
  rather than re-implementing either.
- Routed at `/onboarding`, added to `ACCOUNT_NAV_ITEMS` as "Master
  Profile".

**Explicitly out of scope for this phase** (named, not silently
dropped): CV upload and the `import-cv`/`promote-cv` migration, which
needs new multipart-upload infrastructure and a `FactProposal` review UI
built on `domain/ingestion.py` -- deferred to a dedicated phase.

## Consequences

- A dashboard user can now build and edit their candidate profile
  entirely in the browser, with no terminal required, satisfying the
  identical need `SqliteUserPreferencesStore` already satisfies for job
  preferences.
- The CLI's single-operator `profile.json` workflow is unaffected --
  `career-agent setup`/`import-cv`/`promote-cv`/`discover`/`prepare` all
  behave exactly as before. The two profile sources are independent by
  design: a CLI operator's `profile.json` and a dashboard user's stored
  `MasterProfile` are not synchronized or merged.
- `ADR-0017`'s named trigger is now resolved without introducing a
  `Protocol` -- if a third profile source or a call site needing runtime
  polymorphism ever appears, that would be the moment to add one.
- CV-upload-based onboarding remains CLI-only until a dedicated phase
  builds the multipart infrastructure and ingestion-review UI.
