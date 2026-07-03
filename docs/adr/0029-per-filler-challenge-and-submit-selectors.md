# ADR-0029: Per-FormFiller challenge/submit selectors and name-based field matching

- **Status:** Accepted
- **Date:** 2026-07-03
- **References:** [ADR-0020](0020-browser-tier-session-and-pause.md)
  (`BrowserApplicator`'s pause/resume machinery, whose challenge-detection
  and submit-click selectors this ADR generalizes), [ADR-0028](0028-browser-tier-dispatch-and-unsupported-field-refusal.md)
  (`FormFiller`, `known_field_selectors`, `_unhandled_required_fields` --
  the mechanisms this ADR extends), [ADR-0027](0027-applicant-identity-snapshot.md)
  (the "don't build on an unverified assumption" discipline this ADR's
  scoping decisions repeat)

## Context

After ADR-0028 shipped, the user personally inspected a real, live Lever
posting (Palantir) via browser dev tools — the one verification path
neither this codebase's sandbox nor any automated tool available in this
conversation could reach (confirmed across four independent attempts: this
sandbox's Playwright cannot reach live internet hosts at all; this
session's `WebFetch` returned `403` on every live posting tried; a
separate `web_fetch`/`web_search` attempt got readable job-description text
but no form DOM; and Ashby's board turned out to be a client-side React SPA
returning no server-rendered content to any static tool at all).

That real inspection returned concrete, load-bearing findings ADR-0028's
stub-only scope did not anticipate:

- Lever's identity fields have **no `id` attribute at all**, only
  `name` (`name="name"`, `name="email"`) — `_unhandled_required_fields`
  only ever built an `#id`-shaped selector, so it could never have matched
  a `known_field_selectors` entry for a real Lever field even if one were
  declared.
- The posting used **real hCaptcha markup** (`div#h-captcha` with a
  sitekey, a hidden `h-captcha-response` field, a hidden submit button) —
  `BrowserApplicator.submit()`/`resume()` hardcoded
  `page.is_visible("#verification-challenge")` and
  `page.click("#submit_app")` directly, both literal strings from
  Greenhouse's own test fixture, which would never match hCaptcha's real
  markup at all.
- The posting had a real EEO section (`data-qa="eeo-section"`) — confirming
  ADR-0028's refusal mechanism has a genuine real-world target, not a
  hypothetical one.
- The resume field is a collapsed `<li class="application-question
  resume">` with a `resumeStorageId` hidden field, suggesting a JS-driven
  file-upload widget rather than a fillable text field — unconfirmed
  whether a text-paste alternative exists.

## Problem

Which of these findings justify a code change now, versus which stay
blocked on a further unknown. Building indiscriminately on all of it would
repeat exactly the mistake this project has refused before (guessing where
real evidence is still incomplete); refusing to build anything until every
unknown is resolved would delay real, already-justified fixes for no
reason.

## Decision

### Three mechanical generalizations, built now: justified by confirmed evidence, independent of any remaining unknown

1. **`_unhandled_required_fields` now derives a field's selector from
   whichever attribute it actually has** -- `#id` first, then
   `[name='...']` -- instead of assuming `#id` always exists.
   `known_field_selectors` entries are documented as arbitrary CSS
   selectors, not assumed `#id`-shaped.
2. **`FormFiller` gains `challenge_selector`/`submit_selector`** declared
   fields. `BrowserApplicator.submit()`/`resume()` now read
   `filler.challenge_selector`/`filler.submit_selector` instead of the two
   literal strings previously hardcoded directly in the class.
   `GreenhouseFormFiller` declares its existing fixture markers
   (`#verification-challenge`/`#submit_app`) as those fields -- pure
   "hardcoded → declared," no behavior change for the one platform that
   already works for real.
3. `_PausedSession` gains a `filler` field so `resume()` can reach the same
   declared selectors a paused submission's `submit()` call used, keeping
   the two methods' selector sources consistent.

All three are justified by evidence already in hand, are strict
improvements to `GreenhouseFormFiller`'s own honesty regardless of what
Lever/Ashby ultimately need, and require no knowledge of the still-unknown
resume-field interaction shape to build correctly.

