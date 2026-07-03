# ADR-0028: Browser-tier per-ATS dispatch, unsupported-field refusal, and deferring the custom-questions problem

- **Status:** Accepted
- **Date:** 2026-07-03
- **References:** [ADR-0003](0003-truthfulness-gate.md) (the epistemic
  "ground it in evidence or block it" discipline this ADR explicitly does
  *not* try to extend to EEOC questions, and why), [ADR-0019](0019-ats-kind-resolution-and-tier-fallback.md)
  (`resolve_ats_kind`, reused here for browser-tier dispatch),
  [ADR-0020](0020-browser-tier-session-and-pause.md) (`BrowserApplicator`,
  originally Greenhouse-only), [ADR-0027](0027-applicant-identity-snapshot.md)
  (`Application.applicant`, `_split_name`, and the two independent Tier-1
  API-credential verifications this ADR's Lever/Ashby investigation
  extends into a third, DOM-level verification attempt)

## Context

ADR-0027 confirmed Tier 1 direct-API submission is dead for arbitrary
companies, and fixed `BrowserApplicator`'s hardcoded-placeholder-identity
bug, making it the only tier that can carry real submission weight. That
ADR explicitly deferred two things: generalizing `BrowserApplicator` past
Greenhouse's one form, and the custom-questions/EEOC problem that
generalization would reopen. This ADR is that deferred design pass.

## Problem

Three real, separable questions: (1) how does `BrowserApplicator` dispatch
to the right form-filling logic per ATS platform; (2) what happens when a
real posting's form has a field (a custom question, an EEOC/demographic
question) no filler knows how to answer; (3) is any part of *answering*
those questions in scope for this slice.

## Decision

### Dispatch: a per-`ats_kind` `FormFiller`, resolved the same way Tier 1 resolves its adapter

`form_fillers.py` (new) defines a `FormFiller` Protocol (`ats_kind`,
`known_field_selectors`, `fill_identity_and_resume`) and
`BrowserApplicator` now resolves which one applies via
`resolve_ats_kind(opportunity.source_url)` -- the identical pattern-match
ADR-0019 built for Tier 1, reused rather than reinvented.
`NoApplicableFormFillerError` mirrors `NoApplicableAdapterError` for an
unresolvable URL or an unregistered `ats_kind`.

### Real Lever/Ashby selectors could not be verified -- so they are explicit stubs, not guesses

Before writing any selector code, real live Lever and Ashby postings
needed inspection. **Two independent attempts, from two different
vantage points, both hit real walls:**

