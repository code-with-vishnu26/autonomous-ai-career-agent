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

---

## Deferred work (named, not forgotten)

Items explicitly scoped out of the numbered phases above, with a recorded reason
— tracked here so they don't quietly reopen an already-"done" phase.

- **Company Watchlist / Proactive Career Page Monitoring.** Deferred from Phase
  4 (see the named-gap note above). Distinct from job *discovery*: proactively
  finding and watching the career pages of companies with no currently-visible
  postings, so a listing is caught the moment it appears rather than only when
  it surfaces via a known ATS or search. Needs its own pre-brief when prioritized
  — not a Phase 4 patch.
