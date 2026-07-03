# ADR-0027: Applicant identity snapshot on Application, real data into BrowserApplicator

- **Status:** Accepted
- **Date:** 2026-07-03
- **References:** [ADR-0020](0020-browser-tier-session-and-pause.md) (`BrowserApplicator`,
  Greenhouse's-form-only scoping, whose `_fill_form` this ADR fixes),
  [ADR-0023](0023-resume-tailoring-pipeline.md) (`ResumeTailoringPipeline`,
  where `Application` is built and `MasterProfile` is already in scope),
  [ADR-0025](0025-resume-renderer.md) (`TailoredResume.profile_version`,
  the existing "frozen snapshot, not a live pointer" pattern this ADR
  extends to identity), [ADR-0026](0026-real-apply-command-and-promptfoo-enforcement.md)
  (the real `apply` command whose investigation into a real `ATSAdapter`
  surfaced this gap)

## Context

Investigating a real `ATSAdapter` for Greenhouse (the natural next step
after ADR-0026 made `career-agent apply` runnable) surfaced that Tier 1
direct-API submission is not a real capability for this project's use case
at all: Greenhouse's, Lever's, and Ashby's submit-side endpoints each
require an employer-issued API credential (Greenhouse: HTTP Basic Auth with
the board's own Job Board API key; Lever: a key "a Super Admin of your
account can generate"; Ashby: a permissioned API key sent on every
request) that a generic applicant tool has no path to obtaining. Verified
against each platform's own current documentation, not assumed from one
data point. This makes `BrowserApplicator` (Tier 2) — which drives the same
public apply form a human uses, requiring no company cooperation — the only
tier that can actually carry real submission weight for arbitrary
companies.

Checking `BrowserApplicator` before proposing how to generalize it past
Greenhouse's one form surfaced a second, more basic gap: `_fill_form`
filled the form's identity fields with hardcoded placeholder strings
(`"Applicant"`, `"Name"`, `"applicant@example.com"`), never the real
applicant's data. This passed full-intensity review in the slice that
built it (7b3/ADR-0020) because that slice was correctly focused on
proving the pause/resume/session-encryption machinery against a test
fixture — the identity fields were incidental to what it was proving, and
no test asserted the filled values against real profile data, only that
the flow completed and the pause mechanics worked.

## Problem

Two things, discovered together but logically separable: (1) where does
real applicant identity data come from at submission time, given
`SubmittableApplication`/`Application` carried none at all; and (2) how
should `_fill_form` turn a real `MasterProfile.basics.name` (one string)
into Greenhouse's separate `first_name`/`last_name` fields.

## Decision

### `Application` gains a required, frozen `applicant: BasicsSection` snapshot

Three options were weighed for getting real identity to `BrowserApplicator`:

- **(a) Inject `MasterProfile`/`BasicsSection` into the constructor**,
  resolved by some lookup at submit-time. Rejected: no such lookup exists
  or makes sense — Phase 6's `load_master_profile` is a plain function
  reading a path, and this is a single-user system with exactly one
  profile, so "look it up by id" doesn't apply.
- **(b) Add a `basics` parameter to the `Applicator` Protocol's
  `prepare`/`submit` methods.** Rejected: this widens the shared interface
  for one implementation's need — `TieredApplicator` and `EmailApplicator`
  would both have to accept and ignore or awkwardly consume a parameter
  they don't need. The same kind of interface pollution this project has
  avoided elsewhere (`HeldCandidateSink` was added because it is genuinely
  additive and optional to the sources that need it; this would not be).
- **(c) Snapshot identity onto `Application` itself, at
  `ResumeTailoringPipeline`-construction time, where `MasterProfile` is
  already in scope** (the same place `render_tailored_resume` was wired in,
  ADR-0025). **Chosen.**

(c) is not merely the smallest change — it is the more correct semantics.
A live lookup at submit-time (the alternative (a) would require) would let
a profile edit made *between* `prepare()` and `submit()` — correcting a
typo in a name, updating an email — silently submit under a *different*
identity than the one the resume content was actually gated and rendered
against. The submitted application's stated identity and its actual
content could come from two different moments in time, with nothing to
flag the mismatch. This is exactly the drift risk
`TailoredResume.profile_version` already exists to prevent for resume
content; `Application.applicant` extends the same "was this true when
submitted" discipline to identity. Everything about one `Application` —
content, gating verdict, and now identity — is frozen together at the
moment the pipeline builds it.

`applicant: BasicsSection` is **required, not optional-with-a-default** —
the same "impossible to construct otherwise" discipline `canonical_company`
and `provenance` already hold elsewhere in this codebase. An optional field
would let some future code path build a real `Application` with no
identity and have that go unnoticed until a real external form tried to
fill blank fields; a required field makes that a construction-time error
instead. Verified this bites: temporarily made the field
`BasicsSection | None = None`, confirmed
`test_application_requires_an_applicant_snapshot` failed
(`DID NOT RAISE ValidationError`), reverted.

Every existing `Application(...)` construction site across the test suite
(six test files) was updated to pass a real `BasicsSection`, not left with
a default that would have silently masked the requirement.

### `BrowserApplicator._fill_form` now reads real data, with a documented, known-imprecise name split

`_fill_form` reads `application.application.applicant.name`/`.email`
instead of the hardcoded placeholder strings. Splitting one JSON-Resume
`name` string into Greenhouse's separate `first_name`/`last_name` fields
needed a heuristic: `name.rsplit(" ", 1)` — the last whitespace-separated
token becomes `last_name`, everything before it becomes `first_name`; a
single-token name puts that token in `first_name` with an empty
`last_name`.

This is documented in the code as a **known-imprecise stopgap, not an
assumed-correct split** — it gets multi-part surnames ("van der Berg"),
suffixes ("Jr.", "III"), and non-Western name orders wrong. The docstring
states explicitly *why* this isn't solved properly now: real correctness
needs per-field human confirmation before a real submission (a person
checking the split before confirming), not a smarter heuristic — that is
named, deferred future work, not silently left for later.

Verified both the "real data lands" guarantee and the split heuristic
against a real, live Chromium page (not asserted as a claim): a new test
opens the real fixture form, calls `_fill_form` with a multi-part name
("Grace Beatrice Hopper"), and asserts the actual filled `input_value()`
of each field — proving the split lands as `"Grace Beatrice"` /
`"Hopper"`, and a single-token name ("Cher") falls back to an empty
`last_name`. Also verified by deliberate regression: reverted `_fill_form`
to the old hardcoded-string behavior, confirmed both new tests failed
against the real page, reverted back.

## Alternatives considered

- **(a)/(b) for identity sourcing** — see above; both rejected.
- **A smarter name-splitting library/heuristic (e.g. handling known
  particles like "van", "de", "von").** Rejected for this slice: still
  fundamentally guesses, and the honest fix is human confirmation, not a
  better guess. Documented as future work rather than half-solved now.
- **Building the real Tier-1 `ATSAdapter` instead, per the original next
  thread.** Rejected on investigation: verified across Greenhouse, Lever,
  and Ashby's own API docs that direct submission requires an
  employer-issued credential no generic applicant tool can obtain — not a
  scoping choice, a dead end for this project's arbitrary-company use case.

## Trade-offs

- **(+)** The one submission path that can actually carry real weight
  (`BrowserApplicator`, Tier 2) now fills a real applicant's real name and
  email rather than filing every application under a fake identity — a
  correctness bug that existed, merged, and passed prior full-intensity
  review, now fixed and independently re-verified against a live page.
  Identity and content are frozen together at one moment, closing a
  real-world drift risk a live lookup would have reopened.
- **(−)** The name-splitting heuristic remains genuinely imprecise for
  real-world edge-case names — named and documented, not silently
  papered over, but not solved. `Application` gaining a required field
  changed six pre-existing test call sites; a future domain-model
  reviewer must remember `applicant` exists wherever an `Application` is
  constructed.

## Consequences

- `domain/models.py`: `Application.applicant: BasicsSection` (required).
- `agents/resume/pipeline.py`: `ResumeTailoringPipeline.run()` populates
  `applicant=profile.basics` when building `Application`.
- `agents/apply/browser_applicator.py`: `_fill_form` reads real identity;
  new module-level `_split_name` helper, documented as a known-imprecise
  stopgap.
- Six test files updated to pass `applicant=` at every `Application(...)`
  construction site; two new tests in `test_browser_applicator.py` assert
  real filled values against a live Chromium page; one new test in
  `test_models.py` proves the required-field guarantee.
- This is a **prerequisite**, not a substitute, for generalizing
  `BrowserApplicator` past Greenhouse's one form (still separate, deferred
  future work) — a broken/fake-identity form-filler generalized to more
  ATS platforms would just produce more broken applications faster.

## Future revisit criteria

Revisit if:

- Real per-field human confirmation of the split name (or any other
  auto-derived form field) is built — replaces the heuristic's role
  entirely rather than improving it.
- `BrowserApplicator` is generalized past Greenhouse's one form (a
  separate, later design pass) — the same `applicant` snapshot should
  carry identity into whatever new per-ATS form-filling logic is built,
  and per-posting custom questions (EEOC, freeform "why do you want to
  work here") are real, reopened there, not solved by this ADR.
- Tier 1 direct-API submission becomes viable for some subset of use
  cases this project didn't originally target (e.g. a mode where the user
  supplies their own employer-issued API key for a company they already
  have a relationship with) — that would be new, explicitly scoped work,
  not a resurrection of the general "submit anywhere via API" premise this
  ADR found dead.
