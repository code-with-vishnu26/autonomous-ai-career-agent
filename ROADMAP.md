# Roadmap

The project is built **one phase at a time**. We stop and commit after each
phase, and we do not generate everything at once. Each phase below lists its
goal and its definition of done.

> **Guiding principle:** quality over volume, truthfulness non-negotiable, no core
> rewrites to add capabilities. Significant architectural decisions are recorded
> as ADRs in [`docs/adr/`](docs/adr/).

---

## ✅ Phase 1 — Project structure *(this commit)*
Scaffold the repository: `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`,
`CONTRIBUTING.md`, `LICENSE`, `docs/` + `docs/adr/` (with **ADR-0001** recording
the agent-oriented architecture decision), `.gitignore`, `requirements.txt`,
`pyproject.toml`, and the package skeleton under `src/career_agent/`.
**Done when:** the structure exists, documents are coherent, and the layout has
been reviewed.

## ✅ Phase 2 — Architecture + interfaces
Define the core abstractions and Pydantic models: agent base interface, event
types, the `Opportunity` / `Resume` / `Application` domain models, the plugin
extension-point protocols, and the Planner's decision contract. Interfaces only —
no heavy implementation. Delivered a dependency-free `domain/` layer split from
the orchestration-facing `core/` layer, with ADR-0011 recording the structured
tailored-content decision.
**Done when:** typed interfaces compile, are documented, and an ADR captures the
interface design.

## ✅ Phase 3 — Plugin system + event bus
Implement the plugin registry and the publish/subscribe event bus that everything
else builds on. Include discovery/registration of plugins and event dispatch with
tests. Registry keys by `(extension-point protocol, name)`; the bus is in-process,
best-effort, with error-isolated delivery — and, critically, **events notify but
do not gate** (safety-critical blocks are enforced inline, never via delivery;
ADR-0005 amendment). Dependency direction is now enforced by import-linter in the
test suite.
**Done when:** a sample plugin can register and agents can communicate purely via
events, covered by tests.

## ✅ Phase 4 — Discovery Engine (with one named gap — see below)
Discovery Agent + first opportunity sources: Greenhouse / Lever / Ashby ATS APIs,
then YC `hiring.json` + Hacker News, then Career Page Finder + ATS Detector, then
the provider-abstracted search layer (Exa + Google CSE failover).
**Done when:** real openings can be discovered and normalized into `Opportunity`
records, ToS-respecting, with tests.

Sub-slices, all merged: **4a** Discovery Agent + wiring + one real source
(Greenhouse). **4b** remaining ATS/feed sources, split: **4b-ATS** Lever + Ashby
(same shape as Greenhouse — proved the `OpportunitySource` contract survives a
differently-shaped API of the same kind; `interfaces.py` diff empty), then
**4b-feeds** YC `hiring.json` + HN "Who's Hiring" (the harder test — a firehose to
filter, no structured job object; ADR-0013's held-candidate mechanism landed
here). **4c** the provider-abstracted search layer + dynamic ranking (ADR-0002),
split further: **4c-slice-1** cross-source identity (ADR-0014), **4c-slice-2**
Exa `SearchProvider` + web-search classification (ADR-0015, applying ADR-0013 to
search), **4c-slice-3** Google CSE + capability/health ranking (ADR-0002
amendment).

> **Phase 4c decision checkpoint — resolved in [ADR-0014](docs/adr/0014-cross-source-opportunity-identity.md)
> (4c-slice-1).** Decided against the five existing sources before web search
> arrived: two-key dedup (ATS-native id for exact idempotency; a
> `canonical_fingerprint` match for cross-source collapse, but only when the
> incoming opportunity is non-authoritative, so two authoritative same-title
> reqs never over-merge) and a required `canonical_company` field each source
> computes (a domain where available, else a normalized token/slug). Two bounded,
> safe-direction gaps are recorded with revisit criteria: ATS sources have no
> domain (under-merge, not corruption) and a rare cross-source over-merge is
> accepted as the quality-over-volume trade-off.

> **Named gap: Career Page Finder + ATS Detector — resolved, gap accepted with
> reasoning, not by default.** The original scope named it explicitly; no
> 4a/4b/4c sub-slice built it, and the breakdown silently dropped it without a
> recorded decision — caught here rather than left implicit. Its original
> purpose was: given a company name with no other information, find its careers
> page and detect which ATS it runs, so it could be polled. But the six sources
> actually built collectively substitute for most of that practical value: the
> four ATS sources (Greenhouse/Lever/Ashby) cover any company on a known ATS
> directly, by config (board token), without ever needing to *discover* the
> page; YC covers YC-backed companies structurally; and
> `SearchOpportunitySource` (4c-slice-2) already does a narrower but real form
> of ATS detection — it recognizes known ATS URL patterns inside search results
> and confirms them against the real parser, i.e. detection triggered by a
> posting surfacing in search, not by a company name with no jobs yet found.
> For a personal, quality-over-volume job search that is very likely sufficient
> coverage of *currently open* jobs. What is genuinely left is a **different**
> capability — proactively finding and watching career pages for companies with
> **no currently-visible postings** — not unfinished discovery of open jobs.
> That is logged as its own future phase, **"Company Watchlist / Proactive
> Career Page Monitoring,"** in the deferred-work list at the bottom, rather
> than reopened as Phase 4 work.

## ✅ Phase 5 — Truthfulness gate: adversarial verification suite
Brought forward ahead of the JSON Resume master profile, deliberately. The gate
has been a **tracked, merge-blocking deliverable since Phase 2/3** — every
downstream design decision in this build (Phase 4c's `SearchOpportunitySource`
holding uncertain results, ADR-0013's held-candidate mechanism, ADR-0003 itself)
has deferred to it as the ultimate backstop, and it is the single most
safety-critical piece of the whole system. Phase 4's "Career Page Finder" gap
just demonstrated how a tracked item can silently survive multiple phases when
each individual phase looks complete on its own terms — the gate must not be
allowed to do the same. Built a real `MasterProfile` fixture and the concrete
`LLMTruthfulnessGate.verify()` implementation, validated against a
**reviewer-defined 12-case adversarial fabrication matrix** (same discipline
proven twice already: the HN held-candidate matrix, ADR-0013; the cross-source
dedup branches, ADR-0014) — the user drafted the adversarial cases, the agent
implemented against them, fixtures verified as genuine near-misses, not
strawmen. Recorded in **ADR-0016**: entailment-over-keyword-matching (catches
composite fabrication for the right reason, not by coincidence), the category
rubric, `summary` explicitly out of scope and coupled to Phase 8's
`ResumeGenerator` design, and — because this is the first safety-critical
component resting on model judgment rather than a structural guarantee — five
required compensating controls around the `ClaimVerifier` port: required
confidence with sub-threshold blocking, verifier-failure-is-an-explicit-block,
permanent cost-cascade exemption, documented temperature/variance limits, and a
**promptfoo suite as the hard merge gate** for the real implementation before
it may be wired into Phase 7's apply path.
**Done when:** the gate blocks every case in the matrix and passes every honest
rephrasing case in it, with real fixtures independently verified, not just a
passing test summary.

## ✅ Phase 6 — JSON Resume master profile
The structured master profile (JSON Resume schema) and its loader/validator —
built with the gate's real `verify()` already in hand, so the profile model
was validated against what the gate actually needs, not a scaffolding guess.
Recorded in **ADR-0017**: every `work`/`education`/`skills`/`projects` entry
must carry an explicit `id` (JSON Resume has none natively) — rejected as a
loud, actionable validation failure if missing or duplicated, never inferred
or silently written back, since only a deliberately-committed id honors the
"assigned once, never reused" guarantee `EvidenceRef` (ADR-0012) depends on.
`version` is a deterministic SHA-256 over exactly the fields `MasterProfile`
models, not the raw file — an unmodeled JSON Resume section (`awards`,
`publications`, `languages`, `interests`, `references`, `volunteer`,
structured `basics.location`/`basics.profiles`) changing must not falsely
bump `version` and invalidate every stored `EvidenceRef` pointing at facts
that didn't actually change; those sections are named as a tracked gap
(Career Page Finder pattern), not silently ignored. `load_master_profile` is
a plain function, not a `Protocol` — one real format, no second
implementation on the roadmap, so no speculative abstraction.
**Done when:** a validated profile loads and the grounding contract is
defined. ✅ 12 tests: valid-profile mapping, deterministic/scoped version
hashing, missing/duplicate id rejection (within and across sections), and
non-id validation errors surfaced from Pydantic unwrapped.

## 🔶 Phase 7 — ATS adapters (in progress: 7a merged)
Concrete ATS adapters registered as plugins for reading postings and (where
supported) submitting applications. This is the first phase that *acts* on
the real world rather than reads it, and is sub-sliced accordingly (Phase 4a
precedent: prove the safety machinery correct on one path before adding
breadth) — recorded in **ADR-0018**.

**7a — submission safety scaffolding, merged.** `SubmittableApplication`
(`domain/models.py`) makes submitting an unapproved resume type-level
impossible — a Pydantic validator that runs on every construction path, not
a designated-factory-only check, the same "impossible to construct
otherwise" discipline as `TailoredResumeDraft`/`TailoredResume` (ADR-0011).
`Applicator.apply()` is replaced by `prepare()`/`submit(preview,
confirmation)`: `HumanConfirmation` is a token bound to one exact
`SubmissionPreview`, not a boolean — a mismatched, unknown, or replayed
token is refused by `TieredApplicator` (`agents/apply/applicator.py`)
*before* the `ATSAdapter` is ever reached, tested by asserting the adapter's
call log stays empty, not just that an error came back. A fourth
import-linter contract mechanically forbids orchestration from importing
`AnthropicClaimVerifier` directly (verified to bite, same as the
`core.config` contract) — Phase 7 is built and tested 100%
`FakeClaimVerifier`-backed; the real verifier stays unwired until a live
promptfoo run passes. `FakeATSAdapter` fixtures model real ATS-side failure
(duplicate submission, rate limit, malformed payload) as a distinct outcome,
not just the happy path — consequence, not testability, is what's different
from Phase 4's version of offline-fixture-first discipline. This slice wraps
exactly one `ATSAdapter` (no tier fallback, no company/ATS-kind resolution
yet) — named, not silently dropped.

**7b1 — ATS-kind resolution + the cross-tier confirmation rule, merged.**
Recorded in **ADR-0019**. `domain/ats_urls.py` extracts the ADR-0015
pattern-match classifier (originally built for web search) into a shared,
dependency-free module; `TieredApplicator` now resolves which registered
`ATSAdapter` applies to an opportunity from its `source_url` via an injected
`OpportunityRepository` (Phase 4a's existing port — deliberately no new
`CompanyRepository`, YAGNI same as Phase 6's loader), raising
`NoApplicableAdapterError` explicitly when nothing applies. Decided and
fixed in the type's shape now, before Tier 2/3 exist to make it concrete: a
tier-fallback attempt is never an automatic retry under the original
`HumanConfirmation` — each tier attempt requires its own `prepare()` →
confirm → `submit()` cycle, since a fallback tier is a materially different
real-world action (different target, sometimes different content shape),
not a retried transport for the same one.

**7b3 — browser-tier session encryption + pause/resume, merged.** Recorded
in **ADR-0020**. `BrowserApplicator` (`agents/apply/browser_applicator.py`)
targets Greenhouse's public apply form only this slice (same Greenhouse-
first discipline as Phase 4a and ADR-0019) — generalizing to arbitrary
career pages is separate future work. Two new structural guarantees, both
the same weight as ADR-0018's: (1) `EncryptedSessionStore`
(`integrations/browser_session.py`) encrypts a persisted, reusable session
at rest with a key held in the OS keychain (`keyring`) — never together with
the ciphertext on disk — and **fails closed**: if the keychain backend is
unavailable, the session is not persisted at all, never silently written
unencrypted. (2) A mid-submission challenge (CAPTCHA/verification/login)
returns `HumanActionRequired` (a Phase 2 event type, unused until now) and
holds the live browser page open; `resume(pause_token, ack)` mirrors
`HumanConfirmation`'s token-binding shape but goes further — it re-verifies
the challenge is actually gone on the live page before touching it again,
never trusting the acknowledgment alone. Tested against a real, local
Chromium driven against an offline HTML fixture (`tests/fixtures/greenhouse/
apply_form.html`, loaded via `file://`) rather than Python-level fakes — a
materially stronger proof for browser behavior than fixtures alone, and the
load-bearing test asserts the fixture's own success marker never appears
when `resume()` is called with the challenge still visible, the browser-tier
analogue of ADR-0018's `adapter.calls == []` proof.

**7b4 — email tier, draft-only, merged.** Recorded in **ADR-0021**. A design
check corrected the pre-brief's own premise mid-flight: the Gmail tool
surface available in *this development session* has no send capability, but
that's a fact about this session's connector, not the shipped application —
so the real guarantee comes from `EmailDraftSink` (`core/interfaces.py`)
deliberately exposing **no `send` method at all**, pinned by a canary test
(verified to bite, same as ADR-0019's). `EmailApplicator.submit()` creates a
draft (same confirmation-token binding as Tier 1/2 — a mismatched/unknown/
replayed token never reaches `EmailDraftSink`) and always returns
`HumanActionRequired(reason="confirmation")`, never `ApplicationSubmitted` —
claiming a send that didn't happen would be the truthfulness gap ADR-0003
exists to prevent, relocated from resume content to the system's own claims
about its actions. `Application.status="paused_for_human"` is now documented
as meaning two structurally different things: a browser-tier pause is
temporary and resumable (`BrowserApplicator.resume()`); an email-tier pause
is permanent from this system's perspective (no `resume()` exists for this
tier at all). The real, OAuth-backed `GmailDraftSink` is explicitly **not
built this slice** — an OAuth token is the same credentials-risk category
ADR-0020 designed encryption for, and deserves its own dedicated review, not
a rider on this one. Recipient-address resolution and confirming a drafted
email was actually sent are named gaps; the latter is tied to the same
scheduled/autonomous-run trigger as ADR-0018's profile-staleness gap.

**Remaining:** the lower-priority remaining Tier 1 adapters (7b2); the real
`GmailDraftSink`; recipient-address resolution; generalizing
`BrowserApplicator` beyond Greenhouse's form shape. The profile-staleness
gap and the send-confirmation gap must both close before any
scheduled/autonomous apply run is built.
**Done when:** adapters plug in via the registry with no core changes, with tests.

## ✅ Phase 8 — Application engine
Resume Agent + Apply Agent: truthful tailoring through the cost cascade, the
fabrication gate (Phase 5) as a hard blocker, and the tiered/supervised applicator
(API → browser → email), with throttling and human-in-the-loop pauses. The
renderer **must** call `domain.rendering.resolve_work_dates` for every work
entry's dates — never re-derive them another way, never omit them (ADR-0016's
Case #6 correction: the generator can't write a date, but the resume still
has to show the real one). Sub-sliced (same discipline as Phase 7): 8a proves
generation + gating correct in isolation before 8b wires it to real
submission — recorded in **ADR-0022**.

