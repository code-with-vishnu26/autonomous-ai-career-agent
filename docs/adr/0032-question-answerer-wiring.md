# ADR-0032: Wiring QuestionAnswerer into BrowserApplicator's live pause/resume flow

- **Status:** Accepted
- **Date:** 2026-07-03
- **References:** [ADR-0031](0031-question-answerer.md) (built `QuestionAnswerer`
  in isolation, named this wiring as deliberately deferred future work),
  [ADR-0020](0020-browser-tier-session-and-pause.md) (the original
  token-bound pause/resume guarantee this ADR extends to a second pause
  reason), [ADR-0027](0027-applicant-identity-snapshot.md) (`Application.
  applicant`, the frozen-snapshot precedent `Application.legal_status`
  applies one field wider), [ADR-0028](0028-browser-tier-dispatch-and-unsupported-field-refusal.md)
  (`UnsupportedFormFieldsError`'s original, broader scope, narrowed here)

## Context

ADR-0031 built `QuestionAnswerer` and proved its four-category guarantees
in isolation, explicitly deferring the harder question: how does a
component that classifies and answers a question in isolation actually
drive a live browser form, without weakening any of the guarantees Phase
8j spent its whole slice proving? This ADR is that wiring.

Three open questions were named in the pre-brief and decided before any
code was written, per this project's standing discipline.

## Decision

### 1. Two pauses, sequential by construction, not by convention

`BrowserApplicator.submit()` now has two phases relative to the existing
submit click:

- **Phase A (pre-click, `HumanActionRequired(reason="fields_need_human_input")`).**
  After known identity/resume fields are filled, every remaining required
  field is triaged through `QuestionAnswerer.classify_question`. A
  Category 2 (factual) field with an already-captured `LegalStatusSection`
  fact is filled automatically -- same tier as an ordinary known field, no
  pause. Everything else unresolved (EEOC, subjective, a missing
  legal-status fact, or a field this slice doesn't attempt to
  auto-resolve) is batched into **one** pause naming every unresolved
  selector, not one pause per field.
- **Phase B (post-click, `HumanActionRequired(reason="verification")`).**
  Unchanged from ADR-0020: click, check for a challenge, pause if present.

These are sequential by construction: Phase B is unreachable until Phase
A's own `resume()` has already re-verified its manifest and performed the
first submit click. There is no code path that reaches Phase B without
passing back through Phase A's re-check first -- this is the direct
answer to the pre-brief's sequencing question. It also dissolves the
original "does pause #2 need to re-verify pause #1" worry: there is no
pause #2 to worry about, because Phase A's N unresolved fields collapse
into one pause, not N.

### 2. The human fills Phase A's fields directly on the live page

`resume()` for either phase reuses `PauseAcknowledgment`'s existing shape
(ADR-0020) unchanged -- a token match, nothing more. No new acknowledgment
type carrying typed EEOC/legal-status/subjective answers was built. The
human fills every manifested field **directly in the visible browser
window**; `resume()`'s only job is to re-verify, against the live page,
that every manifested selector is now non-empty
(`RequiredFieldsStillUnresolvedError` if not) before proceeding to the
first submit click.

This is the strongest guarantee this ADR ships, and it is stronger than
"received the data and used it correctly": an EEOC response, under this
design, **never becomes a Python value this process holds at any point**.
There is no parameter, no local variable, no log line, no future refactor
that could ever leak, mis-route, or accidentally persist that data,
because nothing here ever holds it. This is the same category of move as
removing the date field from `TailoredWorkEntry` rather than trusting the
generator not to write one -- applied to data with real legal and
personal stakes, not resume content.

Cost, named plainly: this requires a visibly-interactive (non-headless)
browser at Phase A, not only at Phase B's CAPTCHA. There is no headless
version of this design that doesn't reopen the exact risk it eliminates --
a headless Phase A would require the opposite design (this code
constructing and typing in the answer itself). Given ADR-0008's
human-in-the-loop premise already requires a supervising human present at
Phase B, this is not a new category of burden, just a wider one.

### 3. `Application.legal_status`: the same frozen-snapshot precedent, one field wider

`BrowserApplicator` needs `LegalStatusSection` data to auto-fill a
Category 2 field it already has a captured fact for, but `submit()` never
receives a full `MasterProfile` -- only `Application.applicant:
BasicsSection`, a frozen identity snapshot (ADR-0027). `Application` gains
`legal_status: LegalStatusSection`, captured at the same
pipeline-construction moment `applicant` already is
(`ResumeTailoringPipeline`), required (always present, never
optional-with-a-default) for the same "impossible to construct otherwise"
reason `applicant` is required. This is not a new decision -- it is
ADR-0027's exact precedent applied one field wider, not a fresh judgment
call, as confirmed explicitly before implementation.

**`BrowserApplicator` gains zero dependency on `MasterProfile` storage as
a result -- this is a deliberate structural boundary, recorded here so a
future reader sees it as a choice, not an incidental fact about what
happened not to exist yet.** It only ever receives `legal_status` as
pre-frozen data, the same way it has always received `applicant`. It never
loads a profile file and never saves one.

A captured legal-status answer is **not** persisted back to the profile
for reuse by a future application in this slice. `storage/profile.py` has
only `load_master_profile` (ADR-0017) -- there is no `MasterProfile` writer
anywhere in this codebase to persist into. Building one is a real design
question of its own (file round-tripping, concurrent-edit safety, what
"bump the version" means for a hand-edited JSON file) that deserves its
own dedicated ADR, not something folded silently into this wiring. Named
honestly: the same legal-status question is asked again on a future
application unless the human separately edits their profile file by hand.
Safe (never worse than asking too often), consistent with this project's
"name the gap, don't silently drop it" discipline.

### `answer_factual_question`'s signature narrowed while wiring this in

Discovered during implementation, not planned in the pre-brief:
`answer_factual_question` only ever reads `MasterProfile.legal_status`, so
its parameter was narrowed from `profile: MasterProfile` to
`legal_status: LegalStatusSection` directly (ADR-0031's tests updated to
match, behavior unchanged). This is a strict reduction in what the
function could possibly touch -- the same minimization instinct behind
Case 1d's "no `MasterProfile` parameter at all" for EEOC, one register
down: Category 2 legitimately needs *some* profile data, but never more
than this one section.

### `UnsupportedFormFieldsError`'s scope narrows; a new exception covers the gap it leaves

ADR-0028's original `UnsupportedFormFieldsError` meant "any required field
this `FormFiller` doesn't know how to fill." It now means something
narrower: "a required field with no describable text at all" -- no
`aria-label`, no associated `<label>`, no `placeholder`. Every other
required field goes through Phase A's classify-then-manifest path
instead. Handing a human a blank, context-free field is close enough to
guessing that outright refusal remains the honest response for that one
case; every describable field gets a real chance at either auto-fill or a
human-visible manifest entry.

`RequiredFieldsStillUnresolvedError` is a new, distinct exception for
Phase A's re-verification failure -- deliberately not reused from
`ChallengeStillPresentError`, the same "different failure mode, own name"
precedent as `AmbiguousDropdownMatchError` vs. `UnsupportedFormFieldsError`
in ADR-0031.

### `_PausedSession`: one type with a `reason` discriminator, proven load-bearing

`_PausedSession` gained a `reason: Literal["fields_need_human_input",
"challenge"]` field and an optional `manifest: tuple[str, ...]`, rather
than becoming two separate types. This is a narrower case than
`ClaimVerdict`/`DropdownMatchResult` staying distinct types: those
represented genuinely different *judgments*; here the difference is only
in *what `resume()` re-verifies* on an otherwise-identical live page.

Per an explicit requirement before merge: a discriminator is only safe if
it is provably load-bearing, not decorative. `test_reason_discriminator_
actually_selects_the_right_reverification` constructs one pause of each
reason on the same live page and proves `resume()` genuinely branches --
a field-manifest pause raises `RequiredFieldsStillUnresolvedError`, never
`ChallengeStillPresentError`, and vice versa for a challenge pause.
Verified further by deliberate injection: forcing `resume()` to always
take the challenge branch (ignoring `paused.reason` entirely) was
confirmed to break this test and `test_resume_refuses_while_a_manifested_
field_is_still_empty` before being reverted.

### Category 4 (dropdown auto-matching) stays unwired this slice

Auto-matching a live dropdown against profile data (e.g. Education) would
require its own new frozen profile-data snapshot on `Application` (an
education snapshot, mirroring `legal_status`), which was never decided in
the approved pre-brief. Rather than invent that decision mid-implementation,
Category 4 fields land in the Phase A manifest like anything else this
slice doesn't auto-resolve -- a safe degradation (never a broken
guarantee, since manifested fields already get a human's direct
attention), named as explicit future work, not silently expanded scope.

