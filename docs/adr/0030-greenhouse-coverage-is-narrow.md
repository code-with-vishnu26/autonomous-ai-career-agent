# ADR-0030: Real Greenhouse coverage is narrow -- resume_text confirmed, but "Tier 2 works" overstates practical completeness

- **Status:** Accepted
- **Date:** 2026-07-03
- **References:** [ADR-0020](0020-browser-tier-session-and-pause.md)
  (`BrowserApplicator`'s original Greenhouse fixture, whose `#resume_text`
  assumption this ADR resolves), [ADR-0028](0028-browser-tier-dispatch-and-unsupported-field-refusal.md)
  (`_unhandled_required_fields`, the refusal mechanism whose real-world
  trigger rate this ADR corrects the record on), [ADR-0029](0029-per-filler-challenge-and-submit-selectors.md)
  (the Lever DOM inspection this ADR's Greenhouse inspection mirrors)

## Context

The user personally inspected a real, live Greenhouse posting (a
ZipRecruiter job) via browser dev tools -- the same verification method
that resolved ADR-0029's Lever findings, applied here to the one platform
this project had been treating as its fully proven baseline. Two real
findings resulted, one resolving an open question favorably, one
surfacing a bigger, previously unrecorded gap.

## Finding 1: `resume_text` is a real, DOM-confirmed form option -- with a caveat

Greenhouse's real apply form has an explicit **"Enter manually"** option
for both Resume/CV and Cover Letter, alongside Attach/Dropbox/Google
Drive. This upgrades `resume_text` from "documented in Greenhouse's API,
but unconfirmed whether the candidate-facing UI actually exposes it" to
**DOM-confirmed: a real, visible option a real candidate can choose.**

This is a genuine, positive resolution -- not an assumption that turned
out wrong, unlike Lever's identity-field `id` assumption in ADR-0029.

**Not yet confirmed, and worth stating precisely rather than rounding up
to "closed":** the real form exposes "Enter manually" as one *choice*
among several (Attach/Dropbox/Google Drive/manual), which strongly
suggests a mode-toggle UI -- selecting "Enter manually" likely reveals a
text field that may not be `#resume_text` had by simply being visible on
page load the way the current fixture (and `GreenhouseFormFiller`'s
unconditional `page.fill("#resume_text", summary)`) assumes.
Whether the real toggle needs to be clicked first, and what the revealed
field's real selector actually is, remain unconfirmed. `resume_text`
existing as a real concept is confirmed; `GreenhouseFormFiller`'s current
unconditional-fill interaction with it is not yet proven correct against
the real toggle-gated UI.

## Finding 2: an ordinary real Greenhouse posting requires far more than identity + resume

The same inspection surfaced something bigger. On an **ordinary** posting
(not a deliberately unusual or maximally-configured one), the real form
also required: **Education** (School/Degree/Discipline dropdowns), **three
explicit legal work-authorization yes/no questions**, a full **Voluntary
Self-Identification section** (Gender, Hispanic/Latino), and a **Veteran
Status section with legal definitions**.

`GreenhouseFormFiller.known_field_selectors` covers exactly four fields:
name, email, resume. `_unhandled_required_fields` correctly refuses to
submit through any posting carrying required fields beyond that set --
which, per this finding, is **most real Greenhouse postings, not an edge
case.**

This is not a bug. The refusal is doing exactly what ADR-0028 designed it
to do, and doing it correctly is precisely why this finding is safe to
have made this late -- nothing was ever silently mis-filed. But the
project's own record has, until now, characterized this as "Tier 2 works
for Greenhouse" without qualifying what fraction of real postings that
actually covers. **The honest statement is: Tier 2 currently means
"correctly refuses most real Greenhouse postings, and completes only the
minority with minimal custom fields" -- not "completes most real
Greenhouse applications."** Those are different claims, and only the
narrower one has ever actually been proven.

## Decision

No code change is required by this ADR -- the refusal mechanism is
already behaving correctly; this is a correction to what the project's
record claims about it, not a defect to fix. Two corrections made:

1. This project's documentation (ROADMAP, ADR-0028's characterization of
   the custom-questions/EEOC gap) is corrected to state the real,
   narrow practical coverage plainly, rather than letting "Tier 2 works"
   continue to imply broader real-world completion capability than has
   ever been demonstrated.
2. **The custom-questions/EEOC answering design (already named, deferred
   future work since ADR-0028) is re-prioritized in the record from "a
   generalization nice-to-have" to "the actual gate on this system's
   practical usefulness on the one platform it already supports."**
   Without it, `career-agent apply` can assemble, gate, and truthfully
   render a resume for any Greenhouse posting, but can only complete
   submission through Tier 2 for the minority of postings with minimal
   custom fields -- for most real postings, today, the honest end state
   of a real run is a correct, safe refusal, not a completed application.

## Alternatives considered

- **Treat this as closed once `resume_text` was DOM-confirmed**, since
  that was the specific open question from ADR-0029. Rejected: the
  ZipRecruiter posting's field requirements are a materially bigger,
  separate finding that a narrow "resume_text: confirmed" framing would
  have buried. Naming both, at their actual relative importance, matters
  more than closing the smaller one cleanly.
- **File this as a bug against `_unhandled_required_fields` or
  `GreenhouseFormFiller`.** Rejected: nothing is broken. The refusal is
  the correct, safe behavior for a field this project has no honest way
  to answer. The correction is to the *record's claims*, not the code.

## Trade-offs

- **(+)** The project's record now honestly reflects what has actually
  been demonstrated: a real fixture-based resume-text concern resolved
  with genuine DOM evidence, and a real, previously unstated scope
  limitation surfaced before it could mislead a future reader (or a
  future "let's ship this" decision) into overestimating how much of
  Tier 2's real-world value has actually been proven.
- **(−)** `career-agent apply`'s practical completion rate on real
  Greenhouse postings is lower than the project's own prior framing
  implied. The custom-questions/EEOC design pass is now understood to be
  load-bearing for practical usefulness, not merely thorough, which may
  change its priority relative to other deferred work (multi-tier
  selection, the real Gmail client).

## Consequences

- `ROADMAP.md`: Phase 8g/8h narrative corrected to state Tier 2's real,
  narrow coverage plainly.
- `docs/adr/0028-...md`: cross-referenced from here; its own
  "Future revisit criteria" already named the custom-questions/EEOC
  design pass as deferred work -- this ADR corrects the record on how
  urgent that deferred work actually is, without altering ADR-0028's own
  decision.
- The next real design pass on custom-questions/EEOC answering should be
  scoped with this finding in hand: it is not solving a rare edge case,
  it is solving the majority case for Greenhouse, this project's only
  currently-functional ATS platform.
- `GreenhouseFormFiller`'s resume-field interaction (does it need to
  click an "Enter manually" toggle first? what's the revealed field's
  real selector?) remains a named, open, smaller verification gap.

## Future revisit criteria

Revisit if:

- The exact real interaction sequence for Greenhouse's resume field
  (toggle-click-then-fill vs. always-visible) is confirmed via a closer
  dev-tools inspection -- `GreenhouseFormFiller.fill_identity_and_resume`
  may need updating to match.
- The custom-questions/EEOC answering design (ADR-0028's deferred item,
  re-prioritized here) is undertaken -- this ADR's finding is the concrete
  evidence for why it matters in practice, and should be cited as the
  motivating data point.
- A second and third real Greenhouse posting (different companies) are
  inspected to confirm whether this level of required custom/EEOC fields
  is typical or this one posting's own configuration choice.