**8a — ResumeGenerator + gate wiring, merged.** `summary` is sourced
read-only from `profile.basics.summary`, never LLM-drafted —
`DraftedTailoring` (`domain/models.py`) structurally has no `summary` field
at all, the same move as `TailoredWorkEntry` having no date fields
(ADR-0016's Case #6). A missing profile summary is a loud
`MissingSummaryError`, raised before the drafter is ever called — not a
structurally-derived fallback, which would be zero-invention but produce an
obviously templated, low-quality resume (a quality-over-volume failure, the
4c search-confidence problem's shape, not a truthfulness one).
`ContentDrafter` (the narrow LLM port, mirroring `ClaimVerifier`'s shape) is
**not** permanently cost-cascade-exempt like `ClaimVerifier` — a
false-approve on tailoring is recoverable via the independent gate, unlike a
false-approve on verification, so the exemption's actual justification
doesn't transfer. `LLMResumeGenerator` does no self-verification; the first
integration test feeds real generator output (not hand-authored fixtures)
into the real `LLMTruthfulnessGate` and proves an honest draft approves, a
hallucinated skill blocks structurally, and a hallucinated `source_entry_id`
blocks as `employer_mismatch` — the seam between two independently-built
components, proven, not assumed.

**8b — the resume-tailoring pipeline, merged.** Recorded in **ADR-0023**.
`ResumeTailoringPipeline` (`agents/resume/pipeline.py`) composes
`ResumeGenerator` → `TruthfulnessGate` into one on-demand call: a real
`Opportunity` + `MasterProfile` in, an audited `Application` out always, plus
a `SubmittableApplication` when approved. `Application.status` gains
`"rejected"` — deliberately distinct from `"failed"`, since a gate rejection
(a content problem, never reached a submission attempt) and a submission
failure (a real-world event, possibly worth a different tier) are different
events that would otherwise be forced to share one status word, requiring
every future consumer to re-derive the distinction from
`resume.truthfulness.approved`. `ResumeTailored`/`TruthfulnessRejected` —
defined since Phase 2, never emitted — finally fire, reuse over invention
again. **Deliberately stops before calling `Applicator`**, canary-checked
(the module imports neither `Applicator` nor `ATSAdapter`): actually
invoking a tier is a separate action requiring tier selection and a real
`HumanConfirmation`, and folding it in here would compound "first real
generation-to-submission wiring" with "first real confirmation flow against
real content" in one slice — the same sequencing discipline as 7a before
7b3. Confirmed on-demand only; the profile-staleness and send-confirmation
gaps stay correctly deferred.

**8c — real confirmation + single-tier submission wiring, merged.** Recorded
in **ADR-0024**. Closes the one remaining unexercised link in the entire
submission-safety chain: `cli.confirm_submission` is this project's first
real, executable source of a `HumanConfirmation` — reads a yes/no-shaped
answer from stdin (via an injected, fully-testable `input_fn`, no
monkeypatching needed), returns a confirmation only for an exact "y"/"yes,"
**no default-to-yes path** (verified: the guarantee was broken on purpose,
the test caught it, reverted). Deliberately built now rather than deferred
behind a port the way `AnthropicClaimVerifier`/the real `GmailDraftSink`
were — those deferrals were forced by being untestable live in this
sandbox; a local stdin/stdout prompt has no such constraint, so that
precedent doesn't transfer. `SubmissionPipeline` (`agents/apply/pipeline.py`)
composes any `Applicator` with any matching confirmation source
(`prepare()` → `confirm()` → `submit()` or a clean, non-error abort),
proven here against a real `TieredApplicator` — single-tier only, since
`TieredApplicator`/`BrowserApplicator`/`EmailApplicator` are three
independent `Applicator` implementations with nothing that chooses between
them (ADR-0010's "tier selection is internal" describes a component that
was never actually built). Multi-tier selection is real, confirmed,
deferred work, not assumed to exist.

**8d — the resume renderer, merged.** Recorded in **ADR-0025**. Closes the
gap 8c's own writeup surfaced: not just missing dates, but no renderer at
all — every real confirmation this project could perform showed only
`content.summary`, since `TailoredResume.rendered_text` had existed as a
documented "derived cache" since Phase 2 with nothing ever populating it.
`render_tailored_resume` (`domain/rendering.py`) is computed once, in
`ResumeTailoringPipeline` at resume-creation time — the one place
`draft.content` and `profile` are both already in scope — requiring **zero
changes to any `Applicator`**, whose `rendered_text or content.summary`
fallback was correctly designed from the start. Raises loudly
(`KeyError`) rather than silently dropping a work/project entry it can't
resolve: the renderer is a second, independent consumer of
`source_entry_id` references and must not assume the gate already ran —
verified to actually catch a regression (broke the raise into a silent
skip on purpose, confirmed the test failed, reverted). Tested with
adversarial-matrix weight, not routine-formatting weight: a realistic,
multi-entry profile render is asserted structurally complete (every work
entry, real dates, highlights, skills, projects all present), not just
"renders without crashing."

**8e — the real, runnable `career-agent apply` command, merged.** Recorded in
**ADR-0026**. The first slice where a real person can type a real command
against real data: `apply --profile <path> --opportunity-file <path>` loads a
real `MasterProfile` and `Opportunity` from disk, tailors and gates a real
resume with the real, Claude-backed generator and verifier, renders it, and
asks a real human to confirm it via `confirm_submission`. Stops there --
prints plainly that nothing was actually sent rather than pretending to
submit, since no real `ATSAdapter` exists yet. Opportunity input is a plain
`--opportunity-file` JSON handoff, not a lookup against a persistent store
that doesn't exist. The real `AnthropicClaimVerifier` is gated by a new,
positive check (`llm/promptfoo_gate.py::verify_promptfoo_results`) against an
actual promptfoo results artifact on disk, keyed to the exact prompt version
by filename -- not a flag typed from memory -- closing the gap where ADR-0016's
requirement was enforced only by written policy. `main()` now takes an
explicit `argv` (dependency-injection, same pattern as `input_fn`), fixing a
real regression a pre-existing scaffolding test caught. All three new
structural guarantees in this slice (the promptfoo gate's pass/fail check,
its ordering before real client construction, and the `argv` fix) were
verified by deliberately breaking each, confirming a test caught it, then
reverting.

**8f — applicant identity snapshot + real data into BrowserApplicator, merged.**
Recorded in **ADR-0027**. Investigating a real Tier 1 `ATSAdapter` (the
natural next step after 8e) found it isn't a real capability at all:
verified against Greenhouse's, Lever's, and Ashby's own API docs that
direct submission requires an employer-issued credential no generic
applicant tool can obtain -- confirmed across all three platforms, not a
Greenhouse-specific quirk. That makes `BrowserApplicator` (Tier 2, the same
public form a human uses, no company cooperation required) the only tier
that can carry real submission weight -- but checking it before proposing
how to generalize it past Greenhouse's one form found a sharper gap:
`_fill_form` filled the form with hardcoded placeholder strings
(`"Applicant"`, `"Name"`, `"applicant@example.com"`), never real applicant
data, undetected since 7b3 because that slice's own review was correctly
focused on pause/resume/session-encryption, not the identity fields
incidental to it. `Application` gains a required, frozen
`applicant: BasicsSection` snapshot, populated once in
`ResumeTailoringPipeline` alongside `profile_version` -- the same "was this
true when submitted" discipline preventing a profile edit between
`prepare()` and `submit()` from silently submitting mismatched identity and
content. `_fill_form` now reads real data, with a documented,
known-imprecise name-splitting heuristic (multi-part surnames, suffixes,
non-Western name orders named as real, deferred limitations, not silently
assumed correct). Both the required-field guarantee and the real-data fix
were verified by deliberately breaking each and confirming a test caught
it (the latter checked against a real, live Chromium page, not simulated).

**8g — browser-tier per-ATS dispatch + unsupported-field refusal, merged.**
Recorded in **ADR-0028**. Generalizes `BrowserApplicator`'s *dispatch* past
Greenhouse-only: which ATS's form to fill is resolved via
`resolve_ats_kind` (the same pattern-match ADR-0019 built for Tier 1),
dispatching to a per-`ats_kind` `FormFiller` (`form_fillers.py`, new).
Real Lever/Ashby form selectors could not be verified before building
them: two independent verification attempts, from two different vantage
points, both hit real walls -- this sandbox's Playwright cannot reach any
live internet host at all, and a separate attempt with real web access
could reach Lever's own documentation (confirming the form is genuinely
organization-configurable, and that its `apply` questions API requires
the same employer-issued credential that already killed Tier 1) but not
rendered page DOM. `LeverFormFiller`/`AshbyFormFiller` are therefore
explicit, registered stubs that raise a clear "not yet verified" error
rather than guess at selectors. Before ever clicking submit,
`BrowserApplicator` now also refuses (`UnsupportedFormFieldsError`) any
*required* form field the active `FormFiller` doesn't declare knowing how
to fill -- checked generically against the live page's real form
elements, not a fixed per-platform list, so it works the same way
regardless of which ATS's form is loaded; an optional unanswered field is
left alone. Verified against a real, live Chromium page with a second
fixture carrying one extra required field, and verified to actually bite
by deliberately breaking both the refusal check and the dispatch-failure
check and confirming each broke a test.

The custom-questions/EEOC-answering problem this generalization reopens
is explicitly **not** solved here -- named, deferred to its own dedicated
ADR, with one absolute stated now rather than left implicit: EEOC/
demographic self-identification fields must never be auto-filled or
guess-then-confirmed, only left blank (where the form permits) or
answered directly by a human with zero suggested default. This is a
different kind of guardrail than anything built so far in this project --
not "verify harder," but "don't build the capability at all, on
principle," because the field isn't asking for a fact to verify, it's
asking the person to exercise a legally protected choice about disclosure
itself.

**8h — per-FormFiller challenge/submit selectors + name-based field matching,
merged.** Recorded in **ADR-0029**. The user personally inspected a real,
live Lever posting via browser dev tools -- the one verification path
neither this codebase's sandbox nor any automated tool in this session
could reach (four independent attempts confirmed this: no live network
access at all, `WebFetch` 403s, readable-text-only extraction, and
Ashby's board turning out to be a client-side React SPA opaque to every
static tool). That real inspection found two load-bearing gaps 8g's
stub-only scope hadn't anticipated: Lever's identity fields have no `id`
attribute at all, only `name` -- `_unhandled_required_fields` only ever
built an `#id`-shaped selector and could never have matched a real Lever
field; and the posting used real hCaptcha markup that
`BrowserApplicator`'s hardcoded `#verification-challenge`/`#submit_app`
literals (Greenhouse's own fixture markers) would never have matched.
Both fixed: `_unhandled_required_fields` now derives a selector from
whichever attribute an element actually has (`#id` first, then
`[name='...']`); `FormFiller` gains declared
`challenge_selector`/`submit_selector` fields, read by
`BrowserApplicator` instead of hardcoded literals.
`GreenhouseFormFiller`'s own values became declared, not hardcoded, with
an explicit acceptance bar: the full pre-existing suite (ADR-0020's
CAPTCHA-pause tests, ADR-0027's real-name-fill test) had to pass
unchanged, proving pure generalization, not accidental behavior change to
the one platform that already works for real -- confirmed. New coverage
proves both mechanisms against a fixture deliberately shaped like the
real, confirmed Lever DOM, not just Greenhouse's own shape, and all four
new guarantees were verified by deliberate injection (two caught by
assertion failures, two caught by real Playwright `TimeoutError`s waiting
on selectors that don't exist on the alt fixture) before reverting.
`LeverFormFiller`/`AshbyFormFiller` deliberately stay stubs: the resume
field's real interaction shape (plain text vs. a JS-driven file-upload
widget) is still unconfirmed, and this project has no resume-file
artifact anywhere in its domain model -- selectors alone don't unblock a
still-open unknown.

**8i — Greenhouse coverage correction, recorded (no code change).** Recorded
in **ADR-0030**. The user personally inspected a real, live Greenhouse
posting -- the one platform this project had been treating as its fully
proven baseline. `resume_text` was upgraded from "documented in
Greenhouse's API, UI-unconfirmed" to **DOM-confirmed**: the real form has
an explicit "Enter manually" option alongside Attach/Dropbox/Google Drive
(the exact toggle interaction and revealed field's real selector remain
unconfirmed, so `GreenhouseFormFiller`'s current unconditional
`page.fill("#resume_text", ...)` is not yet proven correct against it).
More consequentially: the same ordinary posting (not an unusual one)
required Education, three legal work-authorization questions, a full
Voluntary Self-Identification section, and a Veteran Status section --
none of which `GreenhouseFormFiller` fills. `_unhandled_required_fields`
correctly refuses on all of them, exactly as designed -- **nothing is
broken.** But this corrects a real overstatement in this project's own
record: **"Tier 2 works for Greenhouse" has only ever meant "correctly
refuses most real postings, completing only the minority with minimal
custom fields," not "completes most real Greenhouse applications."**
The custom-questions/EEOC-answering design (deferred since 8g) is
re-prioritized accordingly: it is not a generalization nice-to-have, it is
the actual gate on this project's practical usefulness on the one
platform it already supports.

**8j — QuestionAnswerer: the four custom-question categories, merged.**
Recorded in **ADR-0031**. Builds the component 8i re-prioritized: EEOC
self-identification (an absolute -- `answer_eeoc_question` takes no
`MasterProfile` parameter at all, proven by a signature-inspection test,
not just runtime behavior), profile-groundable factual yes/no (routed
through a new, narrow `LegalStatusSection` on `MasterProfile` --
`work_authorized_us`/`requires_sponsorship`, `None` structurally meaning
"not yet captured," never a default "no," enforced by
`MissingLegalStatusFactError`), subjective/motivational freeform (no
`answer_subjective_question` function exists anywhere -- the no-LLM-drafting
guarantee is structural, not a runtime check), and structured-but-unmatchable
dropdowns (`match_dropdown_option`, deterministic Jaccard similarity, its
own `DropdownMatchResult` type kept distinct from `ClaimVerdict`, refuses
on both a low-confidence best match and a near-tie between two plausible
options). All four categories investigate deterministic template matching
over an LLM call -- and land there for all four, not just the two
originally expected, because EEOC and legal-status questions follow
OFCCP-standardized boilerplate wording widely enough to make templates
defensible; a real LLM-backed classifier stays a named, deferred
escalation. Built against a 20-case adversarial matrix the user drafted
personally (same discipline as the truthfulness gate's and HN's matrices),
with the four cases the user flagged as load-bearing -- 1d (no profile
lookup ever attempted for EEOC fields), 2b (negated-polarity questions),
3c (restating true profile content is still unapproved generation), and
4c (a close-but-wrong dropdown pick is worse than blank) -- each
independently verified by deliberately injecting the corresponding
violation, confirming the test caught it, then reverting. Named,
honestly-recorded limitation: Category 2 is scoped to `LegalStatusSection`
only this slice, so a profile-groundable-but-non-legal-status question
("years of Python experience") currently falls to the safe SUBJECTIVE
default rather than being properly classified. Deliberately **not** wired
into `BrowserApplicator.submit()`'s live DOM flow this slice -- proven in
isolation first, wiring is its own separate, deferred step, the same
sequencing 8c/8d used for `ResumeTailoringPipeline` before
`SubmissionPipeline`.

**8k — QuestionAnswerer wired into BrowserApplicator's live pause/resume
flow, merged.** Recorded in **ADR-0032**. `submit()` gains two sequential
pause phases: Phase A (pre-click, `reason="fields_need_human_input"`)
triages every required field `FormFiller` doesn't know via
`QuestionAnswerer.classify_question` -- a Category 2 field with an
already-captured `LegalStatusSection` fact auto-fills silently, everything
else unresolved batches into **one** pause, not one per field; Phase B
(post-click, `reason="verification"`) is ADR-0020's original CAPTCHA
pause, unchanged. Phase B is structurally unreachable until Phase A's own
`resume()` has re-verified its manifest and clicked submit -- sequential
by construction, not convention. The load-bearing design choice: `resume()`
reuses `PauseAcknowledgment`'s existing shape unchanged for both phases --
the human fills every manifested field **directly on the visible live
page**, never through a typed answer payload this code constructs and
writes into the DOM. That means an EEOC response never becomes a Python
value this process holds at any point, a categorically stronger guarantee
than "received it and used it correctly." Verified at the wiring level,
not just in isolation: a first injection attempt (auto-filling an
EEOC-classified dropdown via the same matcher Category 2 uses) was
correctly *not* caught, because `match_dropdown_option`'s own refusal
logic declined to map "Yes" onto gender options -- real defense-in-depth,
recorded rather than dismissed; a second, more direct injection
(force-selecting any option on an EEOC field, bypassing matching
entirely) was caught. `Application` gains `legal_status: LegalStatusSection`
-- ADR-0027's `applicant` frozen-snapshot precedent applied one field
wider, confirmed explicitly before implementation rather than assumed, so
`BrowserApplicator` still has zero dependency on `MasterProfile` storage,
recorded as a deliberate structural boundary. A captured legal-status
answer is not persisted back to the profile this slice -- no `MasterProfile`
writer exists anywhere in this codebase, named as separate future work
rather than built silently alongside this wiring. `_PausedSession`'s
`reason` discriminator was required to be provably load-bearing, not
decorative, before merge -- proven by a dedicated test constructing one
pause of each reason on the same live page, and by injection (forcing
`resume()` to ignore `paused.reason` broke exactly the tests expected).
Category 4 (dropdown auto-matching, e.g. Education) stays unwired this
slice -- it would need its own new frozen profile snapshot never decided
in the approved pre-brief, so those fields land in the manifest like
anything else unresolved, a safe degradation not a broken guarantee.

**Remaining (named, not blocking Phase 8's own criterion below):**
persisting a captured legal-status fact back to the profile (needs a
`MasterProfile` writer that doesn't exist yet); wiring Category 4 dropdown
auto-matching (needs its own new frozen profile snapshot decision);
widening Category 2 auto-fill past `<select>` elements if a real posting
renders a boolean question as radio buttons; confirming the exact
Greenhouse resume-field interaction sequence; real multi-tier selection
across the three `Applicator` implementations; resolving the resume-field
interaction shape and confirming Lever's selectors generalize across more
than one company before `LeverFormFiller` can move past a stub; Ashby's
DOM remains fully uninspectable by every tool tried so far; the real,
OAuth-backed `GmailDraftSink`. Tier 1 direct-API submission for arbitrary
companies is no longer on this list -- confirmed dead, not merely
deferred (ADR-0027).
**Done when:** an application can be assembled, gated for truthfulness, and
submitted under supervision, with real employment dates on every tailored
work entry. ✅

*The phases below were renumbered and expanded by the standing master brief
(post-8k): the original "Phase 9 Learning engine / Phase 10 Dashboard /
Phase 11 Deployment" plan is superseded by the concrete 9–18 sequence,
which absorbs all three (Learn → Phase 15, Dashboard → Phase 16,
scheduling/deployment → Phase 17).*

## 🔄 Phase 9 — Resume file generation (DOCX + PDF)
Recorded in **ADR-0033**. Real DOCX (python-docx) and text-based PDF
(LibreOffice headless) from gated `TailoredContent` + read-only profile
facts, per a locked ATS-safe layout spec. Education sourced read-only from
`MasterProfile` (authoritative Option (a) decision) -- structurally
impossible for generated content to carry, override, or fabricate. New
`ResumeArtifact` domain model: content-hash-addressed filenames make
silent overwrite impossible by construction; DOCX bytes are deterministic
(zip-timestamp normalization -- raw python-docx is not, verified
empirically); PDF is a derived, non-reproducible view whose absence
(missing `libreoffice-writer`, a real failure mode this sandbox exhibited)
is a typed error for direct callers and structurally visible in the
pipeline's artifact list. Injection pass found and fixed two real gaps:
the layout runtime check originally ran before content was added (moved to
pre-save), and the determinism test could pass by luck inside ZIP's
2-second timestamp granularity (sleep lengthened past the boundary).
**Done when:** an approved resume produces traceable, deterministic,
ATS-safe files a Playwright `set_input_files` call can attach.

## 🔄 Phase 10 — ATS score gate
Recorded in **ADR-0034**, built against the reviewer's 14-case adversarial
matrix (A1–D3; four flagged load-bearing: A1, B1, B3, C1 — all four
injection-verified). Deterministic curated-taxonomy scoring is the entire
pass/fail authority: the pre-brief rejected spaCy's statistical model
because artifact-dependent determinism is not determinism (same input must
score identically on any machine, forever — D1/D2 demand exact boundary
behavior), and resolved the brief's "raise but never lower" semantic-layer
wording in favor of the matrix's stricter A1 (self-contradictory the
moment a raise crosses the threshold). `passed` is computed in the report
type itself — threshold comparison plus the A2 hard-format-failure
override live in the type's derivation, not caller discipline. The
advisory semantic layer only prunes false-missing keywords from the
retailor gap report, each pruning verbatim-verified against the resume
text (A3), and is deliberately NOT cost-cascade-exempt — it gates
nothing; the exemption protects judgments that gate (reasoning recorded
in the ADR, not just the decision). The retailor loop's backbone:
GENUINE skill gaps (zero profile evidence) are structurally unreachable
by the drafter — `AtsGapReport` has exactly one content field
(`surfaceable`), so auto-retailor cannot become auto-fabricate because
the fabrication targets are withheld from the component that writes
prose (B1, the `answer_eeoc_question` channel-restriction pattern applied
to a new risk category); the full truthfulness gate runs before every
re-score, so a high ATS number never exists for an unapproved draft (B3);
identical-retry convergence stops early and says so (B5); exhaustion
raises a typed refusal carrying the score trajectory and the honest
GENUINE-vs-surfaceable split (B4). One render per accepted draft, proven
by an `is`-identity test: the scorer and the human preview consume the
literal same string. Anti-stuffing: repetition beyond 3 earns nothing and
flags; skills-list-only matches earn half credit and flag (C1/C2).

## 🔄 Phase 11 — LeverFormFiller (real)
Recorded in **ADR-0035**. Built from ADR-0029's recorded live-DOM evidence:
single unsplit full-name field (`_split_name`'s known imprecision never
applies on Lever), `[name='email']`, required file upload satisfied by
attaching the application's own ADR-0033 DOCX artifact via
`set_input_files` -- the attach proven against the live input's real
FileList (injection-verified against a wrong-file swap), typed
`MissingResumeArtifactError` when no artifact exists or the file is gone
from disk (Lever has no manual-text path; nothing to upload means no
honest submission), hCaptcha (`#h-captcha`) through ADR-0020's
pause/resume machinery unchanged. Live validation against a real posting
on the user's machine remains the named final check before first real
use.

## 🔄 Phase 12 — Worldwide + regional discovery expansion
Recorded in **ADR-0036**. Eight Tier A free APIs built as
`OpportunitySource` plugins behind the unchanged Protocol (Adzuna incl.
India, Reed UK via Basic auth, USAJobs header-auth, Arbeitnow, The Muse,
Remotive, RemoteOK with its attribution obligation carried structurally
in provenance, Jooble POST with the key never recorded into stored data
-- injection-verified). `HttpClient.get_json` gained additive `headers`
(the post_json 4c-slice-2 precedent) for the two header-authenticated
APIs. Tier B (JSearch) evaluated and not built (paid, overlaps Adzuna);
Tier C (Naukri/Foundit/LinkedIn/Indeed/Seek) recorded as manual-only --
no permitted programmatic path exists, no scrapers ever (invariant 7);
they work today through the source-agnostic opportunity-file handoff.

## 🔄 Phase 13 — Persistence + discover command + Excel
Recorded in **ADR-0037**. `SqliteOpportunityRepository` -- exact-contract
drop-in (same public-surface guard, same two-key dedup scenarios, plus
real close/reopen round-trip). Append-only `SqliteApplicationStore` audit
trail recorded from `apply` (with the real final ATS score via
`ResumeTailoringResult.ats_report`, additive). Real `career-agent
discover`: config-wired Tier A sources, per-source failure isolation,
writes the exact ADR-0026 opportunity-file handoff. First `MasterProfile`
writer: `capture-legal-status` accepts exactly yes/no/skip -- unrecognized
input can never become an answer in either polarity (injection-verified),
unmodeled JSON Resume sections survive byte-identical, frozen snapshots
on existing Applications never rewritten. `career-agent export`: the
founding-brief openpyxl tracker (formatted, filterable).

## 🔄 Phase 14 — Decide layer
Recorded in **ADR-0038**. `DeterministicDecideScorer` inside the Planner
boundary (ADR-0007's swappable step, first real implementation): profile
match 50% via Phase 10's unforked keyword machinery (one vocabulary across
Decide and the ATS gate), source reliability 20%, freshness 20%
(unknown-date neutral 50), salary-transparency bonus 10% (presence check,
never a parsed number -- floor filter named absent, no structured salary
field exists). Config filters are hard excludes with named reasons,
injection-verified against penalty-conversion; exclusions returned
visibly (ADR-0013 discipline); ties break by id. `discover --profile`
prints the ranked summary. Zero LLM calls.

## 🔄 Phase 15 — Learn pillar
Recorded in **ADR-0039**. `career-agent outcome` (typed kinds only,
refuses unknown application ids -- no orphan rows) + `career-agent
report`: per-variant funnels keyed to prompt/profile/ATS band, reading
the FULL outcome history (an application counts at every stage reached;
rejection stages are separated facts -- post-interview != at-screen).
Raw counts only at personal N: no significance testing, no bandit
routing, mandatory small-sample caveat on every report
(injection-verified) and a tested absence of prescriptive verdict
language. MIN_N_FOR_COMPARISON=50 recorded as visible data.

## 🔄 Phase 16 — Notifications + dashboard
Recorded in **ADR-0040**. Telegram Bot API notifier (token never logged,
never stored, elided from error text -- tested) with ntfy.sh as the
zero-setup fallback, both through the existing HttpClient port;
NotifyingSubscriber turns HumanActionRequired/ApplicationFailed/
OutcomeRecorded bus events into pushes under the notify-never-gate rule
(injection-verified: a propagating delivery failure was caught). Local
read-only Streamlit dashboard (optional extra): pure, tested
dashboard_metrics -- discovery by source, truthfulness pass/block, ATS
distribution, the ADR-0039 funnel with its caveat intact; SQLite read
directly as a separate read model so the repository contract stays
add/get.

## ✅ Phase 17 — Scheduling (LAST, hard-gated)
Recorded in **ADR-0041**. Both recorded gates closed first:
profile-staleness re-verification (`StaleProfileError` before `prepare()`
ever runs -- a stale application never produces a confirmable preview;
injection-verified) and email send-confirmation (`SentMailChecker` port
with no send capability + `confirm_email_sent`: positive SENT observation
only, couldn't-check is a typed unknown, never a boolean; the real OAuth
Gmail checker stays user-validated live work). Scheduling itself is
`career-agent auto`: one bounded, cron-invokable pass (discover -> rank
-> tailor+gate -> record -> notify) that **structurally cannot confirm or
submit** -- no input function, no HumanConfirmation, no Applicator in its
code, asserted at the co_names level. Confirmation and submission remain
human-gated forever (ADR-0008) -- a permanent boundary, not a current
limitation. Deferred: multi-tier selection; real OAuth GmailDraftSink +
SentMailChecker (live, user-present).

**Post-merge correction (found in a repository reality audit after PR
#40):** `run_auto_command` was built and tested as a Python function this
phase, but `main()` never actually registered an `auto` subparser -- this
roadmap claimed "Scheduling itself is `career-agent auto`" while a real
user typing that command got `argparse: invalid choice`. Fixed: `auto` is
now a real subcommand (`run_auto_cli_command`, mirroring `apply`'s
gate-then-construct ordering: real `ClaimVerifier` selected, its
promptfoo results positively verified, then the content drafter selected,
all before the structurally-submission-incapable `run_auto_command` body
ever runs), plus this project's first offline end-to-end rehearsal test
(`tests/test_cli_auto.py`) proving discover -> dedup -> rank -> tailor ->
truthfulness-gate -> notify compose for real through the actual CLI
entry point, not just in per-phase isolation.

## ⬜ Phase 18 — Ashby (whenever unblocked)
Blocked on the user's dev-tools DOM inspection of a live Ashby posting --
a client-rendered SPA invisible to every tool tried. Build nothing on
assumption.

---

## Research track (evidence-driven, not scheduled ahead of need)

A separate track from the numbered phases above: algorithmic/mathematical
improvements to existing components, pursued only where this project's own
repository evidence shows a real gap, not because a technique sounds
sophisticated. Each item gets its own audit before implementation; most stay
proposed until a concrete trigger justifies the work.

- **R1 — Formal claim-evidence entailment.** ✅ First slice done: **ADR-0044**
  (deterministic Layer-1 precheck: technology/metric/verb-strength/seniority,
  closed-vocabulary, zero-cost, no NLP model). Object/scope/causal-relation
  predicates deliberately deferred to the LLM (Layer 4) -- revisit only if
  real tailoring runs show that gap causing missed fabrications at scale.
- **R2 -- Hybrid retrieval/ranking for discovery.** Proposed, not started --
  no evidence yet that polling-based discovery is missing relevant postings
  at this project's actual (single-user) scale.
- **R3 -- Graph-based deduplication.** Proposed, not started --
  `domain/identity.py`'s exact-key + fingerprint approach has shown no
  observed false-duplicate or missed-duplicate failures yet.
- **R4 -- Multi-objective decision engine.** ✅ **ADR-0045** (`domain/pareto.py`
  + `agents/planner/sensitivity.py`: nominal + confidence-interval-robust
  Pareto dominance/frontier over Decide's existing four objectives, plus
  closed-form adjacent-pair weight-flip sensitivity) + **ADR-0046** (Phase 20:
  wired into `discover`'s existing ranked-summary output as read-only
  advisory annotations -- Pareto-frontier/dominance markers computed over the
  full included set, a bounded #1-vs-#2 sensitivity summary, an explicit
  heuristic-not-calibrated evidence-quality caveat). Decide's weighted-sum
  ranking and `auto`'s scalar-order selection remain structurally
  untouched and authoritative -- this item's own trigger ("if soft-score
  trading against hard constraints ever becomes an observed problem")
  remains unmet, so full constrained-optimization/epsilon-constraint/
  lexicographic methods, and wiring this analysis into `auto`'s actual
  selection, both remain future work gated on that same still-unobserved
  trigger. **ADR-0047** (Phase 21) validated, not extended, this system:
  proved (algebraically and by an exhaustive 390,625-pair finite-grid
  search, zero counterexamples) that under the current architecture the
  scalar winner can never be Pareto-dominated -- all four weights are
  strictly positive and the Pareto comparison uses exactly the objectives
  `S` sums over, so dominance always implies a strictly higher scalar
  score. The evidence gate re-checked every adjacent candidate algorithm
  (portfolio, Bayesian uncertainty, Monte Carlo/Sobol sensitivity,
  bandits, learned ranking): none justified by this phase's findings.
- **R5 -- Application portfolio optimization.** Proposed, not started -- no
  current daily/weekly application-budget constraint exists to optimize
  against.
- **R6 -- Uncertainty calibration.** Partially addressed already: the Learn
  pillar (ADR-0039) shows raw counts with an explicit small-sample caveat
  rather than false-precision statistics. A Bayesian/shrinkage model is
  future work if/when N grows enough to matter.
- **R7 -- Ghost-job risk modeling.** Proposed, not started -- no ghost-job
  signal exists in this codebase today.
- **R8 -- Learning/bandits.** Explicitly NOT started, on the Learn pillar's
  own recorded reasoning (ADR-0039): no bandit routing until N is sufficient
  for it to mean anything.

Ranked by evidence-based priority, not sophistication -- see the research
audit in this project's session history (2026-07-06) for the full inventory,
gap analysis, and Groq truthfulness audit that produced this list.

---

## Production reliability track (Phase 22, evidence-gated)

A repository-reality audit for production reliability/recovery/
resumability/observability found this project's actual architecture is
single-process, single-user, at-most-once (the event bus, `core/bus.py`,
says so explicitly), with no retry/backoff, checkpoint, transaction, or
observability-framework concept anywhere -- and none of that is missing by
oversight: no evidence in this repository (its real scale is "tens of
applications, not thousands," ADR-0039) justifies adding any of it yet.

- ✅ **Application-attempt idempotency guard -- ADR-0048.** The one concrete,
  safety-relevant gap the audit found: nothing previously stopped
  `career-agent apply`/`auto` from tailoring and (with two separate human
  confirmations) submitting to the same opportunity twice across separate
  invocations -- opportunity-level dedup (ADR-0014) never covered the
  application-*attempt* layer, and `Application.id` is a fresh UUID every
  pipeline run. `SqliteApplicationStore.prior_attempt_status()` plus a
  refuse-outright guard in both commands closes this, skipping only
  `"rejected"` (no-side-effect) priors, never auto-retrying.
- **Formal execution state machine, automatic retry/backoff, a checkpoint/
  resumability journal, a `SUBMISSION_UNCERTAIN` ambiguous state, a new
  observability framework.** All explicitly evaluated and NOT built this
  phase -- see ADR-0048's "What was deliberately not built" section for the
  evidence behind each. Revisit only if a concrete, observed failure mode
  (not a hypothetical one) shows one of these is actually needed.
- ✅ **Append-only execution journal -- ADR-0049 (Phase 23).** Central
  finding: an irreversible external submission -- the one risk Phase 23's
  brief centrally worried about -- is structurally unreachable from any
  composition-root command today (`TieredApplicator`/`BrowserApplicator`/
  `EmailApplicator`/`SubmissionPipeline` are never imported by `cli.py`).
  A minimal, append-only `SqliteRunJournal` gives `apply`/`auto` a stable
  per-invocation `run_id` and reconstructable stage history (for
  auditability/crash-forensics, not as a safety gate), composed with
  ADR-0048's still-active guard. A recovery planner, a validated
  transition-gated state machine, and a `SUBMISSION_UNCERTAIN` state were
  explicitly NOT built -- nothing reachable today is unsafe to simply
  re-run from the start. **Named, deferred trigger:** before any real
  `Applicator` is ever wired into a live `cli.py` command, this journal
  must be extended with `EXTERNAL_ACTION_*` states and a deterministic
  recovery planner enforcing "uncertain effect ⇒ never auto-replay" --
  tracked explicitly, not built speculatively now.
- ✅ **Execution-safety boundary -- ADR-0050 (Phase 24).** Builds the exact
  prerequisite ADR-0049 deferred: a pure, deterministic, fail-closed
  execution-permission boundary (`domain/execution.py`) with a four-way
  `SubmissionOutcome` (incl. `OUTCOME_UNCERTAIN`, never collapsed into
  failure), a retry rule where uncertain/submitted priors are never
  auto-retryable, deterministic source-policy resolution (no source maps
  to `AUTOMATED` -- ADR-0027 killed every fully-automated path), and a
  reference confirmed-artifact digest. The whole 256-combination input
  space is exhaustively enumerated (`research/execution_safety.py`) with
  zero invariant/metamorphic counterexamples. Wired live into `apply`
  after confirmation with `executor_available=False`, so it always refuses
  with an explicit journaled reason -- **no executor is wired and no
  external submission is newly reachable** (browser=no-exception-means-
  success, email=draft-only, direct-API=dead: none safe to wire). **Named,
  deferred trigger:** the eventual executor-wiring phase must add a
  write-ahead `EXECUTION_INTENT` event and a real, provider-specific
  acknowledgement classifier feeding this boundary's `prior_outcome`, and
  flip `executor_available` per source only when a deterministic ack model
  exists -- specified in ADR-0050, not built speculatively now.

---

## Product usability track (Phase 25, competitive-audit-driven)

A cross-repository audit against MIT-licensed
[`MadsLorentzen/ai-job-search`](https://github.com/MadsLorentzen/ai-job-search)
(a Claude-Code markdown/skills workspace, pinned at commit `79b1537`)
found our architecture materially stronger on rigor and safety (their
fit-scoring and truthfulness protection are prompt-only; their apply flow
is an unenforced LLM reviewer loop), but weaker on **time-to-first-useful-
result**. The verified top gap: we had no onboarding command, so a new
user had to reverse-engineer the JSON Resume schema and hand-author a
profile.

- ✅ **Guided `setup` command -- ADR-0051 (Phase 25).** A deterministic,
  fully-offline `career-agent setup`: scaffolds a schema-correct starter
  profile iff none exists (never overwrites a real one), prints an offline
  readiness report (profile loads? provider key present -- value never
  printed? Promptfoo artifact present?), and names the single next
  command. Zero LLM/network/cost; touches no safety gate.
- **Deferred (evidence-backed, but not this phase):** LLM-based CV
  extraction (must write extracted facts as an editable *unverified* draft,
  never verified evidence); a drafter/reviewer revision loop (safe only if
  every revision re-passes the truthfulness + ATS gates -- the reference's
  reviewer can introduce unsupported claims with only a prompt instruction
  as its guard); an interview-prep pack (LLM-dependent). Each is named for
  a future phase, not built speculatively now.
- ✅ **Evidence-grounded CV ingestion -- ADR-0052 (Phase 26).** Closes the
  "CV extraction must land as an *unverified* draft" half of the deferred
  item above, deterministically (no LLM). `career-agent import-cv` parses a
  DOCX/TXT CV into UNVERIFIED, source-bound `FactProposal`s (email, phone,
  URLs, a labelled name heuristic, an explicit "Skills:" line -- nothing
  inferred) and writes a draft that never touches the profile.
  `career-agent promote-cv` promotes only proposals a human marked
  `confirmed`, through a fail-closed boundary (`domain/ingestion.py`,
  108-point space exhaustively verified) requiring a content-bound
  confirmation, evidence re-validated against the re-read source
  (source-drift refused), no unresolved conflict, and no silent overwrite
  of a different verified value. Zero new dependency (DOCX via the declared
  `python-docx`); MasterProfile/truthfulness gate/prompt-version/Promptfoo
  all unchanged; injection text in a CV is inert data. **Deferred:** PDF/OCR
  ingestion (no declared PDF reader -- named limitation) and LLM-assisted
  proposal extraction (must still pass this same promotion boundary).
- ✅ **Truthfulness-re-gated revision loop -- ADR-0053 (Phase 27).** The
  audit found this loop **already exists and is used** (ADR-0034's
  `_ats_gate_loop`: retailor up to 2×, full truthfulness gate before any
  ATS re-scoring, convergence, fail-closed refusal, SURFACEABLE-only gap
  report). **Decision: Option A** -- build no LLM reviewer/reviser
  subsystem (it would duplicate the loop, add a prompt-injection surface
  and LLM cost, and any reviser output is re-gated anyway). Phase 27
  formalizes the authority model (truthfulness rejection is absolute; ATS/
  "reviewer" advice is advisory + SURFACEABLE-only; skills are structural)
  and pins the composition invariants: the gate never receives the JD (I9),
  no verification cache (I3), `agents/resume` never imports Phase 26
  ingestion (I10/I11), and an injection JD that makes the drafter add an
  unsupported skill yields a rejected application. No production code, no
  prompt-version bump, no new dependency. **Deferred (Phase 28 candidate):**
  a *deterministic* typed advisory reviewer (never a free-form LLM one),
  only if real usage shows the ATS-driven retailor leaves an observed
  quality gap.
- ✅ **Production-readiness release gate -- ADR-0054 (Phase 28).**
  Validation phase. **Decision: Option A** (tests + ADR, no production
  code): the architecture already satisfies the requirement, so a
  `doctor` command was rejected as a duplicate of `setup`'s readiness
  report. Documents the reconstructed end-to-end state machine (external
  submission and outcome-unknown/recovery states are **unreachable** -- no
  executor is wired), a capability matrix, a fail-closed failure matrix,
  and the I1-I22 release-invariant contract. Adds a composed end-to-end
  dry-run (setup → import-cv → promote-cv → auto → prepared, +
  restart-idempotency + UTF-8 survival with a synthetic Aarav-Rao fixture)
  and a cross-cutting contract test (no submission reachable from the CLI,
  Promptfoo gate enforced offline, network guard active). **Finding:**
  release-ready as a supervised **prepare-only** product; no irreversible
  external action exists today. **Recommended Phase 29:** a user-run
  manual live smoke-test harness (real Groq validation, one real tailored
  resume), outside the automated suite, still stopping at prepared.
- ✅ **Bounded real-provider release policy -- ADR-0055 (Phase 29).**
  Audited the real LLM path (exact models: verifier `openai/gpt-oss-120b`
  Promptfoo-gated / `claude-opus-4-8`; drafter `llama-3.3-70b-versatile` /
  `claude-opus-4-8`; matcher `llama-3.3-70b-versatile` /
  `claude-haiku-4-5-20251001`; Groq-preferred) and bounded its cost/calls
  (`_MAX_ATS_RETRIES=2`, Layer-1 precheck resolves clear claims with zero
  calls, reasoning capped). **This environment has no key/artifact, so a
  live run is BLOCKED_BY_CONFIGURATION -- not performed, not faked.**
  **Decision: Option A** -- no smoke harness (`apply` already is the
  bounded prepare-only path); adds drift-guard tests (exact model-id pins,
  token/retry bounds, empty/whitespace-key edges, verifier-only Promptfoo
  scope) and documents the user-run controlled-smoke procedure + evidence-
  invalidation triggers. **Release decision: RELEASE_READY_WITH_
  LIMITATIONS** -- safety proven offline; real-output quality + live
  integration require the user's own local smoke run. **Recommended Phase
  30:** the user runs that controlled smoke locally and records the
  claim-ledger + quality verdict (safety failure = any unsupported claim
  surviving the gates, judged separately from quality).
- ✅ **Controlled live-smoke validation -- Phase 30 (under ADR-0055).**
  Re-audited fresh: models unchanged (no drift), provider path bounded.
  **This environment still has no key/artifact/opt-in, so the live smoke is
  BLOCKED_BY_CONFIGURATION -- not performed, not faked.** **Decision: Option
  A** (no production code, no new ADR -- ADR-0055 already defines the
  live-smoke policy). Adds the deterministic *safety half* of the smoke as a
  permanent regression (`test_phase30_offline_smoke_rehearsal.py`): the
  composed pipeline against the synthetic Aarav-Rao candidate and an
  adversarial JD (inert injection: "led a team of 20 engineers... 8 years of
  Kubernetes experience") proves the full claim ledger is caught -- Senior
  title → `unsupported_seniority`, "led 20 engineers" → `metric_unsupported`,
  Kubernetes skill → `skill_not_found` (all **deterministic Layer-1/
  structural, no model call**), "8 years..." → verifier -- with **zero
  unsupported claim surviving** and nothing submitted. **Release decision:
  BLOCKED_BY_CONFIGURATION** for the live half; the safety half is proven
  offline, real-output *quality* still needs the user's local run. **Next:**
  the user performs the local live smoke (real Groq + Promptfoo PASS) and
  records the quality rubric + any live claim-ledger findings.

- ✅ **Final v1.0 release audit -- ADR-0056 (Phase 34).** Fresh reality audit
  (the brief's "Phase 33/Phase 31/ADR-0059" do **not** exist; real state is the
  Phase 30 merge `46d267a`, highest ADR 0055, baseline **667 passed/0 skipped/0
  failed**, ruff clean, imports 4/4, clean-install + `--help` + `setup` smoke
  pass). Re-proved the safety architecture intact and external submission
  **UNREACHABLE**. One release-blocking gap: the README **overclaimed** (said it
  "submits", was "scaffolding only / not yet runnable", Anthropic-only cascade).
  **Decision: Option B** (docs + release artifacts + drift-guard tests, no
  production code). Rewrote the README truthfully; added `SECURITY.md`,
  `RELEASE_CHECKLIST.md`, `docs/release/v1.0.0-rc1-notes.md` (capability matrix +
  known limitations), `test_phase34_release_audit.py`; bumped version `0.1.0 →
  1.0.0rc1`. **Release decision: CONDITIONAL_GO** for v1.0.0-rc1 supervised
  prepare-only -- no critical invariant violated; conditions are live-output
  quality unvalidated, live Promptfoo BLOCKED_BY_CONFIGURATION, no in-repo CI,
  and Windows/macOS execution untested. No safety semantics changed.

- ✅ **CI and cross-platform release hardening -- ADR-0057 (Phase 35).** Fresh
  audit reconfirmed the one gap Phase 34 named: no `.github/` directory, no CI.
  Baseline unchanged: **672 passed/0 skipped/0 failed**, ruff clean, imports
  4/4. Adds `.github/workflows/ci.yml` -- matrix `ubuntu-latest`x`windows-
  latest`, Python 3.11, `permissions: contents: read`, no secret ever
  referenced (structurally cannot make a live/paid LLM call), no
  `continue-on-error` -- running lint, architecture contracts, the full test
  suite, a real `python -m build`, a wheel+sdist content check, and a
  clean-venv install + CLI smoke on **every push/PR**. Adds two dependency-free
  release-tooling scripts: `scripts/verify_release_artifacts.py` (checks wheel
  **and** sdist; fixed two false positives while building it -- `.env.example`
  is a safe template, and `tests/` legitimately belongs in the sdist, only
  forbidden in the wheel) and `scripts/smoke_test_wheel.py` (one OS-branch-free
  script proving install+`--help`+`setup` identically on both OSes, rather than
  duplicated conditional YAML). Amends ADR-0056's platform table from *static
  reasoning* to *evidence*: Windows is now actually exercised in CI, not
  inferred from explicit-UTF-8 alone; macOS stays a named, deliberate gap
  (10x runner-cost multiplier, no evidence of a macOS-specific defect).
  `tests/test_phase35_ci_release_tooling.py` (6 tests) pins the scripts' pure
  logic and the workflow's fail-closed shape. No production code, no safety
  semantics changed, no external submission newly reachable.

- ✅ **Controlled live Groq validation and a real declined-confirmation
  defect fix -- ADR-0058 (Phase 36).** The user ran the first genuinely live
  Groq smoke on their real Windows machine (real `GROQ_API_KEY`, real
  `verify-promptfoo --provider groq` PASS): the pipeline tailored, gated,
  ATS-scored (**78.125**), and rendered a real DOCX from real Groq output.
  Declining the confirmation prompt (`N`) exposed a real defect: the
  application-store row was written `status="pending"` **before**
  confirmation and never corrected afterward, so a declined run permanently
  refused every future retry with a message wrongly asserting real-world-
  submission risk. Reproduced deterministically offline first (no live call
  needed) with a failing regression test, then fixed with the smallest safe
  change: `Application.status` gains `"declined"` (means "zero external
  side effect," same as `"rejected"`); `_apply_pipeline` now records once
  per run, at the correct terminal branch; `prior_attempt_status()` excludes
  `"declined"` alongside `"rejected"`. Genuinely risky statuses remain fully
  blocking (proven by a dedicated test); external submission remains
  **UNREACHABLE**; no schema migration; 4 new tests. **Release evidence:**
  the real-provider path, truthfulness gate, ATS gate, and injection
  containment all held under a real live model call -- see ADR-0058 for the
  full defect writeup and PR #58 for the fix.

- ✅ **v1.0.0 release promotion -- ADR-0059 (Phase 37).** Fresh audit
  confirmed `origin/main` at `833c5db` (real PR #58 merge) and independently
  checked the GitHub Actions API directly -- both `verify (ubuntu-latest)`
  and `verify (windows-latest)` on that exact commit are `completed`/
  `success`, resolving Phase 36's unconfirmed-CI gap with a real result.
  Local baseline reconfirmed: **682 passed/0 skipped/0 failed**, ruff clean,
  imports 4/4. Re-inspected the maintainer's real Phase 36 live-Groq
  transcript directly: no injection-derived claim appears anywhere in the
  real rendered resume; ATS `78.125` and `truthfulness_approved=1` are real
  values, not asserted. **Decision: GO** -- all four of ADR-0056's
  `CONDITIONAL_GO` conditions are now closed by real evidence; macOS remains
  a named, deliberate gap, not a blocker. Promotes version `1.0.0rc1 →
  1.0.0`; adds `docs/release/v1.0.0-notes.md` (rc1 notes kept, unedited,
  marked superseded); adds `tests/test_phase37_v1_release_promotion.py`. No
  production code changed; no safety semantics changed; no git tag created;
  nothing published -- both left for the maintainer.

- ✅ **Promptfoo runtime path portability -- ADR-0060 (Phase 40).** Fixed
  the v1.1-backlog P1 Phase 39 found: the Promptfoo results-directory
  default was `__file__`/install-tree-relative, only correct for an
  editable install -- reproduced live (a fresh wheel install, run from
  outside the repo, reported the broken path before the fix). Fixed by
  consistency, not new design: `Settings` gains `promptfoo_results_dir`
  (CWD-relative, `.env`-overridable), mirroring `database_path`/
  `artifacts_dir` exactly; `_REPO_ROOT`/`_DEFAULT_PROMPTFOO_RESULTS_DIR`
  deleted; every command (`setup`/`apply`/`auto`/`verify-promptfoo`/
  `diagnose-promptfoo-drift`) now resolves from the same field. Records a
  durable policy (ADR-0060): no future runtime path may be `__file__`/
  install-tree-relative. 6 new tests; re-verified live on both an editable
  install and a fresh wheel install from outside the repo. No Promptfoo
  gate semantics changed, no new dependency, no external submission
  newly reachable.

- ✅ **Installed-package and distribution hardening -- ADR-0061 (Phase 41).**
  Built a fresh sdist and found a real leak: `.claude/` (this agent's own
  local session state) and `.import_linter_cache/` -- both untracked but
  not `.gitignore`d -- appeared as top-level sdist entries (hatchling's
  default sdist packaging includes anything not explicitly `.gitignore`d).
  Fixed by adding both to `.gitignore` and, durably, by adding a
  **positive top-level allowlist** to `scripts/verify_release_artifacts.py`
  -- a suffix/fragment blocklist can never catch an unanticipated
  directory. Also fixed two stale metadata facts: the `Development Status`
  classifier (`2 - Pre-Alpha` -> `5 - Production/Stable`, matching the
  actual tagged v1.0.0 state) and `requirements.txt`'s comment (abandoned
  "Haiku->Sonnet->Opus cascade" -> actual Groq-preferred policy). Confirmed
  live: fresh wheel **and** sdist installs, each in an independent clean
  venv, run from outside the repo -- `--help`/`setup`/`verify-promptfoo`/
  import/metadata all correct; distribution name (`career-agent`) confirmed
  distinct from repo name and import package name. 5 new tests. No safety
  semantics changed, no dependency version changed, no new CI platform
  (wheel-install already exercised on both Ubuntu and Windows, confirmed
  from existing green CI).

- ✅ **Fresh-machine onboarding validation (Phase 42).** Revalidated the
  whole zero-to-first-run path against freshly built, independently
  installed artifacts: editable + wheel installs (run from outside the
  source tree, source-tree independent), the `setup` readiness state matrix
  (no-key / key-present / no-artifact / artifact-present, key value never
  printed), profile onboarding through the real `load_master_profile`
  (camelCase mapping, not raw `model_validate`), and apply-journey safety
  on synthetic `.invalid` domains (fail-closed at every gate; no real
  submission reachable). One doc-accuracy defect found and fixed: the README
  falsely framed its example as the literal scaffold output. 3 new tests. No
  production/dependency/safety/ADR change.

- ✅ **v1.1 production-readiness audit + version decision -- ADR-0062
  (Phase 43).** Audited eight categories against directly-observed
  evidence and decided the release version by SemVer reasoning. The only
  runtime change since the `v1.0.0` tag is the new `promptfoo_results_dir`
  `Settings` field (backward-compatible functionality); no LLM-facing code
  changed. **Decision:** target **v1.1.0** (MINOR); release gate
  **CONDITIONAL_GO**, pending Phase 44 mechanics (version bump in lockstep
  with the three v1.0.0 drift-guard tests + release notes + fresh green CI)
  and owner authorization for the tag. No P0/P1 blocker; `v1.0.0` tag
  immutable. Records the decision only -- no version bump, no tag.

- ✅ **v1.1.0 release promotion (Phase 44, ADR-0062).** Executed the
  CONDITIONAL_GO conditions: bumped `pyproject` `1.0.0 → 1.1.0` in lockstep
  with the three v1.0.0 drift-guard tests (`test_phase34/37/38` -- updated
  to guard the new version, never weakened), added
  `docs/release/v1.1.0-notes.md`, and added a Phase 44 promotion-guard test.
  Full suite + fresh build + artifact verification + wheel smoke green on
  the bumped version. The git tag and GitHub Release remain a **manual
  maintainer step** (exact `git tag`/`push` commands are in the v1.1.0
  notes) -- the agent never creates or pushes the tag itself. `v1.0.0` tag
  immutable throughout.

- ✅ **v1.1.0 post-release reconciliation -- ADR-0063 (Phase 45).** After the
  maintainer manually pushed the annotated `v1.1.0` tag and published the
  GitHub Release, reconciled the repository against that reality: verified
  tag integrity (`v1.1.0` peels to `a563dbe…` = `origin/main`; `v1.0.0`
  untouched) and the GitHub Release via API (id `352138767`, `draft=false`,
  `prerelease=false`). Corrected stale pre-release wording in the v1.1.0
  notes and README Status, drawing an explicit line between **software
  release state = `RELEASED`** and **product posture = `PREPARE_ONLY`**.
  **Artifact decision: `KEEP_SOURCE_ARCHIVES_ONLY`** -- Releases publish
  source archives only; no binary assets attached (a fresh `1.1.0`
  wheel/sdist was built + verified as evidence, not uploaded), matching the
  README's editable-install-only policy. No version bump, no safety change,
  no tag mutation.

## v2: automation layer (foundation)

- ✅ **User Job Preference Engine -- ADR-0064 (Phase 46).** The first phase
  of a new v2 automation layer built on top of the existing prepare-only
  engine (the engine itself -- discovery, decide, truthfulness gate, ATS
  scoring, tailoring, tracker -- is unchanged). A new, deliberately
  separate model/file (`domain/job_preferences.py` /
  `storage/job_preferences.py` / `job_preferences.json`, never merged into
  `profile.json`) captures titles, seniority, experience range, employment
  type, work mode, location, salary, preferred/blacklisted companies,
  industries, visa sponsorship, preferred technologies, include/exclude
  keywords, and a handful of behavior toggles for future phases. New
  interactive `career-agent preferences` wizard (injected `input_fn`, no
  globals, matching `capture-legal-status`'s shape) -- re-running it to
  tweak one field never requires re-entering the rest. `discover`/`auto`
  now generate intelligent search queries from preferences (title x
  location combinations, e.g. "Backend Developer Remote", "Backend
  Developer India") and fan Adzuna/Reed/USAJobs/Jooble out across them,
  instead of one static keyword string -- proven byte-identical to the
  prior single-keyword behavior when no preferences are configured (a
  regression guard, not just a docstring claim). Only the title/location/
  work-mode/exclude-keyword fields are wired to real behavior this phase;
  every other field (salary, visa, company lists, the confirmation/
  auto-tailor/auto-cover-letter toggles, max applications/day) is captured
  and persisted but explicitly documented as not yet enforced -- named,
  deferred integration points, not silent overclaims. The prepare-only
  execution boundary is untouched: `require_human_confirmation` is
  informational only and cannot bypass the real, hardcoded confirmation
  step. Incidental fix: `profile.json` was never actually gitignored
  (only the unused `master_profile.json` pattern was) -- fixed alongside
  adding `/job_preferences.json`. 41 new tests; 762 total. No browser
  automation in this phase -- that begins Phase 47.

- ✅ **Browser Automation Foundation -- ADR-0065 (Phase 47).** Launch
  Chrome (persistent profile or an ephemeral context seeded from an
  encrypted saved session), reuse/persist sessions, detect login, wait for
  -- never automate -- a human login, multi-tab support. The audit found
  this wasn't greenfield: `agents/apply/browser_applicator.py` already
  drives real Chromium (unwired from the CLI) and
  `integrations/browser_session.py`'s `EncryptedSessionStore` already
  persists sessions encrypted at rest -- both reused, not duplicated. New
  `BrowserManager`/`SessionManager`/`TabManager` under
  `integrations/browser/` (not a new top-level package -- consistent with
  `storage`/`integrations` as this project's existing unlayered I/O
  branches). `SessionManager.wait_for_login` is structurally incapable of
  typing a credential -- an AST-based test scans for any
  `.fill()`/`.type()`/`.press()` call, not a fragile text search. A fifth
  import-linter contract + purity test enforce that this layer has zero
  knowledge of jobs/résumés/applications, mirroring `domain/`'s existing
  zero-I/O enforcement. 28 new tests, all driven against a real local
  Chromium instance, not mocks; 790 total. No CLI command yet (nothing to
  invoke -- future adapter/planner phases are the consumers), no change to
  `BrowserApplicator` or the execution-safety boundary
  (`executor_available=False` still hardcoded), no website-specific logic
  (Phase 48), no automated login of any kind on any site. No new
  dependency, no version bump.

- ✅ **Website Adapter Framework -- ADR-0066 (Phase 48).** A common
  interface over eight providers (Greenhouse, Lever, Ashby, Workday,
  RemoteOK, Remotive, Arbeitnow, TheMuse). The audit found six of seven
  already have a real, working, tested, API-based `OpportunitySource` and
  `resolve_ats_kind` already does deterministic provider detection --
  `search()` delegates to what exists rather than re-scraping through a
  browser. No new canonical job model (reuses `Opportunity`; capability
  flags live on the adapter class, mirroring `ProviderCapabilities`'s
  existing pattern). Capabilities are grounded in `FormFiller`'s real
  evidence, not assumption: Greenhouse's verified text resume field ->
  `supports_resume_upload=False`; Lever's verified required file upload ->
  `True`; everything else unverified -> `False`. `extract_job()` (a
  URL-only fallback) uses only universal Open-Graph/`<title>` signals,
  never a guessed vendor selector -- this codebase has never verified any
  platform's job-*content* DOM, only Greenhouse/Lever's *application-form*
  DOM. `open_job`/`extract_job`/`detect_login` are identical across every
  adapter, shared via one mixin wired to Phase 47's `TabManager`/
  `SessionManager`. Workday's adapter is an honest stub (zero prior art
  anywhere in this codebase), matching `AshbyFormFiller`'s own precedent.
  `prepare_application` always raises -- declared on the interface, not
  implemented this phase. `AdapterRegistry.find(url)` means no caller ever
  switches on provider names. 45 new tests; 835 total. No CLI wiring, no
  form-filling, no login automation, no `Opportunity`/`ats_urls.py`
  change, no new dependency, no version bump.

- ✅ **Search Planner -- ADR-0067 (Phase 49).** Decides what to search
  *before* discovery runs (provider priority, keyword queries, budget,
  diversification) -- a second capability inside the existing
  `agents/planner/` boundary ADR-0007 already named, not a new top-level
  package. ADR-0007's original LangGraph/LLM-cost-cascade coordinator
  vision was never built (no `langgraph`/`langchain` import exists
  anywhere under `src/`); this stays purely deterministic, matching how
  `Decide` (the boundary's other capability) already works. New
  `execution_plan.py`/`provider_selector.py`/`budget.py`/
  `planning_rules.py`/`planner.py`, flat alongside `decide.py`. No
  `keyword_expander.py` (would wrap Phase 46's already-real
  `generate_search_queries`) and no `strategy.py` (diversification is one
  assembly-loop decision inside `build_execution_plan`, not an
  independently swappable strategy). Finally consumes
  `JobPreferences.preferred_ats_providers` -- captured in Phase 46,
  documented there as unconsumed until now. Search-volume budget is kept
  explicitly distinct from `max_applications_per_day` (an unrelated
  application-rate limit). `max_retries` is declared, not enforced -- no
  executor exists yet to enforce it (future work); an AST-based purity
  test proves zero I/O and zero `async def` across every new module. 33
  new tests; 868 total. No CLI wiring, no AI/LLM call, no change to
  `Decide`/`AdapterRegistry`/the execution-safety boundary, no new
  dependency, no version bump.

- ✅ **Resume Variant Engine -- ADR-0068 (Phase 50).** Cover-letter
  generation + resume-variant storage on top of the unmodified tailoring
  pipeline. Most of the brief already existed (`ResumeTailoringPipeline.run()`
  already does generate -> gate -> ATS-score; `ats_scoring.extract_jd_keywords`
  already is skill/JD analysis); the truthfulness gate is deliberately
  *not* extended to freeform prose this phase -- atomizing/verifying
  arbitrary generated sentences is a real, separate design problem, left
  for future work. Instead `domain/cover_letter.py::assemble_cover_letter`
  is a **deterministic, zero-LLM** template that copies only the
  already-approved résumé summary and up to three highlights verbatim into
  a letter shape -- no new fabrication surface, so no new gate is needed.
  `domain/resume_variants.py::select_closest_variant` ranks previously
  approved variants by keyword overlap (reusing `extract_jd_keywords`
  unchanged) but is purely advisory -- `ResumeVariantEngine.build_materials()`
  (renamed from `.prepare()` in Phase 51 -- see below)
  always calls the unmodified pipeline regardless of its answer, so it
  cannot influence what gets gated. `SqliteResumeVariantStore` (added into
  the existing one-file `storage/sqlite.py` convention) is append-only,
  mirroring `SqliteApplicationStore`; `ResumeVariantEngine` itself has zero
  storage dependency (proven by an AST canary) -- it returns a
  built-but-unsaved `ResumeVariant`, the same "pipeline doesn't touch
  storage either, `cli.py` does" shape already established. 24 new tests;
  892 total. No CLI wiring, no change to `ResumeTailoringPipeline`/
  `LLMResumeGenerator`/`LLMTruthfulnessGate`, no new dependency, no version
  bump.

- ✅ **Application Preparation Engine -- ADR-0069 (Phase 51).** Opens a
  real browser, fills a live application form, and stops before Submit --
  the audit found this is almost entirely not greenfield: the unwired Tier
  2 `BrowserApplicator` (ADR-0020/0028/0032) already implements the exact
  sequence the brief describes (per-platform `FormFiller` fills identity/
  résumé fields, `question_answerer.py` classifies and auto-answers
  everything else it safely can, unresolved fields are manifested for a
  human) and only then clicks submit. Extracted the field-detection/triage
  helpers out of `browser_applicator.py` into a new shared
  `agents/apply/field_inspection.py` (verbatim, no behavior change --
  proven by `browser_applicator`'s own unchanged 32-test suite), and built
  `agents/application/engine.py::ApplicationPreparationEngine` composing
  them plus Phase 47's `BrowserManager`/`SessionManager`/`TabManager` --
  reaching the identical point `BrowserApplicator.submit()` reaches right
  before the submit click, then simply returning. No submit-selector/click
  reference exists anywhere in the new module, proven by an AST-based
  source-scan test. No new `field_detector.py`/`answer_engine.py` (would
  duplicate the extraction/`question_answerer.py`); no `field_mapper.py`
  (most example fields -- website/LinkedIn/GitHub -- have no
  `MasterProfile` field to map from at all, so they honestly fall through
  to the manifest); no `upload_manager.py` (Lever's real upload already
  lives in `LeverFormFiller`; cover-letter upload is attempted nowhere
  since no platform has a verified selector). New `domain/
  application_session.py::ApplicationSession` (pure data; no
  submission-confirmation field can exist on it at all) follows Phase 50's
  precedent of pure results living in `domain/`. Found and fixed a real
  collision: `ResumeVariantEngine.prepare()` would have tripped the
  existing release-invariant test's literal `.prepare(` ban the moment
  `cli.py` actually called it -- renamed to `.build_materials()`. New
  `career-agent prepare` CLI command and `SqliteApplicationSessionStore`.
  19 new tests; 911 total. No submit click anywhere, no change to
  `BrowserApplicator`/`TieredApplicator`/the execution-safety boundary, no
  new dependency, no version bump.

- ✅ **Human Review Center -- ADR-0070 (Phase 52).** The sole
  `READY_FOR_REVIEW` -> `APPROVED` transition boundary. `ApplicationSession`
  already carries everything a human needs to decide (Phase 51); this
  phase adds the decision. `domain/review.py::ReviewSession` references
  `application_session_id` plus a few cheap denormalized display fields
  rather than duplicating warnings/missing-fields/filled-fields/uploaded-
  files/résumé-variant/cover-letter content -- the same "denormalize
  identity fields, not full content" precedent `SqliteApplicationStore`'s
  own `company`/`title` columns already set, proven structurally (a test
  asserts those fields don't exist on `ReviewSession` at all).
  `format_review_summary` is pure, deterministic formatting (no AI, no
  filtering -- every warning and missing field always shown) living in
  `domain/` alongside `ReviewResult`, not split into separate
  `review_summary.py`/`review_result.py` files as the brief suggested (no
  capability behind the split). `agents/review/review_engine.py::ReviewEngine`
  has zero browser dependency -- proven by two AST-based source-scan tests
  (no `integrations.browser` import, no `.click(` call), the identical
  structural-guarantee discipline `ApplicationPreparationEngine`'s own
  no-click test already established. Only an explicit "y"/"yes" answer
  produces `APPROVED` (reusing `confirm_submission`'s no-default-to-yes
  discipline); `CANCELLED`/`TIMEOUT` are reachable via an
  injectable-exception seam on `input_fn`, since a portable stdin timeout
  is a real, separate, `SIGALRM`-is-POSIX-only problem this phase doesn't
  need to solve to prove the states exist and are handled correctly.
  `career-agent prepare` now also writes a JSON session-file handoff
  (mirroring `discover`'s own opportunity-file-handoff convention exactly)
  that the new `career-agent review --session <path>` command consumes. No
  new `review_storage.py` either -- `SqliteReviewSessionStore` joins the
  existing one-file `storage/sqlite.py` convention. Checked against Phase
  51's found `.prepare(`-collision release-invariant test explicitly; no
  second collision. 36 new tests; 947 total. No Submit, no browser
  mutation, no AI review, no résumé/field editing, no Submission Engine,
  no new dependency, no version bump.

- ✅ **Human-Approved Submission Engine -- ADR-0071 (Phase 53).** The
  boundary every phase since Phase 24 (ADR-0050) built toward and refused
  to cross -- undertaken only after the user's own explicit, detailed,
  safety-first authorization. The audit found the actual executor already
  exists: `BrowserApplicator` (Tier 2, ADR-0020/0028/0032) already does
  fill -> triage/auto-answer -> click submit -> check for a challenge ->
  return `ApplicationSubmitted`, unwired specifically pending this
  boundary. **This phase builds the fail-closed gate in front of it, not
  a second implementation.** `agents/submission/submission_engine.py::
  SubmissionEngine` checks, in order: the review and application session
  actually pair together; the review is `APPROVED`; the application
  session is still `READY_FOR_REVIEW`; the résumé about to be submitted
  matches (content-for-content, via a new `SqliteResumeVariantStore.get`)
  what was actually reviewed -- a profile edit in between refuses rather
  than silently submitting different content; `domain/execution.py`'s
  unmodified fail-closed boundary (`execute_allowed`, `resolve_source_policy`
  -- only Greenhouse/Lever/Ashby resolve `ASSISTED`, everything else
  refuses) evaluated as a dry run *before* ever asking the human anything,
  so a doomed attempt never wastes their attention; and only then a real
  5-second countdown plus a blocking ENTER confirmation
  (`_countdown_and_confirm`), un-bypassable, Ctrl+C recorded as
  `CANCELLED`. No fabricated verification: this codebase has never
  verified a "Thank you" page/confirmation number on any platform, so
  `confirmation_id`/`confirmation_url` stay `None` with an explicit
  warning rather than guessed; the only verified signal is
  `BrowserApplicator`'s own `ApplicationSubmitted`/`HumanActionRequired`
  distinction, reused unchanged. A generic exception during the actual
  submit call (which contains the click) is recorded `UNKNOWN`, never
  `FAILED` -- the same "ambiguous evidence can never become a definite
  result" rule `domain.execution.outcome_from_ack` already enforces,
  applied to this exception-handling decision. No new `verification.py`/
  `tracker.py`: verification *is* the reused event distinction (no new
  algorithm to house), `SqliteSubmissionResultStore` joins the existing
  one-file `storage/sqlite.py` convention, and `storage/excel.py` gains a
  small `export_submissions()` sibling. **Found and deliberately rewrote**
  (not weakened) `tests/test_phase28_release_invariants.py`'s blanket
  `.submit(`/`.prepare(` ban -- correctly tripped by this phase's own
  `engine.submit(` call -- into a stronger, more precise invariant proving
  `execute_allowed()` genuinely runs before the real executor call, Tier 1/
  email remain fully dead, and `BrowserApplicator` is only ever
  constructed inside `SubmissionEngine`, never directly in `cli.py`. 27
  new tests; 974 total. No CAPTCHA/MFA automation, no password storage, no
  silent retry, no AI verification, no change to `BrowserApplicator`/
  `ApplicationPreparationEngine`/`ReviewEngine`, no new dependency, no
  version bump.

- ✅ **Web Dashboard read API -- ADR-0072 (Phase 54).** The backend core
  workflow (Search -> Plan -> Discover -> Tailor -> Prepare -> Review ->
  Approve -> Submit -> Track -> Export) is complete; this phase is the
  first step toward a web dashboard on top of it, scoped deliberately down
  from the full brief (new frontend toolchain + FastAPI layer in one pass)
  to the backend API surface only, and further scoped to **read-only**.
  `src/career_agent/api/` is a thin FastAPI layer: each router
  (`applications`/`reviews`/`submissions`/`resume_variants`) wraps exactly
  one existing store's `all_*()` method, `analytics.py` adds one
  `collections.Counter` aggregation step (no new metrics engine, and
  deliberately does not touch the older `SqliteApplicationStore`/funnel
  pipeline -- a documented separate pipeline since Phase 51), and
  `settings.py` redacts every API-key/token field to a `configured: bool`
  flag, never its value. **No route can trigger discovery, tailoring,
  review approval, or submission** -- `SubmissionEngine` is not imported
  anywhere under `career_agent.api`, and this is enforced structurally, not
  just documented: `CORSMiddleware` only allows `GET`, and a dedicated test
  enumerates every route the app actually registers and asserts each one's
  methods are a subset of `{GET, HEAD, OPTIONS}`. New CLI subcommand
  `career-agent serve [--host] [--port]` runs `uvicorn.run(create_app())`;
  `fastapi`/`uvicorn` are a new optional `web` extra
  (`pip install 'career-agent[web]'`), imported lazily inside
  `run_serve_command` so every other command keeps working with a plain
  install. 15 new tests; 990 total. No authentication (single-user,
  localhost-only, matching the README's own framing -- multi-user auth is
  a later phase); no React frontend yet -- that is the immediate follow-up
  phase, building against this now-tested API contract.

- ✅ **React Dashboard frontend -- ADR-0073 (Phase 55).** The frontend
  ADR-0072 named as its own immediate follow-up. `frontend/` is a React 19 +
  TypeScript + Vite app (TailwindCSS + hand-written shadcn-style
  primitives, TanStack Query, React Router, React Hook Form, Recharts,
  Lucide) with 8 pages (Dashboard, Search Jobs, Applications, Review Queue,
  Submission Queue, History, Analytics, Settings), a responsive
  sidebar/navbar layout (mobile drawer), and persisted dark mode. **Every
  page renders real data from the six existing `GET` routes only** --
  `services/api.ts` is a one-function-per-route wrapper matching
  `api/routers/*.py` exactly; cross-route joins (e.g. Review Queue's
  résumé/cover-letter preview alongside its approval decision, Submission
  Queue's "ready to submit" list) are pure functions over the already-
  fetched responses (`lib/derive.ts`), the same "aggregation is
  presentation logic" precedent `analytics.py` already set server-side --
  no new status vocabulary, no client-side business rule the backend
  doesn't already express. The brief's write actions (Search Jobs'
  Search, Review Queue's Approve/Reject, Submission Queue's Submit) have no
  backing endpoint (ADR-0072 shipped read-only, by design) -- rather than
  fabricate them, `components/CliOnlyAction.tsx` renders a disabled button
  naming the exact real CLI command instead, and each page's `Callout`
  explains why (most pointedly: Submission Queue states there is no live
  browser state or countdown to show, since ADR-0071's countdown-plus-
  blocking-ENTER confirmation is a real terminal interaction this
  dashboard cannot safely reproduce over HTTP). UI primitives
  (`components/ui/*`) are hand-written in the shadcn "copy into your repo"
  style rather than generated via the shadcn CLI (no network path to its
  registry in this sandbox) -- same contract, same reasoning as any other
  reused-not-duplicated primitive in this project. New CI job
  `verify-frontend` (matrix `ubuntu-latest`/`windows-latest`, matching the
  backend `verify` job) runs `npm ci`, type-check, lint, `vitest run`, and
  `vite build` on every push/PR. 15 new frontend tests (pure-function
  coverage for every `derive.ts` join, a `CliOnlyAction` behavior test,
  route/rendering smoke tests including an API-unreachable error-banner
  path); manually verified against a real running `career-agent serve`
  with seeded data, screenshotted in light/dark themes and at a mobile
  viewport. Zero backend files changed; full backend suite re-confirmed
  unmodified (990 passed).

- ✅ **Authentication & Multi-User Platform -- ADR-0074 (Phase 56).**
  Turns the dashboard from single-user to real multi-user: JWT access
  tokens (15 min, in-memory on the frontend, never `localStorage`) +
  opaque rotate-on-use refresh tokens (30 days, httpOnly `SameSite=Lax`
  cookie, SHA-256-hashed server-side, never a JWT). `user_id` lives as a
  SQL column (a new required keyword-only argument on each store's
  `save()`, no default) on `application_sessions`/`review_sessions`/
  `submission_results`/`resume_variants` -- **not** a domain-model field,
  keeping `ApplicationSession`/`ReviewSession`/`SubmissionResult`/
  `ResumeVariant` themselves and all ~40 of Phases 50-53's existing tests
  completely unchanged. Password hashing (bcrypt) and JWT encode/decode
  live in new `core/security.py`, not `domain/` -- `domain/auth.py` was
  the first draft, moved after `tests/domain/test_purity.py` (rightly)
  rejected `bcrypt`/`jwt` imports there; `domain/user.py::User` stays pure
  data. New `SqliteUserStore`/`SqliteRefreshTokenStore`/
  `SqlitePasswordResetTokenStore`/`SqliteUserPreferencesStore` (the last
  reusing `JobPreferences`, ADR-0064, unmodified, as a per-dashboard-user
  payload alongside the CLI's untouched file-based store) plus
  `migrate_to_multi_user()` -- idempotent, `ALTER TABLE`s the `user_id`
  column into a pre-Phase-56 database and backfills every ownerless row to
  one real, auto-provisioned "local operator" account. The CLI has no
  login flow and never will -- `prepare`/`review`/`submit` now call that
  migration function once per command and always act as that one account;
  multi-user is a dashboard concept only. All six existing dashboard
  routes gained `Depends(get_current_user)` and switched from `all_*()` to
  `by_user(current_user.id)`, proven by a real cross-account isolation
  test; `/api/settings` gained `jwt_secret_key` to its redaction list (a
  real leak caught while wiring this phase -- leaking the signing key
  would let a caller forge a token for any user). `Settings.jwt_secret_key`
  has no default and fails closed with a `500` if unset. New `/auth/*`
  (register/login/logout/refresh/me/forgot-password/reset-password) and
  `/user/*` (profile/preferences) routers -- the only write-capable
  routers this API has ever had, proven structurally (every other route
  stays `GET`-only). `forgot-password` always returns `202` regardless of
  whether the email exists and issues a real hashed token, but sends no
  email -- no transport exists yet (Phase 58); faking delivery was
  refused. A process-local, in-memory fixed-window rate limiter guards
  register/login/forgot-password (Redis deferred to the eventual
  multi-instance deployment story, Phase 59). Frontend: `AuthProvider` +
  `ProtectedRoute` + a refresh-aware `apiFetch` (attaches the token,
  retries once via `/auth/refresh` on 401, dispatches a
  `session-expired` event on final failure -> `SessionExpiredScreen`);
  Login/Register/ForgotPassword/ResetPassword/Profile/Account pages. Two
  real bugs found and fixed only by driving a live browser against a live
  backend (not caught by any mocked-fetch unit test): (1) React Strict
  Mode's dev-mode double-invoked effects raced refresh-token rotation and
  lost a just-restored session -- fixed with a `useRef`-memoized in-flight
  promise, now covered by a Strict-Mode regression test; (2) dark mode
  never applied on the public auth pages at all, since Phase 55's
  `useTheme()` call lived only inside `Navbar` -- fixed by lifting theme
  state to a root-level `ThemeProvider`. 79 new backend tests (1069
  total), 13 new frontend tests (29 total); manually verified end-to-end
  with Playwright (register -> per-user empty dashboard -> profile update
  -> reload preserves session -> logout -> redirect), light/dark and
  mobile confirmed. No Postgres (one SQLite file with per-row ownership
  fully satisfies the actual requirement), no admin capability wired
  (`User.role`/`require_admin` exist, nothing grants elevated access yet),
  no in-app change-password (reset-token flow only), no organizations/
  billing (Phase 60).

- ✅ **AI Career Coach -- ADR-0075 (Phase 57).** Ten features named in the
  brief; a repository-reality audit found six have a real data source
  (`domain/ats_scoring.py`'s taxonomy, the LLM provider abstraction,
  `ClaimVerifier.verify_claim`) and four (Company Research, Salary
  Insights, Weekly Career Report, Career Roadmap) do not -- no company-
  research/salary-benchmarking data source exists (and ADR-0036 rules out
  a scraper), and outcome data (interviews/rejections) only lives in an
  old, disconnected CLI-only pipeline the dashboard never reads. Surfaced
  as an explicit scoping question; **user chose to build the six for real
  and defer the four with a named reason, still visible in the UI**.
  Built: Resume Analysis (ATS score, missing keywords, weak-bullet and
  formatting checks), Job Match Score, AI Resume Suggestions, Cover
  Letter Assistant (rewrite/shorten/more formal/more technical),
  Interview Preparation (JD-grounded technical/behavioral/role-specific
  questions plus STAR guidance), Skill Gap Analysis. New
  `domain/coach_analysis.py` is a distinct, lighter deterministic
  pipeline for freeform pasted resume text against a JD -- reuses
  `extract_jd_keywords`/the curated taxonomy but not `score_resume`'s
  structured-`TailoredContent`-shaped matching (a genuinely different
  input contract), plus two new heuristics (`find_weak_bullets`,
  `find_formatting_issues`), both fixed and explainable, never a model
  judgment. Skill Gap's "learning priority" ranking (hard skills first,
  then by earliest JD mention) is the same kind of named heuristic, not a
  learned model -- there's no outcome data in this codebase to train one
  on. A new narrow LLM port, `CareerCoachAdvisor`
  (`draft_text(prompt) -> str`, Groq-first/Anthropic-second like every
  other port), backs the three LLM features. **Every AI-drafted claim is
  verified before it is ever shown**: Resume Suggestions only ever asks
  the advisor to reword an existing bullet, then independently re-checks
  each rewording via the *same* `ClaimVerifier` the truthfulness gate
  uses (0.7 confidence threshold, matching `agents/resume/gate.py`) --
  an unverified suggestion is silently dropped, not surfaced. Cover
  Letter Assistant's rewrite is verified the same way, raising a typed
  `CoverLetterTransformRejectedError` (fail closed) if it can't be
  confirmed as entailed by the original letter. Interview Prep needs no
  verifier -- it produces questions/guidance, not achievement claims,
  and its prompt requires every question's "why" to cite the specific JD
  text that prompted it. Nothing in this phase has any write path back
  to a résumé, profile, or stored record -- Resume Suggestions'
  Accept/Reject buttons only flip local component state, which is how
  "users explicitly accept any changes before they're applied" is
  actually enforced (there is no channel to apply one automatically even
  if a caller tried). New `/coach/*` router (deliberately not
  `/api/coach/*`, preserving the existing `/api/*` GET-only structural
  proof) is a third write-capable-router exception alongside
  `/auth/`/`/user/` -- every call is stateless and self-contained (resume/
  JD text in the body), so it never touches the database. Frontend: a new
  "Career Coach ⭐" sidebar section with an overview page plus the 6 real
  and 4 deferred feature pages; the deferred ones render an honest
  `Callout` explaining why, the same `CliOnlyAction` precedent Phase 55
  established for naming an unavailable capability instead of faking one.
  35 new backend tests (1104 total), 3 new frontend tests (32 total);
  clean ruff/lint-imports/`tsc`/`oxlint`/`vite build`. Zero changes to
  `ats_scoring.py`, `domain/cover_letter.py`, or the real ATS-gated
  tailoring pipeline.

- ✅ **Production Deployment & Infrastructure -- ADR-0076 (Phase 59).**
  The audit found a real conflict inside the brief itself: real
  PostgreSQL support would mean duplicating `storage/sqlite.py`'s ~15
  `sqlite3`-based store classes for a second backend, or rewriting the
  whole storage layer onto something like SQLAlchemy -- both directly
  contradicting the brief's own "do not duplicate logic"/"do not rewrite
  backend services" instructions. Surfaced to the user rather than
  decided unilaterally; **chose to ship the Docker/Nginx/health/logging
  infrastructure for real, with `DATABASE_URL` accepted and validated in
  configuration but not consumed** -- SQLite remains the only backend the
  storage layer actually reads from or writes to, named as a deferred
  follow-up in ADR-0076, not faked.

  `Dockerfile.backend`: two-stage build, installs the package plus
  Playwright's Chromium (the exact browser this project already depends
  on, `pyproject.toml`'s `playwright>=1.44` -- not a new one), runs as a
  non-root user via gunicorn supervising 4 uvicorn workers.
  `Dockerfile.frontend`: builds the same `npm ci && npm run build` CI
  already runs (ADR-0073), serves the static output through nginx,
  non-root. A third, small image (`deploy/nginx/`) is the edge reverse
  proxy: `/` to the frontend container, `/api`/`/auth`/`/user`/`/coach`/
  `/health`/`/ready`/`/metrics` to the backend -- the exact same path
  list `frontend/vite.config.ts`'s dev-server proxy already uses, one
  source of truth. `docker-compose.yml` (base: backend + frontend +
  nginx, SQLite) / `.dev.yml` (hot reload, Vite dev server, edge proxy
  disabled since Vite's own dev proxy already covers it) / `.prod.yml`
  (resource limits, `restart: always`, `JWT_COOKIE_SECURE=true`) --
  `postgres`/`redis` services exist and are startable but sit behind
  Compose profiles (`--profile postgres`/`--profile redis`), off by
  default, since neither is consumed by the application (redis: there is
  no caching layer anywhere in this codebase to back with one, either --
  adding one speculatively would be exactly the unrequested abstraction
  this project's own discipline avoids).

  New `/health` (liveness), `/ready` (readiness -- opens the real SQLite
  database, returns `503` on failure, never a false `200`), and
  `/metrics` (Prometheus text format: uptime + request counts by status
  class, hand-formatted, no new dependency) routes join the unchanged
  `/api/health` (Phase 54) in `api/routers/health.py` -- all GET-only, so
  no change to the existing `/api/*`-GET-only / `/auth/`,`/user/`,
  `/coach/`-are-the-only-write-capable-routers structural tests.
  `core/logging_config.py::JsonFormatter` is one small stdlib
  `logging.Formatter` subclass (no `structlog`/`python-json-logger`
  dependency) for structured JSON logs, on by default in
  `ENVIRONMENT=production`; `api/middleware.py::log_requests` logs one
  line per request (method/path/status/duration) and **never logs
  headers or bodies** (a token/password/API-key leak risk, the same care
  Phase 56/57 already took). `core/startup_validation.py::validate_startup`
  surfaces missing-config findings (a missing `JWT_SECRET_KEY` is an
  error only in `ENVIRONMENT=production`, else a warning; a set-but-
  unconsumed `DATABASE_URL` always warns) at process start via the
  FastAPI `lifespan` hook -- changes no existing fail-closed enforcement,
  only makes the same fact visible in the log stream before the first
  request hits it.

  New CI `docker` job (Linux-only, matching ADR-0056's existing Windows/
  macOS Docker-scope line): validates all three Compose files, builds all
  three images for real, **verifies Playwright's Chromium actually
  launches** inside the built backend image (a real headless
  `sync_playwright().chromium.launch()` call, not an assumption -- the
  brief explicitly asked for this), starts the full stack, waits for
  `/ready`, and smoke-tests `/health`/`/metrics`/the frontend's root HTML
  through the edge proxy before tearing down. Browser automation stays
  headed-by-design (`BrowserManager.launch`'s own `headless=False`
  default, unchanged, in service of the human-in-the-loop review/
  confirmation the Submission Engine's whole safety model depends on) --
  the backend container has no display server, so `prepare`/`review`/
  `submit` are not expected to run inside it; named honestly in
  `docs/deployment/docker.md` rather than silently worked around, since
  forcing headless automation to work would be a real Submission Engine
  safety-posture change, explicitly out of scope for this phase.

  `frontend/src/services/http.ts` gained a build-time
  `VITE_API_BASE_URL` prefix (empty by default -- every existing
  relative-path call is unaffected; only meaningful when backend and
  frontend are genuinely served from different origins). 30 new backend
  tests (1134 total), 1 new frontend test (33 total); full suites, ruff,
  lint-imports, `tsc`/`oxlint`/`vite build` green. Zero changes to
  `SubmissionEngine`, `BrowserApplicator`,
  `BrowserManager`/`SessionManager`/`TabManager`, or any auth logic.

- ✅ **Notifications & Background Processing -- ADR-0077 (Phase 58).** The
  brief named 17 trigger events, a full `NotificationEngine`/
  `ReminderEngine`/`DigestGenerator` stack, and Slack/Discord/Teams
  channels, requesting ADR number "0075" -- already used by the AI Career
  Coach phase; correctly numbered ADR-0077 instead. The audit found the
  existing `EventBus`/`Notifier` (Telegram + ntfy, ADR-0040) is CLI-only
  and was never wired to the dashboard, no scheduler dependency or SMTP
  transport exists anywhere, and several named events have no real
  trigger point: discovery and application-outcome recording remain
  CLI-only, dashboard-disconnected pipelines; no interview-tracking or
  per-user profile-completeness store exists; no invitation system
  exists; no API-key-expiry concept exists; the Career Coach is
  synchronous request/response with no async "available later" state;
  session-expiry is already fully handled client-side
  (`SessionExpiredScreen`). This was the third consecutive phase to hit
  this "brief names more than the architecture supports" pattern, after
  two explicit user endorsements of "build what's real, defer what's not,
  name it" (Phase 57, Phase 59); the scoping decision was stated directly
  this time rather than asked a third time.

  **Built for real:** notifications for résumé prepared, review
  approved/rejected, submission completed/cancelled/failed, and password
  changed -- wired at their six real call sites in `cli.py`/
  `api/routers/auth.py`, every dispatch wrapped in a broad exception
  catch so a delivery failure can never block the underlying operation
  ("notify, never gate," ADR-0005). `domain/notification.py`'s
  `Notification`/`DeliveryAttempt` follow the "`user_id` in the SQL row,
  never the domain model" precedent (Phase 56); `DeliveryStatus =
  SENT | FAILED | SKIPPED` is recorded for every real attempt through
  every channel, regardless of outcome -- the literal implementation of
  "never fabricate delivery success." Email is stdlib `smtplib` only (no
  new dependency, matching `TelegramNotifier`/`NtfyNotifier`'s own "raw
  protocol over an SDK" discipline); the webhook channel is one
  **generic** `HttpClient`-based JSON POST sender that already satisfies
  Slack/Discord/Teams incoming webhooks -- not three separate SDKs,
  reading the brief's own "only build channels that have existing
  infrastructure" instruction correctly rather than treating it as a gap.
  `ReminderEngine` covers the three reminder types with a real data
  source (pending review, pending submission, missing Promptfoo
  validation, reusing `select_claim_verifier`/`verify_promptfoo_results`
  exactly as `cli.py` already does); `DigestGenerator` reports the three
  counts it can compute for real (prepared/awaiting-review/submitted),
  omitting "new jobs"/"interview scheduled" as having no data source
  rather than guessing zero.

  `career_agent/scheduler.py` (`APScheduler`'s `AsyncIOScheduler`, six
  named jobs, wired into `api/app.py`'s existing `lifespan` hook) lives
  **top-level**, not under `core/`, because it needs to import both
  `agents.notifications.*` and `llm.providers` -- both forbidden for
  `core/` by the two import-linter layer contracts (ADR-0018/ADR-0043).
  This exactly mirrors how `cli.py`, the existing composition root, is
  already exempt from both contracts -- a reusable pattern for any future
  cross-layer-composing module that isn't itself an agent. **The
  scheduler is structurally proven incapable of ever submitting
  anything** via an AST source scan (`tests/test_scheduler_purity.py`),
  the same discipline `ApplicationPreparationEngine`'s no-submit-selector
  test and `ReviewEngine`'s no-browser-import test already established --
  not merely a docstring promise. Two new write-capable routers
  (`/notifications/*`, `/notification-settings`) join `/auth/`, `/user/`,
  `/coach/` as the API's only mutation-capable exceptions to the
  `/api/*`-GET-only structural test, both proven user-isolated (a
  cross-user notification access attempt is a 404, never a leak).

  Frontend: `NotificationBell` (navbar, polls `/notifications/unread`
  every 30s via TanStack Query's `refetchInterval` -- no websockets, the
  same shape the rest of this dashboard already commits to),
  `NotificationsPage` (full center: filter/search/pagination/mark-read/
  mark-all-read/delete), `NotificationSettingsPage` (channel toggles,
  reminders/digests toggles, webhook URL -- never echoed back once set,
  the same discipline this API already applies to secrets), and
  `BrowserNotifier` -- the exact file `agents/notifications/dispatcher.py`'s
  own docstring names as where the client-side-only browser-push channel
  lives, since there is no server-side "send a browser notification"
  action to attempt or log; it shows a permission banner only while
  undecided, and degrades gracefully (verified against a real
  `Notification`-undefined test case) where the browser API is
  unsupported.

  99 new backend tests (1233 total), 16 new frontend tests (49 total);
  full suites, ruff, both import-linter contracts, `tsc`/`oxlint`/
  `vite build` all green. Zero changes to `SubmissionEngine`,
  `BrowserApplicator`, the Human Review Center's approval semantics, or
  any authentication logic beyond one notification dispatch call at the
  end of an already-existing `reset_password` handler.

- ✅ **SaaS Multi-Tenant Platform (Organizations & RBAC) -- ADR-0078
  (Phase 60).** Unlike the three prior phases' "brief names more than the
  architecture supports" pattern, this phase's audit found something
  categorically different: [ADR-0000](docs/adr/0000-project-philosophy.md)
  (this project's own foundational document) explicitly rules out
  multi-tenancy "by fiat" and names its own revisit trigger as exactly
  this scenario -- single self-hosted user becoming a hosted/multi-user
  product. Surfaced directly to the user (not folded into a routine
  scoping question); **the user confirmed: proceed, and amend ADR-0000**
  -- its Status line and "Future revisit criteria" now point to ADR-0078;
  the original decision text is untouched, since ADRs are immutable once
  accepted. A second real tension resolved before writing code: the brief
  demands `organization_id`+`user_id` on every query while also
  forbidding rewriting existing services -- retrofitting `organization_id`
  onto the nine pre-existing personal-resource tables (résumé variants,
  application sessions, review sessions, submission results,
  notifications, and four more) would mean rewriting every one of them.
  The scoping adopted: **every genuinely new piece of data this phase
  introduces (organizations, memberships, invitations, roles, audit log,
  billing) is organization_id+user_id-scoped from creation; the nine
  existing tables stay exactly as user_id-scoped as before**, named
  explicitly rather than silently narrowed.

  Every registered account gets a real personal organization at
  registration (owner role, slug derived from the email's local part);
  pre-Phase-60 accounts are backfilled idempotently on every startup,
  mirroring `migrate_to_multi_user`'s own "never orphan history, safe to
  re-run" discipline. Five fixed roles (owner/admin/recruiter/member/
  viewer) with a fixed permission matrix (`domain/roles.py`) -- a
  deliberately separate concept from `domain.user.UserRole`
  (`"user"|"admin"`, Phase 56's still-mostly-unused platform-wide flag).
  `api/rbac.py`'s `OrganizationRequired`/`PermissionRequired`/
  `RoleRequired` are real per-request `SqliteMembershipStore` lookups --
  deliberately no JWT claim change (would touch every token-handling call
  site for one phase, and a 15-minute-old claim can't reflect a role
  changed 30 seconds ago anyway). Invitations
  (`career_agent/invitations.py`) mirror `SqlitePasswordResetTokenStore`'s
  "store a hash, never the token" discipline and **never duplicate email
  logic** -- delivery reuses the exact Phase 58
  `NotificationEngine`/`NotificationDispatcher`/`EmailSender` stack when
  the invited email already has an account (in-app plus the account's own
  preferences), falling back to a direct email send only when it
  genuinely can't (no `user_id` yet exists for an in-app row), named as
  exactly that limitation rather than hidden.

  Billing (`integrations/billing.py`'s `BillingService` protocol +
  `FakeBillingProvider`) is the same port+adapter shape every other
  integration in this project already uses -- **no Stripe integration, no
  external payment call anywhere in this codebase**, but seat limits are
  *actually enforced* (`402 Payment Required` past a plan's `max_seats`,
  checked before creating an invitation), not just displayed. Audit log
  is append-only and best-effort (a failed audit write can never fail the
  real action it's describing). `require_admin` (Phase 56's own unused
  scaffolding) gets its first real caller: a minimal platform-admin
  surface listing every organization and its members.

  New GET-only routers (`/api/roles`, `/api/admin`, `/api/audit`) join
  the existing read-only structural proof for free; new mutation-capable
  routers (`/organizations/*`, `/team/*`, `/billing/*`) join `/auth/`,
  `/user/`, `/coach/`, `/notifications/`, `/notification-settings` as the
  API's only write-capable exceptions, each proven both permission-gated
  and organization-isolated. Frontend: `organization_id` travels as a
  route param (`/organizations/:id/{team,billing,audit}`), not a new
  global "current organization" context -- `OrganizationsPage` is the
  real switcher/creator that links into each org's own pages;
  `AcceptInvitePage` drives the real accept flow from a URL token; the
  sidebar gains an "Organization" section plus a conditionally-rendered
  "Platform Admin" link.

  116 new backend tests (1349 total), 19 new frontend tests (68 total);
  full suites, ruff, every import-linter contract, `tsc`/`oxlint`/
  `vite build` all green. Zero changes to `SubmissionEngine`,
  `ReviewEngine`, `NotificationEngine`, the tailoring pipeline, the
  Career Coach, the scheduler's job logic, JWT/refresh-token
  authentication, or any of the nine pre-existing personal-resource
  tables. The CLI remains single-operator with no organization
  awareness -- multi-tenancy is a dashboard/API concept only.

- ✅ **Production Hardening -- ADR-0079 (Phase 61).** Not a feature phase:
  with the roadmap (Phases 1-60) feature-complete, the owner asked to
  shift effort to observability/error-handling/security/CI scanning
  instead of adding scope. The audit found ADR-0076's structured JSON
  logging, request logging, and edge security headers already real, but
  no request-correlation ID anywhere, no global exception handler, no
  Content-Security-Policy at either nginx layer, and CI running only
  `ruff`+`pytest` -- no dependency or secret scanning at all.

  `core/request_context.py` is a new, framework-agnostic `ContextVar`
  (kept out of `api/` on purpose -- `core` importing FastAPI would need
  nothing here, and the layers contract already forbids the reverse
  direction). `api/middleware.py`'s new `request_id_middleware` is
  registered as the *outermost* app middleware: it reuses an incoming
  `X-Request-ID` header or generates a UUID4, threads it through every
  structured log line for the rest of the request via a new
  `RequestIdLogFilter`, and always returns it on the response. A real bug
  surfaced by testing, not assumed: Starlette treats a handler registered
  for the bare `Exception` type as `ServerErrorMiddleware`'s own handler,
  which sits *outside* every `app.middleware("http")` callback -- so by
  the time it runs, `request_id_middleware`'s own `finally` has already
  reset the contextvar back to empty. Fixed by also stashing the ID on
  `request.state`, which survives regardless of how the exception
  unwound (verified with a real `TestClient` call before and after the
  fix). The new global exception handler
  (`api/app.py::_handle_unexpected_error`) leaves every existing
  `HTTPException` response (401/403/404/422, ...) untouched -- verified
  by a dedicated test -- and only catches genuinely unhandled exceptions,
  logging the full traceback through this project's own structured
  logger and returning `{"detail": "Internal server error", "request_id":
  "..."}`, never `str(exc)` or a traceback fragment.

  CSP added to both `deploy/nginx/edge.conf` and `frontend.conf`,
  matching the existing per-layer duplication of the other three security
  headers: `script-src` stays strict (no `'unsafe-inline'`/`'unsafe-
  eval'` -- the SPA build has no inline `<script>`), `style-src` keeps a
  documented, deliberate `'unsafe-inline'` exception for React/Recharts'
  runtime inline `style="..."` attributes (no nonce/hash mechanism wired
  yet).

  CI gains three real, always-run gates in a new `security` extra
  (`pip install -e ".[dev,security]"`, opt-in rather than folded into
  `dev` since neither `verify-frontend` nor `docker` needs it):
  `pip-audit` (20 CVEs across `aiohttp==3.13.4`/`pypdf==6.10.2`
  individually `--ignore-vuln`'d and named in the workflow itself -- both
  are exact-pinned transitive dependencies of `browser-use`, the
  Submission Engine's real browser automation library; confirmed the
  latest available release, 0.13.4, still pins the identical vulnerable
  versions, a genuine upstream constraint rather than a shortcut --
  `pip`/`setuptools` themselves are upgraded before the audit runs,
  fixing 5 real CVEs in each for real -- `setuptools`' vulnerable
  `65.5.0` only ever surfaced on the `windows-latest` CI leg, caught by a
  real CI failure, not assumed), `npm audit` (genuinely clean today,
  added as an unconditional gate), and a new `.secrets.baseline` +
  `scripts/check_secrets_baseline.py` that fails CI if a fresh scan no
  longer matches the committed baseline. Four real bugs found and fixed
  while building the checker, all by actually running the tool rather
  than assuming it would work: `detect-secrets` enumerates scan targets
  via `git ls-files`, not a filesystem walk, so a scratch copy with no
  `.git` silently scans nothing; the baseline file was scanning *itself*,
  treating its own recorded secret-hashes as fresh high-entropy findings
  and snowballing on every regeneration, fixed by excluding
  `.secrets.baseline` from its own scan; and, caught only by a real
  Windows CI failure (two wrong guesses -- line endings, then forced
  UTF-8 -- were tried and ruled out first, each verified against the
  actual failing job's log before moving on), `detect-secrets` reports
  `results` filenames with `\` path separators on Windows and `/`
  everywhere else, so a Linux-generated baseline never matched a fresh
  Windows scan until both sides were canonicalized to `/`.

  Existing `InMemoryRateLimiter` (auth-only, process-local, ADR-0074) and
  the CSRF decision (`SameSite=Lax` cookie, no CSRF token, ADR-0074's own
  documented rationale) were re-examined against this phase's brief and
  **reaffirmed, not reopened or duplicated**.

  24 new backend tests (1349 -> 1368), 0 new frontend tests (no frontend
  code touched this phase); full suite, ruff, both import-linter
  contracts, and the frontend's type-check/lint/test/build all still
  green. Zero changes to any existing route's status codes, response
  bodies, or business logic.

- ✅ **Browser Automation Robustness -- ADR-0080 (Phase 62).** Continuing
  Phase 61's hardening-not-features direction into the part of this
  project most likely to fail silently against a real, live ATS
  posting -- it had never been exercised against one. The audit found
  zero retry logic anywhere (`agents/planner/execution_plan.py`'s own
  `max_retries` field is declared plan metadata, its docstring stating
  outright it is "not enforced ... anywhere in this codebase"), zero
  failure capture (no screenshot/HTML/console-log anywhere in
  `integrations/`/`agents/`), and -- the most consequential finding --
  `BrowserApplicator._click_submit_and_check_challenge()` and both of
  `resume()`'s click-completing paths had **no exception handling at
  all**, leaving the browser open and unclosed on any failure there.
  Never-submit-twice (`domain/execution.py`'s `execute_allowed()`,
  ADR-0050, plus the CLI's own pre-tailoring idempotency guard,
  ADR-0048) confirmed already real and settled -- not reopened or
  duplicated.

  `integrations/browser/retry.py` (new, no `tenacity` dependency --
  the same "a small helper beats a library" precedent
  `core/logging_config.py`'s `JsonFormatter` already established):
  `retry_async()` wraps only `_open_page`'s `page.goto()` and
  `submit()`'s pre-click field-fill step, retrying up to 3 times on a
  real `playwright.async_api.TimeoutError`. **The submit click itself
  is never wrapped in retry** -- its own docstring states why directly:
  retrying it risks a second real-world submission if the first attempt
  actually succeeded but the response was slow, exactly the ambiguity
  the never-submit-twice guarantee exists to prevent.

  `integrations/browser/diagnostics.py` (new): `ConsoleLogCollector`
  (attached to every page `_open_page` creates, bounded to the last 500
  lines) and `capture_failure_diagnostics()` (screenshot + `page.
  content()` + the collected console log, written to
  `<diagnostics_dir>/<correlation_id>_<timestamp>/`) -- best-effort by
  construction, every capture step swallows its own exceptions so a
  failure while diagnosing a failure never masks the real one. Wired
  into `BrowserApplicator` via a new `_fail_with_diagnostics()` helper
  at all three browser-touching failure points (closing the resource
  leak found in the audit as a direct byproduct). `diagnostics_dir`
  defaults to `None` (capture disabled) -- every existing caller/test
  keeps today's exact behavior unless it opts in; `SubmissionEngine`/CLI
  wire `Path(settings.artifacts_dir) / "browser_failures"` through by
  default. `SubmissionResult` gains one additive, optional field
  (`diagnostics_dir: str | None`), read off the caught exception's own
  new `diagnostics_dir` attribute in `SubmissionEngine.submit()`'s two
  `except` blocks and a new catch-all added to `_resolve_pause()`
  (mirroring `submit()`'s own "an exception during a click doesn't
  prove it never fired, so it's `UNKNOWN`" reasoning exactly -- a gap
  found while implementing this, since `_resolve_pause()` previously
  caught only the two "not yet resolved" pause exceptions and let
  anything else propagate uncaught).

  16 new backend tests (1368 -> 1384): pure-asyncio tests proving
  `retry_async`'s exact contract (succeeds first try, recovers after
  N-1 failures, exhausts and re-raises, never retries a non-matching
  exception type); real-Chromium tests proving diagnostics capture
  actually writes a real screenshot/HTML/console-log file (and degrades
  gracefully, never raising, when the page is already closed); a
  real-Chromium test proving the retry wrapping *actually recovers*
  from two injected transient timeouts before succeeding, not just
  compiles; and an end-to-end `SubmissionEngine` test proving
  `SubmissionResult.diagnostics_dir` is populated from a real browser
  failure through the full engine, not only at the `BrowserApplicator`
  layer. `tests/integrations/test_browser_purity.py`'s import allowlist
  (the enforced "zero domain knowledge" contract for
  `integrations/browser/`, ADR-0065) gained four legitimate stdlib
  entries (`collections`/`dataclasses`/`datetime`/`logging`) the new
  diagnostics module needs -- none weaken the guarantee it enforces.
  0 new frontend tests (no frontend code touched this phase). Zero
  changes to `BrowserApplicator`'s existing pause/resume/challenge/
  refusal semantics, the headed-by-design (`headless=False`) Chromium
  launch default (ADR-0076's own prior decision, not reopened), or any
  authentication/organization logic.

- ✅ **Web-Triggered Discover, Review, and Submit -- ADR-0081 (Phase 63).**
  Explicit direction: move the interface to the web, never the business
  logic -- retire the CLI-only boundary ADR-0072 drew for Discover,
  Review, and Submit before authentication/RBAC existed. The audit found
  `GET /api/reviews/pending`'s `approval_status == "WAITING"` filter has
  always returned an empty list in production -- no code path in this
  codebase ever produces a `WAITING` `ReviewSession`
  (`ReviewEngine.review()` only ever returns
  APPROVED/REJECTED/CANCELLED/TIMEOUT) -- a genuine, pre-existing bug
  fixed here by redefining "pending" as a `READY_FOR_REVIEW`
  `ApplicationSession` with no recorded decision yet. `MasterProfile` has
  no per-user API store anywhere (unlike `JobPreferences`, which got one
  in Phase 46/56) -- resolved by reusing the CLI's own
  `Path("profile.json")` default rather than inventing a new store,
  consistent with this project's continued single-operator profile
  framing (ADR-0000/ADR-0078).

  `POST /discover` runs `build_discovery_sources`/`run_discover_command`
  -- the CLI's own functions, unmodified in behavior, given two new
  optional observation hooks (`on_new_opportunity`/`on_source_error`,
  both default `None` and skipped by every existing caller) so a caller
  that can't inspect the function's return value can still build a
  status summary -- inside a `BackgroundTasks` job, polled via a new
  `DiscoveryRun` domain model + `SqliteDiscoveryRunStore` (a real upsert,
  like `SqliteUserPreferencesStore` -- a run's status genuinely changes
  in place). `GET /discover/opportunities` reads a new
  `SqliteOpportunityRepository.list_recent()` (`ORDER BY rowid DESC
  LIMIT ?`, no schema migration -- opportunities have no timestamp
  column). Search preferences are read from the caller's existing
  `JobPreferences` (`GET`/`PUT /user/preferences`) -- no second
  configuration surface invented.

  `POST /reviews/decide` calls
  `ReviewEngine().review(session, input_fn=lambda _: "y" if approved
  else "n")` -- the exact class `career-agent review` uses, only the
  `input_fn` seam swapped; one decision per session is enforced (409 on
  a second attempt for the same session, matching the append-only
  `review_sessions` table). The whole `reviews.py` router moves off
  `/api/reviews` onto `/reviews` (mixed GET/POST, the same "one feature,
  one prefix" shape `notifications.py`/`team.py` already established),
  since it now carries a real decision-making action.

  The highest-risk piece: `cli.py::run_submit_command`'s core (fresh
  re-tailor via `ResumeVariantEngine.build_materials()`, the promptfoo
  gate, then `SubmissionEngine.submit()`) is extracted into
  `submit_prepared_application(...)`, taking already-loaded domain
  objects instead of file paths, so the CLI and the web API can never
  drift apart on what re-tailoring/validation/submission actually does.
  Two structural ordering tests
  (`test_gates_before_constructing_the_live_verifier`,
  `test_no_application_session_check_precedes_llm_wiring`) moved with
  the logic they verify. `SubmissionEngine.submit()`'s `confirm_fn` now
  accepts a plain `bool` *or* an awaitable (checked via
  `inspect.isawaitable`, `await`ed if so -- zero behavior change for
  every existing sync caller, since a plain `bool` is never awaitable);
  the web path supplies an `async def confirm_fn()` that awaits a
  bounded `asyncio.Future` (5-minute timeout), translating a timeout
  into `CancelledByUserError` -- `submit()`'s *existing*
  `except (KeyboardInterrupt, CancelledByUserError)` handling needed
  zero new code. A new `auto_close_on_pause` flag on
  `submit()`/`_resolve_pause()` (default `False`, unchanged CLI
  behavior) closes a paused browser and returns `UNKNOWN` with a clear
  message instead of blocking a background task on a second `input()`
  prompt nobody can answer, when the browser pauses for direct human
  interaction (a login wall, a challenge) after confirmation -- the
  Browser Automation Monitor that would let a web caller resolve a pause
  interactively is named as its own future phase, not solved here.

  `api/routers/submission_actions.py` (`/submissions`, off `/api/`):
  `POST /submissions/prepare` starts a background task running
  `submit_prepared_application` and returns a token immediately (HTTP
  202); the pending entry (in-memory, module-level dict, never
  persisted -- tied to a live asyncio `Task` that can't survive a
  process restart anyway, the same reasoning
  `BrowserApplicator`'s own pause-token dict already relies on) tracks
  `PREPARING -> AWAITING_CONFIRMATION -> SUBMITTING -> DONE|FAILED`.
  `POST /submissions/{token}/confirm` resolves the same `asyncio.Future`
  the background task's `confirm_fn` is blocked awaiting -- declining,
  double-confirming, or confirming out-of-turn are all refused (404/409),
  never silently re-triggering anything. Both routes are declared
  `async def` deliberately (not plain `def`): FastAPI runs `async def`
  routes directly on the main event loop -- the same loop the background
  task runs on -- so the coordinating `Future` is only ever touched from
  one thread; a plain `def` route would run in a worker thread pool
  instead, making it thread-unsafe.

  34 new backend tests (1384 -> 1418): domain/storage tests for
  `DiscoveryRun`/`SqliteDiscoveryRunStore`/`list_recent`, API tests for
  all three routers (including a real Chromium test proving
  `auto_close_on_pause` actually closes the browser on a real challenge
  pause, and coroutine-level tests driving `confirm_fn`'s asyncio
  coordination directly -- a full live two-step HTTP round trip can't be
  observed through `TestClient`, which blocks until the entire ASGI
  cycle including background tasks completes). Every existing safety
  gate (human review, human confirmation, fail-closed execution,
  never-submit-twice) verified unchanged by running the full
  pre-existing `test_submission_engine.py`/`test_cli_submit.py`/
  `test_cli_discover.py` suites unmodified except the two structural-test
  relocations noted above.

  Frontend wiring shipped in the same phase: Search Jobs (a real filter
  form bound to Job Search Preferences via the existing
  `PUT /user/preferences`, a Search button that saves then triggers a
  run, a polled status callout, and a real results list from
  `GET /discover/opportunities` -- "Prepare via CLI" stays an honest
  `CliOnlyAction` hint, tailoring's own real headed-browser complexity
  not migrated here); Review Queue (`GET /reviews/pending` now renders
  directly -- no join needed, since a pending item *is* the
  `ApplicationSession` -- with an inline Approve/Reject-then-confirm
  step before `POST /reviews/decide` fires); Submission Queue (Submit
  starts `POST /submissions/prepare`, polls status, and shows a real
  Confirm/Cancel step once `AWAITING_CONFIRMATION` is reached, calling
  `POST /submissions/{token}/confirm`). `lib/derive.ts`'s
  `joinReviewsWithSessions` (Phase 55) was removed as genuinely dead
  code once Review Queue stopped needing it. 14 new frontend tests.
  `career-agent prepare` (tailoring) is the only workflow `CliOnlyAction`
  still names.

  Analytics overhaul/Interview Tracking/Email Integration/Calendar
  Integration/Kanban Application Pipeline/Browser Automation Monitor
  (items 4-7, 9-10 of the originating request) are tracked separately,
  named below, not folded into this already-large phase.

- ✅ **Per-User Master Profile + Web Onboarding Wizard -- ADR-0082
  (Phase 64).** The start of the v2.0 program: "a normal user should
  never need to open a terminal." Three ADRs (0017, 0078, 0081)
  independently named this exact moment as the correct time to give
  `MasterProfile` a real per-user store, mirroring
  `SqliteUserPreferencesStore` -- this phase executes that named trigger
  rather than reopening it. The audit found `storage/profile.py`'s pure
  functions (`_validate_ids`, the `_map_*` mappers, `_content_hash`) were
  already separated from file I/O, so a second, DB-backed source could
  reuse them directly once made independently callable --
  `_content_hash` renamed to public `compute_profile_version`, plus a
  new `validate_master_profile_ids(profile)` wrapper reusing
  `_validate_ids` against `profile.model_dump(mode="json")` (the raw
  JSON Resume shape and the Pydantic dump share the same `"id"` key, so
  one loop validates both). ADR-0017 suggested a `Protocol` as the
  eventual resolution; deliberately not built here -- the CLI always
  uses the file loader, the API always uses the DB store, and no call
  site needs to be implementation-agnostic, so a `Protocol` would be
  pure indirection with no beneficiary.

  **Built:** `SqliteMasterProfileStore` (`user_id`/`payload`/
  `updated_at`, upsert via `INSERT ... ON CONFLICT DO UPDATE`, mirrors
  `SqliteUserPreferencesStore` field-for-field) plus a new
  `api/routers/master_profile.py` (`GET`/`PUT /user/master-profile`)
  deliberately kept separate from `user.py`'s existing
  `PUT /user/profile` -- that endpoint's own docstring already warns
  against conflating "account profile" (display name) with
  `MasterProfile` (candidate data). The `PUT` request body omits
  `version` entirely so a client-submitted value can never masquerade as
  real; the server always recomputes it via `compute_profile_version`.

  Frontend: `useMasterProfile`/`useUpdateMasterProfile` (TanStack Query)
  and a new 8-step `OnboardingWizardPage` (Welcome / Personal / Work /
  Education / Skills / Projects / Legal / Review) built on
  `react-hook-form` + `useFieldArray` for the repeatable work/education/
  skills/projects sections, pre-filling from any existing stored profile
  (idempotent re-entry, not a one-time-only flow). The Review step links
  out to the existing Job Preferences (Search Jobs page) and Notification
  Settings pages rather than duplicating either -- those already have
  working, separate flows from Phase 46/56 and Phase 58. Routed at
  `/onboarding`, added to the account nav as "Master Profile".

  CV upload and the `import-cv`/`promote-cv` migration -- which needs
  genuinely new multipart-upload infrastructure (none exists anywhere in
  `api/` today) and a `domain/ingestion.py`-backed `FactProposal` review
  UI -- is explicitly deferred to a dedicated future phase, not silently
  dropped, matching the "Prepare via CLI" honest-narrowing precedent from
  Phase 63.

  13 new backend tests, 3 new frontend tests. The CLI's `profile.json`/
  `setup`/`import-cv`/`promote-cv` workflow and every `--profile` flag
  are completely unchanged -- the two profile sources (CLI file, web DB
  store) are independent by design, never synchronized or merged.

---

## Deferred work (named, not forgotten)

### v1.1 backlog (Phase 39 post-release operability audit)

Evidence-based, not speculative -- each was reproduced or found by direct
code/doc inspection during Phase 39's first-run/installation audit.

- ✅ **P1 — Promptfoo/results-dir resolution breaks for any non-editable
  install. RESOLVED Phase 40 (ADR-0060).** `_DEFAULT_PROMPTFOO_RESULTS_DIR`
  (`cli.py`) was computed from `Path(__file__).resolve().parent.parent
  .parent`, which only landed on the real repo root for an **editable**
  install; a wheel or a plain `pip install .` copies the package into
  `site-packages`, so the path resolved to a nonsensical
  `site-packages/promptfoo/results` location -- reproduced live: a fresh
  wheel install run from outside the repo confirmed the broken path.
  Fixed by consistency with `database_path`/`artifacts_dir`'s existing
  pattern: `Settings` gains `promptfoo_results_dir` (CWD-relative,
  `.env`-overridable); `_REPO_ROOT`/`_DEFAULT_PROMPTFOO_RESULTS_DIR`
  deleted; every command (`setup`/`apply`/`auto`/`verify-promptfoo`/
  `diagnose-promptfoo-drift`) resolves from the same `Settings` field.
  Re-verified live on both an editable install and a fresh wheel install
  from outside the repo -- both now report the correct CWD-relative path.
- **P2 — Canonical profile JSON shape was undocumented until this phase.**
  Root-caused: the real loader (`load_master_profile` -> `_map_work`)
  expects JSON Resume's camelCase `startDate`/`endDate`; the Pydantic
  model's own fields are snake_case `start_date`/`end_date`. Nothing
  shipped an example showing the (correct) camelCase shape -- this exact
  gap caused real, extended trial-and-error during the Phase 36 live smoke
  (both the user's and this agent's own synthetic-fixture debugging).
  **Fixed in this phase**: README now ships a loader-verified example
  (`test_readme_work_entry_example_loads_through_the_real_cli_loader`).
  Tracked here in case a fuller "profile authoring guide" is ever
  warranted beyond the one example.
- **P2 — No opportunity-file authoring example.** The primary supported
  path (`discover --out-dir` writing handoff files `apply` consumes
  directly) doesn't require a user to hand-author one, so this is lower
  priority than originally suspected -- but no example exists for the
  synthetic/manual-testing case documented in ADR-0058/Phase 36. Consider
  a short example alongside the profile one if manual opportunity
  authoring turns out to be a real user path.
- **P3 — macOS remains untested.** Unchanged deliberate gap (ADR-0056/0057,
  10x CI runner-minute multiplier). Revisit only if a macOS-specific defect
  is ever actually reported.
- **P3 — Whitespace-only provider key is truthy and selects a provider.**
  Unchanged, low-severity, already documented and pinned by test since
  Phase 29 (`test_whitespace_only_key_is_treated_as_present_documented_
  limitation`) -- fails closed at the live call (401), never a silent
  truthfulness bypass. Not re-prioritized by this audit; no new evidence
  changes its severity.
- **P3 — GitHub Release publication.** Confirmed `RELEASE_PENDING` (real
  404, not inferred) as of Phase 38/39. A manual, separate maintainer
  action once GitHub's API rate limit resets -- not a repository defect.

Items explicitly scoped out of the numbered phases above, with a recorded reason
— tracked here so they don't quietly reopen an already-"done" phase.

- **Company Watchlist / Proactive Career Page Monitoring.** Deferred from Phase
  4 (see the named-gap note above). Distinct from job *discovery*: proactively
  finding and watching the career pages of companies with no currently-visible
  postings, so a listing is caught the moment it appears rather than only when
  it surfaces via a known ATS or search. Needs its own pre-brief when prioritized
  — not a Phase 4 patch.