**Explicit acceptance bar for this slice:** since Greenhouse is the one
platform with a fully proven, live-DOM-verified path (ADR-0020's
CAPTCHA-pause tests, ADR-0027's real-name-fill test), the existing test
suite must pass **unchanged** after the hardcoded-to-declared refactor --
proof this is a pure generalization, not an accidental behavior change to
the one thing that already works end to end. Confirmed: all pre-existing
`test_browser_applicator.py` tests pass with zero modifications to their
own code, only to `browser_applicator.py`/`form_fillers.py`.

New coverage added for the two new mechanisms themselves, against a fixture
(`tests/fixtures/lever/apply_form.html`) deliberately shaped like the real,
confirmed Lever DOM (name-only fields, differently-named challenge/submit
markers, not Greenhouse's `#id`/`#verification-challenge`/`#submit_app`
shape) and a test-only `FormFiller` (`_AltSelectorFormFiller`) exercising
custom selector values end to end through `prepare()`/`submit()`/`resume()`.
Verified to actually bite by deliberate injection: reverted the
`id`-then-`name` derivation to `id`-only, confirmed the name-matching test
failed; reverted `submit()`'s click/visibility checks to the old hardcoded
literals, confirmed a real Playwright `TimeoutError` occurred waiting for
a selector that doesn't exist on the alt fixture (both in `submit()` and,
separately, in `resume()`'s pause/re-click path); reverted all four.

### `LeverFormFiller`/`AshbyFormFiller` stay stubs: the resume-field unknown blocks real implementation, selectors alone do not unblock it

Building `LeverFormFiller.fill_identity_and_resume` for real was
explicitly **not** done in this slice, even with real name/email selectors
now confirmed and matchable. The resume field's real interaction shape
(plain text vs. a JS-driven file-upload widget) is still unconfirmed, and
this project has no resume *file* artifact anywhere in its domain model —
`SubmittableApplication` only ever carries `rendered_text`. Guessing at
file-upload interaction code here would repeat the exact "silently mis-file
a real application" risk this project has refused at every prior
boundary (the promptfoo gate, the Tier 1 API-credential wall, the
identity-snapshot gap). `LeverFormFiller`/`AshbyFormFiller`'s
`challenge_selector`/`submit_selector` are left as empty strings, explicitly
documented as unused-because-unverified rather than guessed placeholder
values, since `fill_identity_and_resume` still raises before either would
ever be read.

## Alternatives considered

- **Wait for the resume-field answer before building any of this slice.**
  Rejected: the three mechanical fixes don't depend on it at all, and
  Greenhouse's own selectors benefit from becoming declared regardless of
  what Lever/Ashby ultimately need. Holding evidence-justified fixes
  hostage to an unrelated open question serves no purpose.
- **Guess at a `LeverFormFiller.fill_identity_and_resume` for the
  confirmed identity fields, leaving only the resume field unhandled somehow.**
  Rejected: `fill_identity_and_resume` fills identity *and* resume as one
  unit; splitting it to work around one unconfirmed field is itself new,
  unreviewed design surface, and the honest state is still "not ready,"
  not "partially ready."
- **Populate `challenge_selector`/`submit_selector` on the stubs with a
  plausible guess** (e.g. the real hCaptcha selectors confirmed on this one
  posting) in case they're useful later. Rejected: those values are real
  for the one posting inspected, but nothing confirms they're stable
  across companies on Lever, and populating them risks a future reader
  assuming they're verified-for-general-use when they're one data point.
  Left empty and explicitly documented instead.

## Trade-offs

- **(+)** `FormFiller`'s shape now correctly generalizes to what a real,
  live posting actually looks like (no-`id` fields, real CAPTCHA markup),
  fixed once at the Protocol level rather than needing rediscovery per
  platform. Greenhouse's own selectors are more honest (declared, not
  hardcoded) with zero behavior change, proven by the full existing suite
  passing unchanged.
- **(−)** `LeverFormFiller`/`AshbyFormFiller` remain non-functional --
  closer to real (selectors for two of three fields are now a known,
  buildable shape) but still blocked on the resume-field question. Only
  one company's Lever posting has been inspected; whether its challenge
  markup or field shape generalizes across other companies on the platform
  is still unconfirmed.

## Consequences

- `src/career_agent/agents/apply/form_fillers.py`: `FormFiller` Protocol
  gains `challenge_selector`/`submit_selector`; `GreenhouseFormFiller`
  declares its real values; `LeverFormFiller`/`AshbyFormFiller` declare
  empty-string placeholders, documented as unused.
- `src/career_agent/agents/apply/browser_applicator.py`:
  `_unhandled_required_fields` derives `#id`-or-`[name='...']`;
  `submit()`/`resume()` read selectors from the active `FormFiller`;
  `_PausedSession` gains a `filler` field.
- `tests/fixtures/lever/apply_form.html` (new): a fixture shaped like the
  real, confirmed Lever DOM, used to prove both new mechanisms against a
  live page, not just Greenhouse's own shape.
- The next real Lever/Ashby slice must resolve the resume-field question
  (plain text vs. file upload, and whether a resume-file-generation
  capability needs to be built) before `LeverFormFiller` can move past a
  stub, in addition to confirming identity-field/challenge selectors are
  stable across more than one company.

## Future revisit criteria

Revisit if:

- The resume field's real interaction shape is confirmed (text-paste
  alternative exists, or a file-upload capability gets built) --
  `LeverFormFiller.fill_identity_and_resume` becomes buildable for real.
- A second and third real Lever posting (different companies) are
  inspected -- confirms or refutes whether name/email selectors and
  hCaptcha markup generalize, or whether Lever's per-company
  configurability (already confirmed via its own docs, ADR-0028) means
  per-company selector variance is a real problem this design needs to
  account for.
- Ashby's real DOM is ever inspected (still fully blocked -- client-side
  React SPA opaque to every tool tried) -- `AshbyFormFiller` follows the
  same path as `LeverFormFiller` once real data exists.