### Conditional-field edge case: refuse rather than loop

A field filled during Phase A could, on some real form, reveal a new
required field the fixture-driven tests here don't exercise. Rather than
attempting a second Phase A pause automatically (an unbounded re-pause
hazard -- a maliciously or poorly designed form could trap a session in
infinite pauses), the existing `UnsupportedFormFieldsError`/manifest
machinery naturally re-triages on the next `submit()`-equivalent path;
no automatic re-pause loop was built. Named as a future revisit criterion,
not solved speculatively now.

## Load-bearing verification

Three guarantees were verified by deliberate injection before merge, per
this project's standing discipline -- never merged on "this should work":

- **The `reason` discriminator.** Injected: `resume()` ignoring
  `paused.reason` and always taking the challenge-check branch. Caught:
  both `test_reason_discriminator_actually_selects_the_right_reverification`
  and `test_resume_refuses_while_a_manifested_field_is_still_empty` failed.
  Reverted.
- **EEOC never auto-filled, at the wiring level, not just in isolation.**
  First injection attempt (calling `_try_fill_boolean_select` on an EEOC
  field) was *not* caught -- `match_dropdown_option`'s own refusal logic
  correctly declined to map "Yes" onto `["Female", "Male", "Decline to
  self-identify"]`, a genuine defense-in-depth finding worth recording,
  not a test gap. A second, direct injection (force-selecting the first
  non-blank `<option>` on any EEOC-classified `<select>`, bypassing
  dropdown-matching entirely) was caught by
  `test_eeoc_field_is_never_written_by_this_code_only_ever_by_the_human`.
  Reverted.