- From inside this codebase's sandbox: `WebFetch` returned `403` on every
  live posting tried (four different companies across both platforms);
  a real Chromium instance (the same one this project's own tests use)
  could not reach any live internet host at all
  (`net::ERR_TUNNEL_CONNECTION_FAILED`) -- this sandbox's browser
  automation is scoped to local fixtures only.
- Separately (outside this sandbox, with real web access): documentation
  could be reached, but not rendered page DOM. That search did confirm
  something useful, though not a workaround: Lever's own help docs state
  "Full Name" and "Email" are the *only* two fields guaranteed present on
  every posting -- everything else is independently configurable per
  company, which argues against a plausible-but-unverified static
  selector map more strongly than mere uncertainty would. Lever also
  exposes a `GET /v1/postings/:posting/apply` endpoint that could
  enumerate a posting's real fields programmatically -- but it requires an
  employer-issued API key, the identical submit-side-auth wall ADR-0027
  already confirmed kills Tier 1, so it is **not** a usable workaround.
  Recorded here explicitly as "checked, does not help," not left as an
  open possibility someone might mistakenly revisit later.

Given that, `LeverFormFiller` and `AshbyFormFiller` are explicit stubs:
`known_field_selectors = frozenset()`, and `fill_identity_and_resume`
unconditionally raises `FormFillerNotImplementedError` naming exactly what
is missing and what closes the gap (a human inspecting real live
postings). They are still *registered* in `default_form_fillers()` (rather
than omitted) so a real Lever/Ashby opportunity gets a specific,
informative "not verified yet" error instead of the less useful generic
"no filler registered at all" -- the caller learns *why*, not just *that*.

### The refusal: platform-agnostic, live-DOM-verified, required-fields-only

`BrowserApplicator.submit()` now checks, after filling identity/resume and
before ever clicking submit, whether the live page's actual form has any
*required* field not in the active `FormFiller`'s declared
`known_field_selectors`. If so, it raises `UnsupportedFormFieldsError` and
closes the browser -- never clicks, never guesses, never leaves the
question for a human to react to after the fact.

This check is deliberately **generic against the real page's actual `form`
elements** (`page.query_selector_all("form input, form textarea, form
select")`), not a fixed per-platform list of "known custom question
selectors" -- the mechanism, not per-platform knowledge, is what makes the
refusal possible, so it works identically whichever ATS's form is loaded,
including a Greenhouse posting that happens to have a custom question the
fixture never modeled.

**Only required fields trigger a refusal.** An optional field with no
answer is left blank -- leaving an optional field unanswered is honest;
only a required field with no safe way to answer it actually blocks
submission. This is a deliberate, narrow scope, not an oversight: it
means this mechanism can ship now, doing real, verifiable work, without
first resolving question (3) below.

Verified against a real, live Chromium page, not asserted: a second
fixture (`apply_form_with_extra_question.html`) adds one required field
(`#why_us`) beyond Greenhouse's known set; `_unhandled_required_fields`
is proven to return `[]` against the ordinary fixture and `["#why_us"]`
against the extra-question one, and `submit()` is proven to raise
`UnsupportedFormFieldsError` and never reach `#submit_app` for that
posting. Verified to actually bite by deliberate injection: disabled the
`if unhandled:` check, confirmed the refusal test failed; disabled the
dispatch's `if filler is None:` check, confirmed the unresolvable-URL test
failed; reverted both.

### Custom questions / EEOC fields: named and deferred, with an absolute stated now for the EEOC case specifically

Whether and how to actually *answer* a required custom or EEOC question is
explicitly **out of scope for this slice** -- it is real, hard, and
truthfulness-adjacent design work, deserving its own dedicated ADR, not a
rider on a mechanical dispatch extension. Three categories were identified
as the shape that ADR will need to address, and are recorded here so the
distinction isn't lost or re-flattened into "just draft an answer" later:

- **Profile-groundable factual questions** (e.g. work authorization,
  years of experience with a specific technology) have real evidence to
  check against, structurally similar to a resume claim -- any future
  answering mechanism for these should route through the actual
  truthfulness gate machinery, not a parallel one invented for this
  purpose.
- **Subjective/motivational freeform questions** ("why this company")
  have no evidence to ground an answer in at all -- an invented answer
  here is not equivalent to a gate-checkable resume claim, it is worse:
  there is no profile fact to verify it *against*. These must always be
  human-authored, never auto-drafted, the same "no default-to-yes"-shaped
  discipline as everything else in this project's human-in-the-loop
  design.
- **EEOC/demographic self-identification questions are categorically
  different from both, and this is the one absolute this ADR states
  without qualification.** Every other truthfulness guarantee in this
  project exists to stop the system from making an unverified claim about
  something that is true. An EEOC question is not asking for a fact that
  could be verified -- it is asking the person to exercise a legally
  protected choice about disclosure itself, including the choice to
  decline. There is no `MasterProfile` field this could ever be honestly
  grounded in, not because the data model is incomplete, but because the
  right design is that it never should be. "Guess, then ask the human to
  confirm" is not a safer, lesser version of "ask the human directly" for
  this category -- it is a different and inappropriate act, because it
  puts a demographic assumption in front of a person and asks them to
  react to it, rather than letting them originate the answer themselves.
  **The only acceptable behaviors, with no exceptions: leave the field
  unanswered where the form permits that, or pause and let the human
  supply their own, entirely unprompted answer.** No suggested default,
  ever, under any circumstance -- the same fail-closed, no-exceptions
  posture as the truthfulness gate itself, but grounded in a legal/ethical
  reason rather than an epistemic one.

## Alternatives considered

- **LLM-drafts-an-answer for custom questions.** Rejected as a default:
  explicitly the same shape of ungrounded-content problem ADR-0003 exists
  to prevent, worse for freeform/motivational questions specifically
  because there is no profile fact to check an invented answer against at
  all.
- **A single "human confirms everything" policy across all three
  categories**, treating EEOC questions the same as subjective ones (both
  routed to a human-confirmation step). Rejected once examined closely:
  conflates "a human should write this" with "a human should originate
  this from nothing," which are different requirements for EEOC data
  specifically -- confirming a system-generated guess is not equivalent to
  the human typing their own unprompted answer.
- **Omitting Lever/Ashby from `default_form_fillers()` entirely** rather
  than registering explicit stubs. Rejected: an omitted entry produces a
  less informative "nothing registered" error than a stub naming exactly
  what's missing and how to close the gap.
- **Flagging *any* field (required or not) the filler doesn't know as
  unsupported.** Rejected as unnecessarily conservative: an optional field
  can be honestly left blank without misrepresenting anything; only a
  required field with no safe answer actually blocks a truthful
  submission.

## Trade-offs

- **(+)** `BrowserApplicator` now generalizes its *dispatch* correctly
  (resolved via the same trusted pattern-match as Tier 1) and, more
  importantly, has a real, live-DOM-verified structural guarantee against
  ever guessing at a field it doesn't understand -- proven to actually
  block submission, not merely documented as an intention. The EEOC
  absolute is stated plainly, in code and in this record, before any
  answering mechanism gets built that might otherwise be tempted to treat
  it as just another confidence threshold.
- **(−)** Lever and Ashby remain non-functional for real submission --
  registered but stubbed, not usable, pending a human doing the live-page
  inspection neither automated attempt could complete. Custom/EEOC
  question *answering* remains entirely unbuilt; a real posting requiring
  any required field beyond identity+resume cannot be submitted through
  this tier yet, on any platform, including Greenhouse.

## Consequences

- `src/career_agent/agents/apply/form_fillers.py` (new): `FormFiller`
  Protocol, `GreenhouseFormFiller` (real, moved from
  `browser_applicator.py` without behavior change), `LeverFormFiller`/
  `AshbyFormFiller` (stubs), `FormFillerNotImplementedError`,
  `default_form_fillers()`.
- `src/career_agent/agents/apply/browser_applicator.py`: `prepare()`
  resolves a `FormFiller` via `resolve_ats_kind`; `submit()` calls
  `fill_identity_and_resume` then `_unhandled_required_fields` before
  `#submit_app` is ever clicked; `NoApplicableFormFillerError`,
  `UnsupportedFormFieldsError` (new); `on_context_ready` constructor seam
  (test-only, lets tests route a real-looking ATS URL to a local fixture
  without any real network request).
- `tests/fixtures/greenhouse/apply_form_with_extra_question.html` (new).
- The next real ATS-form slice must decide the custom-questions/EEOC
  answering design in its own dedicated ADR before any required-field
  posting on any platform can actually be submitted through Tier 2.

## Future revisit criteria

Revisit if:

- A human inspects real live Lever and/or Ashby postings and reports back
  actual field selectors -- `LeverFormFiller`/`AshbyFormFiller` can then be
  built for real, following `GreenhouseFormFiller`'s pattern.
- The custom-questions/EEOC answering design is undertaken -- its own
  dedicated ADR, per this one's explicit deferral. It must preserve the
  three-category distinction named here, and must not relax the EEOC
  absolute (leave-blank-or-human-originates-only, no exceptions) under any
  framing, including "the human confirmed it first."
- Real multi-tier selection is designed (still deferred since ADR-0024) --
  it will need to reason about a `BrowserApplicator` that can now itself
  refuse a specific opportunity (`UnsupportedFormFieldsError`) as a
  distinct outcome from "this tier doesn't apply at all"
  (`NoApplicableFormFillerError`).
