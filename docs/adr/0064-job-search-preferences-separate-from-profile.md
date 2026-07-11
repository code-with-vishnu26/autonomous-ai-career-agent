# ADR-0064: Job Search Preferences are a separate model/file from the master profile

- **Status:** Accepted
- **Date:** 2026-07-11
- **References:** [ADR-0006](0006-json-resume-master-profile.md)
  (master profile), [ADR-0038](0038-decide-layer.md) (Decide-layer
  filters), [ADR-0056](0056-v1-prepare-only-release-scope.md) (prepare-only
  scope)

## Context

Phase 46 is the start of a second, larger arc (v2, "an automation layer on
top of the existing prepare-only engine") that begins with letting the user
describe what kind of job they're looking for -- titles, seniority,
location, salary, company allow/deny lists, and a handful of future
behavior toggles -- before `discover` runs. That is a different kind of
data than anything the master profile currently holds.

## Problem

Where does "what job am I looking for" live? Two options were considered:

1. **Extend `MasterProfile`** with a new section (the same document
   `profile.json` already holds `basics`/`work`/`education`/`skills`/
   `legal_status`).
2. **A new, separate model and file** (`JobPreferences` /
   `job_preferences.json`), loaded and saved independently.

## Decision

**Separate.** `JobPreferences` is its own Pydantic model
(`domain/job_preferences.py`), its own storage boundary
(`storage/job_preferences.py`), its own file (`job_preferences.json`,
default path via `Settings.job_preferences_path`, same CWD-relative/
`.env`-overridable pattern as `database_path`/`artifacts_dir`/
`promptfoo_results_dir`), and its own CLI command (`career-agent
preferences`). It is never merged into `profile.json` or `MasterProfile`.

### Why

1. **Different kind of data: facts vs. search configuration.**
   `MasterProfile` (ADR-0006) is the single source of truth for
   *applicant-facing claims* -- the truthfulness gate's whole grounding
   substrate is "every statement resolves to a reference into this
   document." A preferred salary range or a blacklisted company is not a
   fact about the candidate; it is an operator instruction about *how to
   search*, structurally closer to `Settings.decide_blacklist_companies`
   than to `MasterProfile.work[]`. Mixing the two would blur what "factual"
   means in a document a truthfulness gate treats as ground truth.

2. **`MasterProfile.version` is a content hash that must not chase search
   behavior.** Every `EvidenceRef` pins a stable `profile_version`, and
   `save_legal_status`'s own docstring is explicit that a version bump
   never retroactively alters an already-recorded `Application`'s frozen
   snapshot. If preferences lived inside `MasterProfile`, editing "how
   many applications per day" or a company blacklist -- something a user
   might reasonably tweak every session -- would bump `profile_version` on
   every edit, for a change that has *nothing to do with what's true about
   the candidate*. That would either (a) genuinely change `profile_version`
   for no evidentiary reason, cluttering the version history real fact
   edits are supposed to be traceable through, or (b) tempt a future
   change to special-case preference fields out of the content hash,
   quietly reintroducing the exact "what does and doesn't affect the hash"
   confusion `MasterProfile`'s docstring already had to resolve once for
   `legal_status`. A separate file sidesteps this entirely: preferences
   change on their own timeline, with no interaction with fact versioning.

3. **Different lifecycle and cardinality.** The master profile is edited
   rarely and carefully (every edit is a claim someone might submit as
   true). Job preferences are expected to be edited often and casually --
   "actually, let's also look at hybrid roles this week" -- with no
   truthfulness implications at all. A separate file makes that difference
   visible instead of implicit.

4. **No schema convention to fight.** `MasterProfile` follows JSON Resume,
   which is why `storage/profile.py` needs a camelCase-to-snake_case
   mapping layer and the Phase 36/39 "loader vs. raw `model_validate`"
   confusion it documents at length. `JobPreferences` is this project's own
   design with no external schema to honor, so its on-disk shape *is* its
   Python field names directly -- `model_validate`/`model_dump_json`, no
   mapping layer, and therefore no way to repeat that exact confusion for
   a second file.

### What is (and is not) wired this phase

Only `preferred_titles`/`alternative_titles`/`work_mode`/`countries`/
`keywords_exclude` are consumed anywhere at runtime, by
`domain.job_preferences.generate_search_queries` -- a pure, deterministic
function turning preferences into search-query strings ("Backend Developer
Remote", "Backend Developer India", ...). `cli.build_discovery_sources`
fans each keyword-capable source (Adzuna/Reed/USAJobs/Jooble) out across
those generated queries instead of the single static
`settings.discovery_keywords` default, when preferences exist and generate
at least one query; with no preferences (or preferences with no titles
configured), behavior is byte-for-byte identical to before this phase --
proven by `tests/test_discover_preferences_integration.py`, not just
asserted.

Every other field (salary, visa sponsorship, preferred/blacklisted
companies, industries, max applications/day, the auto-tailor/auto-cover-
letter/require-confirmation toggles, preferred ATS providers, time zone) is
captured and persisted now, but **not yet enforced anywhere** -- named,
deferred integration points, documented on the model itself
(`JobPreferences`'s own docstring), not silently claimed as done. In
particular:

- `require_human_confirmation` is informational only. The real
  confirmation boundary (`confirm_submission`, the execution-safety
  boundary, ADR-0018/ADR-0050) is hardcoded and does not read this field.
  **It cannot be used to bypass the mandatory confirmation step.**
- `blacklisted_companies`/`preferred_companies` are a separate concept
  from the Decide layer's existing `Settings.decide_blacklist_companies`/
  `decide_allowed_locations` filters (ADR-0038), which remain the
  authoritative discovery/ranking filter for now. Reconciling the two is a
  named future decision, not an oversight.
- `auto_generate_cover_letter` names a capability that does not exist
  anywhere in this codebase yet.

This is deliberately a foundation phase, per the brief: it does not add
browser automation, does not change the prepare-only execution boundary,
and does not perform any real external submission.

## Consequences

- New `domain/job_preferences.py` (`JobPreferences` model +
  `generate_search_queries`), `storage/job_preferences.py` (scaffold/load/
  save), `Settings.job_preferences_path`.
- New `career-agent preferences` CLI command (interactive wizard, injected
  `input_fn`, no globals, matching `run_capture_legal_status_command`'s
  established shape).
- `build_discovery_sources` gains an optional `preferences` parameter;
  `discover` and `auto` both load `job_preferences.json` if present.
- `.gitignore` gains `/job_preferences.json` (same "stays local" treatment
  as the master profile). Incidentally found and fixed in the same change:
  `profile.json` -- the actual default master-profile filename every
  command and the README use -- was never gitignored at all; only the
  unused `master_profile.json` pattern was. Both are now correctly
  ignored.
- No change to the truthfulness gate, the execution-safety boundary, or
  any LLM-facing code. No dependency added.

## Future revisit criteria

Revisit when a future phase wires salary/visa/company-list enforcement
into Decide, implements cover-letter generation, or enforces
`max_applications_per_day` -- each should update this ADR's "not yet
enforced" list rather than silently start claiming the field does
something it didn't before.
