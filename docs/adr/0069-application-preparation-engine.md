# ADR-0069: Application Preparation Engine — reuses the existing Tier-2 apply machinery, minus the click

- **Status:** Accepted
- **Date:** 2026-07-11
- **References:** [ADR-0020](0020-browser-tier-session-and-pause.md) (Tier 2
  `BrowserApplicator`, session persistence), [ADR-0028](0028-browser-tier-dispatch-and-unsupported-field-refusal.md)
  (`FormFiller` per-`ats_kind`), [ADR-0029](0029-per-filler-challenge-and-submit-selectors.md)
  (per-platform challenge/submit selectors), [ADR-0031](0031-question-answerer.md)
  (`question_answerer`'s four-category classification), [ADR-0032](0032-question-answerer-wiring.md)
  (Phase A triage/manifest/hard-refuse), [ADR-0035](0035-real-lever-form-filler.md)
  (real Lever file upload), [ADR-0065](0065-browser-automation-foundation.md)
  (`BrowserManager`/`SessionManager`/`TabManager`), [ADR-0066](0066-website-adapter-framework.md)
  (`AdapterCapabilities`, `prepare_application()` reserved for a future
  phase), [ADR-0054](0054-production-readiness-release-gate.md) (the
  release-invariant contract this phase had to respect)

## Context

Phase 51 asks for an "Application Preparation Engine": open a browser,
navigate to the job page, detect/wait for login, detect the form, map
fields, fill text fields, upload résumé/cover letter, answer known
questions, and **stop before Submit**.

The repository-reality audit found this is almost entirely **not**
greenfield. `agents/apply/browser_applicator.py` (`BrowserApplicator`,
ADR-0020/0028/0032, unwired from the CLI) already implements the exact
sequence the brief describes — open page, fill identity/résumé fields via
a per-platform `FormFiller`, detect every other required field, classify
it (EEOC / factual / subjective / dropdown) via `question_answerer.py`
(ADR-0031), auto-answer what a captured `LegalStatusSection` fact
supports, and manifest the rest for a human — and then, only after all of
that, clicks submit and checks for a challenge. **The entire brief, minus
the click, already exists and is real, tested, evidence-grounded code**:
Greenhouse's identity/résumé fields are real; Lever's real, required
file-upload résumé attachment is real (ADR-0035, verified against a real
live posting's DOM shape); Ashby is an honest, registered stub
(`FormFillerNotImplementedError`) because its selectors were never
verified. `integrations/browser/` (Phase 47) already provides
`BrowserManager`/`SessionManager`/`TabManager`; `integrations/adapters/`
(Phase 48) already provides provider detection and per-platform
capability flags (including `supports_cover_letter_upload`, honestly
`False` — unverified — for every provider today).

## Decision

**Extract the click out, don't rebuild the rest.** A new package,
`agents/application/`, composes the *existing* machinery unmodified and
adds exactly one new thing: stopping before the submit click.

### Extraction: `agents/apply/field_inspection.py`

`BrowserApplicator`'s required-field detection/classification/triage
logic (`_required_unknown_elements`, `_field_question_text`,
`_try_fill_boolean_select`, `_triage_unhandled_fields`,
`_unhandled_required_fields`, `_fields_still_empty`) never depended on
anything `BrowserApplicator`-specific — only a live `Page` and a
`FormFiller`'s declared `known_field_selectors`. Extracted verbatim (no
behavior change) into a new shared module so a second caller
(`ApplicationPreparationEngine`) can reuse the exact same, already-proven
detection/classification/auto-answer logic instead of re-implementing it
— the identical "extract and share, don't duplicate" move Phase 47 made
for `BrowserManager`/`SessionManager` out of this same file.
`browser_applicator.py` now imports from `field_inspection.py`; its own
32 existing tests were run unchanged before and after the extraction and
all still pass, proving it byte-for-byte behavior-preserving.

### `ApplicationPreparationEngine`: everything up to, never including, the click

`agents/application/engine.py::ApplicationPreparationEngine.build_session()`
composes `BrowserManager`+`TabManager`+`SessionManager` (Phase 47),
`resolve_ats_kind`+`default_form_fillers()` (existing, unmodified), and
`field_inspection.triage_unhandled_fields` (extracted above) into exactly
`BrowserApplicator.submit()`'s own Phase-A sequence — fill known
fields, triage everything else — and then simply **returns**, instead of
proceeding to `page.click(filler.submit_selector)`.

This is a structural guarantee, not a documented intention:
`agents/application/engine.py` never reads a `FormFiller`'s
`submit_selector`/`challenge_selector` at all, and never calls a `Page`'s
click method anywhere — proven by an AST-based source-scan test
(`tests/agents/test_application_engine.py::test_engine_source_never_calls_click`),
the same discipline `SessionManager`'s login-safety test already
established for "never types a credential."

### `ApplicationSession`: the result, in `domain/`

`domain/application_session.py::ApplicationSession` is pure data (no
`Page`, fully serializable) with a `status` in
`{READY_FOR_REVIEW, BLOCKED, LOGIN_REQUIRED_TIMEOUT, UNSUPPORTED_PROVIDER}`
— **no value resembling a submission confirmation exists on this type at
all**, a structural fact proven by a test asserting no field named
`submitted`/`submission_id`/`confirmation` exists on the model, not merely
documented. Lives in `domain/` (not `agents/application/session.py` as
the brief's file list suggested) to match the precedent Phase 50 already
set for `ResumeVariant`/`TailoredCoverLetter`: a pure result type produced
by an I/O-driven agent still belongs in `domain/`, automatically covered
by the existing AST-based domain-purity test suite.

### No new `field_detector.py`/`answer_engine.py`/`field_mapper.py`/`upload_manager.py`

The brief's file list names four more modules. **Deliberately not
created**, each for a reason grounded in the audit:

- **`field_detector.py`** would duplicate `field_inspection.py` (above) —
  the exact capability already exists, just needed extracting, not
  rebuilding.
- **`answer_engine.py`** would duplicate `agents/apply/question_answerer.py`
  (ADR-0031) — a fully-built, independently-tested four-category
  classifier (EEOC absolute / factual / subjective / dropdown) already
  used unchanged via `field_inspection.triage_unhandled_fields`.
- **`field_mapper.py`**: the brief's example mappings (First Name, Email,
  Phone, Location, Website, LinkedIn, GitHub) mostly have **no
  `MasterProfile` field to map from at all** — `BasicsSection` carries
  only `name`/`email`/`phone`/`summary`/`location`; there is no `website`,
  `linkedin`, or `github` field anywhere in this codebase's profile model.
  Building a mapper for fields that don't exist would mean either
  fabricating data or mapping to nothing — so name/email (via
  `FormFiller.fill_identity_and_resume`, unchanged) are the only fields
  honestly auto-fillable today; everything else correctly falls through
  `question_answerer.classify_question` to `SUBJECTIVE` and lands in
  `missing_fields` for a human, which is the safe, honest outcome, not a
  gap this phase silently left unhandled.
- **`upload_manager.py`**: Lever's résumé upload is already real, inside
  `LeverFormFiller.fill_identity_and_resume` (ADR-0035) — `build_session`
  independently re-derives `uploaded_files` from the application's own
  DOCX artifact afterward, as evidence of what was actually attached,
  never a blind claim. Cover-letter upload is attempted **nowhere**: no
  platform has a verified cover-letter form field (`AdapterCapabilities.
  supports_cover_letter_upload` is `False`/unverified for every provider,
  Phase 48) — attempting one would mean guessing at an unverified
  selector, the exact discipline `LeverFormFiller`'s own docstring already
  refused for Ashby. A cover letter is carried on `ApplicationSession.
  cover_letter_body` for manual attachment during review instead, with an
  explicit warning recorded.

### Login: caller-supplied selector, or an honest gap

`SessionManager.wait_for_login` requires an `indicator_selector` this
project has **no verified value for on any platform** (Phase 47's own
documented gap). `build_session` accepts one as an optional parameter;
when absent, login state is never checked at all, and a
`login_detection_skipped` warning is recorded — never silently assumed
logged-in or logged-out.

### Storage and CLI wiring

`storage/sqlite.py` gains `SqliteApplicationSessionStore` (append-only,
the same `_connect`/`_XXX_SCHEMA` one-file convention every other store in
this project already uses). `career-agent prepare --profile ...
--opportunity-file ...` is the first CLI command in this codebase to
construct real Phase 47 browser infrastructure: it runs Phase 50's
`ResumeVariantEngine.build_materials()` (unmodified) for tailoring/gating/
cover-letter, then `ApplicationPreparationEngine.build_session()` for the
browser step, persisting both a `ResumeVariant` and an `ApplicationSession`
on success.

### A naming collision, found and fixed: `ResumeVariantEngine.prepare` → `build_materials`

`tests/test_phase28_release_invariants.py::test_no_external_submission_is_reachable_from_the_cli`
(ADR-0054) asserts `cli.py`'s source contains no literal `.prepare(` call
at all — the existing guard against ever reaching an `Applicator`'s
tier-submission `prepare()`/`submit()` lifecycle. Phase 50's
`ResumeVariantEngine.prepare()` (never wired into `cli.py` until this
phase) would have collided with that literal string check the moment it
was actually called from the composition root — an unrelated method
sharing a forbidden word. Renamed to `build_materials()` (Phase 50's test
suite updated in lockstep, zero behavior change) rather than weakening the
release-invariant test, which stays exactly as strict as it always was.

## What this phase explicitly does not do

No submit click, anywhere, ever — proven structurally, not just
documented. No CAPTCHA/MFA solving. No password storage (`SessionManager`
never touches a credential field, unchanged from Phase 47). No assessment
or video-interview automation. No AI-based field detection — every
decision here is the same deterministic pattern/selector logic
`BrowserApplicator`/`question_answerer` already used. No change to
`BrowserApplicator`, `TieredApplicator`, `ResumeTailoringPipeline`,
`LLMResumeGenerator`, `LLMTruthfulnessGate`, or the execution-safety
boundary (`executor_available=False` remains hardcoded and untouched).

## Consequences

- One extracted module (`agents/apply/field_inspection.py`), one trimmed
  existing module (`browser_applicator.py`, behavior-preserving —
  confirmed by its unchanged 32-test suite).
- One new pure `domain/` module (`application_session.py`).
- One new package (`agents/application/`: `__init__.py`, `engine.py`).
- One new class in `storage/sqlite.py` (`SqliteApplicationSessionStore`).
- One renamed method (`ResumeVariantEngine.prepare` →
  `.build_materials`), fixing a real, found collision with an existing
  release-invariant test.
- One new `career-agent prepare` CLI command, one new `Settings` field
  (`browser_session_dir`).
- 19 new tests: 10 real-Chromium engine tests (Greenhouse happy path,
  Lever real upload, Ashby honest-stub propagation, unsupported-provider
  fail-fast, an undescribable-required-field BLOCKED case, two structural
  no-click source-scan tests), 3 pure `ApplicationSession` model tests, 6
  `SqliteApplicationSessionStore` tests. 911 total (up from 892).
- No new dependency, no version bump, no change to the truthfulness gate,
  the ATS gate, or any existing safety semantics.

## Future revisit criteria

Revisit when Phase 52 (Human Review Center) needs to *render*
`ApplicationSession` for a human — the point at which screenshots or a
richer preview format might be added to this type. Revisit `field_mapper`
once `MasterProfile` genuinely gains `website`/`linkedin`/`github` fields
(a profile-model change, not something this phase should invent
speculatively). Revisit cover-letter upload once any platform's real,
live-verified cover-letter field selector is confirmed — the same
verify-before-build discipline that gated Lever's résumé upload
(ADR-0035) and should gate this too.