- **Post-revert clean state.** `diff` against a pre-injection copy of
  `browser_applicator.py` confirmed byte-identical after both reverts;
  full suite, `ruff`, and `lint-imports` all re-run clean afterward.

## Alternatives considered

- **A typed acknowledgment payload carrying the human's answers** (the
  alternative explicitly named in the pre-brief). Rejected: it would mean
  an EEOC response becomes data this process holds and writes into the
  DOM itself, reopening exactly the risk the chosen design eliminates. It
  would also require a second `PauseAcknowledgment`-shaped type per
  category, more surface area than the chosen design needs.
- **Two separate `_PausedSession` subclasses** instead of one type with a
  discriminator. Rejected once the discriminator was proven load-bearing
  by a real, injection-verified test -- the distinction that mattered
  (what gets re-verified) is provably real without needing two types to
  enforce it.
- **Persisting a captured legal-status answer back to `MasterProfile`
  immediately.** Rejected: no writer exists anywhere in this codebase;
  building one is real, separate work deserving its own ADR, not a
  same-slice addition.
- **Wiring Category 4 (dropdown) auto-matching this slice**, since
  `match_dropdown_option` already exists. Rejected: it requires a new
  frozen profile snapshot (education data) never decided in the approved
  pre-brief; adding it silently would be exactly the kind of
  scope-expansion-without-a-decision this project's discipline forbids.

## Trade-offs

- **(+)** The EEOC absolute now holds at the actual wiring level a real
  submission would exercise, not only in `QuestionAnswerer`'s isolated
  tests -- verified by an injection test targeting the integration point
  specifically, which caught a real gap on the first, weaker injection
  attempt (dropdown-matching's own refusal already blocked it) before a
  stronger injection proved the guarantee directly.
- **(+)** `Application.legal_status` extends an already-approved
  precedent rather than introducing a new kind of frozen data; no new
  category of drift risk is created.
- **(−)** Phase A requires a visibly-interactive browser, a real
  operational constraint beyond Phase B's existing CAPTCHA requirement.
- **(−)** Category 2 auto-fill is scoped to `<select>` elements only
  (`_try_fill_boolean_select`); a boolean question rendered as a radio
  group or checkbox pair still lands in the manifest even with a captured
  fact -- a real, current limitation, not yet a proven gap in practice
  (ADR-0030's real Greenhouse finding used dropdowns for its legal-status
  questions).
- **(−)** A legal-status fact captured during one application is not
  remembered for the next one -- the same question may be asked again.

## Consequences

- `src/career_agent/domain/models.py`: `Application.legal_status:
  LegalStatusSection` (required).
- `src/career_agent/agents/resume/pipeline.py`: snapshots
  `profile.legal_status` into `Application` at the same moment
  `profile.basics` already is.
- `src/career_agent/agents/apply/question_answerer.py`:
  `answer_factual_question` narrowed to take `LegalStatusSection` directly.
- `src/career_agent/agents/apply/browser_applicator.py`: two-phase
  pause/resume, `_triage_unhandled_fields`, `_try_fill_boolean_select`,
  `_field_question_text`, `_fields_still_empty`,
  `RequiredFieldsStillUnresolvedError`, `ManifestField`.
- `src/career_agent/core/events.py`: `HumanActionRequired.reason` gains
  `"fields_need_human_input"`.
- All 7 pre-existing `Application(...)` construction sites (pipeline +
  test fixtures) updated for the new required field.

## Future revisit criteria

Revisit if:

- A `MasterProfile` writer is built for any reason -- the deferred
  "persist a captured legal-status fact back to the profile" step becomes
  real work at that point, not before.
- A real posting's Category 2 question is rendered as anything other than
  a `<select>` (radio group, checkbox pair) -- `_try_fill_boolean_select`'s
  scope would need to widen, or an explicit decision to leave those to the
  manifest permanently should be recorded.
- Category 4 (dropdown) auto-matching is wired in -- requires deciding
  whether `Application` gains an education (or other) frozen snapshot,
  the same category of decision this ADR made explicitly for
  `legal_status` rather than assuming.
- A real conditional-field form (filling one Phase A field reveals a new
  required one) is encountered -- the refuse-rather-than-loop default
  should be revisited with real evidence in hand, the same way ADR-0030's
  Greenhouse finding motivated this whole ADR.
