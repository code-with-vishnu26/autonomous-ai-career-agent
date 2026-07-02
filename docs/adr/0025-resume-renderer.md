# ADR-0025: The resume renderer — where it runs, and why it never silently drops an entry

- **Status:** Accepted
- **Date:** 2026-07-02
- **References:** [ADR-0011](0011-structured-tailored-content.md) (structured
  tailored content; explicitly named a future downstream renderer as the
  thing that would eventually produce prose), [ADR-0013](0013-held-candidate-mechanism.md)
  (`HeldCandidateSink`, the "never trust upstream already handled this"
  precedent this ADR follows), [ADR-0016](0016-truthfulness-gate-verification.md)
  (`resolve_work_dates`, Case #6's correction), [ADR-0023](0023-resume-tailoring-pipeline.md)
  (`ResumeTailoringPipeline`, where rendering now happens)

## Context

Every real confirmation this project could perform (through Phase 8c) was
showing the user only `TailoredContent.summary` — `TailoredResume.rendered_text`
was documented as a "derived cache" since Phase 2 but nothing had ever
populated it, so the three `Applicator`s' `rendered_text or content.summary`
fallback always took the fallback branch. What started as a request to add
missing employment dates turned out, on inspection of the actual data flow,
to be a larger gap: no renderer existed at all.

## Problem

Where should `TailoredContent` (plus the `MasterProfile` needed to resolve
real dates) actually get turned into the plain text a human confirms and a
real company receives, and what should happen if a work or project entry's
`source_entry_id` can't be resolved when rendering?

## Decision

### Rendering happens once, at `ResumeTailoringPipeline`'s resume-creation time — not inside any `Applicator`

`ResumeTailoringPipeline.run()` (ADR-0023) already has both `draft.content`
and `profile` in scope at the exact moment it constructs `TailoredResume`.
Rendering there means `TailoredResume.rendered_text` is computed once and
matches its own documented contract exactly ("derived cache"). The
alternative — giving each of `TieredApplicator`/`BrowserApplicator`/
`EmailApplicator` its own `MasterProfile` access to render on demand — was
rejected: none of the three needs profile access for its actual job
(submitting), and three independent render implementations could drift
from each other, the same duplication risk this project has refused
elsewhere (the shared `ats_urls` module, the `_as_utc` precedent). Fixing
rendering at the pipeline layer required **zero changes to any
`Applicator`** — their `rendered_text or content.summary` fallback was
correctly designed from the start; it simply had nothing upstream feeding
it until now.

`rendered_text` is only computed for an **approved** draft. A rejected
draft's `rendered_text` stays `None`: it was never going to be submitted,
and — see below — rendering a rejected draft could itself raise, which
should never abort the pipeline's correctly-functioning rejection path.

### `render_tailored_resume` raises loudly on an unresolvable entry — never silently drops it

The renderer (`domain/rendering.py`) is a **second, independent consumer**
of `source_entry_id` references, the same status `SearchOpportunitySource`'s
re-parse-to-confirm logic (ADR-0015) and the gate itself hold: it must not
assume the truthfulness gate already ran and already blocked an
unresolvable reference. Considered silently skipping an entry that can't be
resolved (the renderer's job is just formatting, after all) — rejected: a
silently-dropped work entry would produce a resume that is quietly
*incomplete*, with no signal to anyone that a job was missing. That is
worse than today's prior gap (total and obvious — no rendering at all);
a per-entry silent skip would be partial and invisible, exactly the failure
mode `HeldCandidateSink` (ADR-0013) exists to prevent in a different layer,
applied here to a different kind of silent loss.

`render_tailored_resume` raises `KeyError` for both work entries (via the
existing `resolve_work_dates`) and project entries (a parallel check added
alongside it) — should be unreachable in practice, since the gate already
blocks an unresolvable `source_entry_id` as `employer_mismatch` before a
draft is ever approved, but "should be unreachable" is not the same claim
as "silently tolerated if it somehow isn't." Verified to actually catch a
regression: the loud-raise behavior was broken on purpose (wrapping the
date lookup in a swallowed `try`/`except KeyError: continue`), confirmed
the test failed, reverted.

**Skills are deliberately not resolved the same way.** `content.skills`
renders directly as plain strings, with no cross-check against
`profile.skills` — a considered asymmetry, not an oversight. A skill string
has no separate identity to resolve the way a `source_entry_id` does, so
there is no equivalent "does this reference exist" question for the
renderer to independently re-verify; the truthfulness gate already checks
exact skill presence (`skill_not_found`) during verification, which is the
only check that shape of value can meaningfully have.

### Test discipline: adversarial-matrix weight, not routine-formatting weight

This is the first artifact in the whole system a human outside the project
will actually read, and potentially the first thing a real company
receives. Tested accordingly: beyond the raise-on-unresolvable-entry proof
above, `test_render_produces_a_structurally_complete_resume` renders a
**realistic, multi-entry** profile (two work entries, two skills, one
project — not a single-work-entry fixture) and asserts every section a real
employer expects is actually present in the output: summary, both work
entries with their real resolved dates and highlights, both skills, and the
project with its highlights. Not "does it render without crashing" but
"does the output look like something a human would recognize as a genuine
attempt," the same standard held for the HN fixture matrix and the
truthfulness gate's adversarial cases.

## Alternatives considered

- **Render inside each `Applicator`, giving each a `MasterProfile`
  dependency.** Rejected: unnecessary coupling (submission logic doesn't
  need profile access) and triplicated, driftable render logic.
- **Silently skip an unresolvable work/project entry.** Rejected: produces
  an invisibly incomplete resume, worse than the total-and-obvious prior
  gap, and violates the "never trust upstream already verified this"
  discipline held everywhere else in this project.
- **Rendering a rejected draft too, for completeness/debugging.** Rejected:
  a rejected draft may contain exactly the unresolvable references the
  gate correctly caught, so rendering it could raise and abort a pipeline
  path that is otherwise working correctly; a rejected resume was never
  going to be submitted, so there is nothing real to render it for.

## Trade-offs

- **(+)** Every real confirmation this project can now perform shows a
  structurally complete resume, not a one-paragraph summary; the fix
  required no change to any `Applicator`; the "never silently drop an
  entry" guarantee is verified to actually catch a regression, not just
  asserted.
- **(−)** Plain text only this pass — no PDF, no ATS-specific form-field
  rendering (both named as future work by ADR-0011 already). The renderer's
  formatting is minimal (headers, dashes, no styling) — "prove the
  mechanism, not the product," matching every other first pass in this
  project.

## Consequences

- `domain/rendering.py`: `render_tailored_resume` added; `resolve_work_dates`
  unchanged.
- `agents/resume/pipeline.py`: now imports and calls
  `render_tailored_resume`, populating `TailoredResume.rendered_text` for
  approved drafts.
- No changes to `agents/apply/applicator.py`,
  `agents/apply/browser_applicator.py`, or `agents/apply/email_applicator.py`
  — their existing fallback logic is now actually fed.
- Every future confirmation preview a human sees will show the full
  rendered resume, not just the summary.

## Future revisit criteria

Revisit if:

- PDF or ATS-specific form-field rendering is built (ADR-0011's named
  future work).
- A richer plain-text format is wanted (better section ordering, basics
  contact info, education) — today's renderer covers summary/work/skills/
  projects only, matching what `TailoredContent` itself models.
- Performance ever matters enough that rendering per-draft (rather than
  cached/lazily) needs reconsidering — not a concern at this project's
  single-user scale today.
