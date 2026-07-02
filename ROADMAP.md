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

**Remaining (7b2+), reprioritized by real-world coverage, not slice number:**
Tier 1's real submission APIs likely cover a narrow slice of postings in
practice (most companies only expose a public *read* API, not a submission
one) — so **Tier 2 (browser, Playwright + Browser-Use, session reuse and
CAPTCHA/verification pause points per ADR-0008) is next**, ahead of building
out the remaining Tier 1 adapters, since it is expected to cover most real
applications. Tier 3 (email-to-apply) follows, likely via this environment's
already-connected Gmail integration rather than a new SMTP integration
(direction flagged now, decision deferred to that slice's own pre-brief).
The profile-staleness gap ADR-0018 names must close before any
scheduled/autonomous apply run is built.
**Done when:** adapters plug in via the registry with no core changes, with tests.

## ⬜ Phase 8 — Application engine
Resume Agent + Apply Agent: truthful tailoring through the cost cascade, the
fabrication gate (Phase 5) as a hard blocker, and the tiered/supervised applicator
(API → browser → email), with throttling and human-in-the-loop pauses. The
renderer **must** call `domain.rendering.resolve_work_dates` for every work
entry's dates — never re-derive them another way, never omit them (ADR-0016's
Case #6 correction: the generator can't write a date, but the resume still
has to show the real one).
**Done when:** an application can be assembled, gated for truthfulness, and
submitted under supervision, with real employment dates on every tailored
work entry.

## ⬜ Phase 9 — Learning engine
Learning Agent: capture outcomes and feed them back into scoring, targeting, and
tailoring.
**Done when:** outcomes are recorded and demonstrably influence prioritization.

## ⬜ Phase 10 — Dashboard
Local visibility into the pipeline: status, decisions, and exports (SQLite +
openpyxl spreadsheet).
**Done when:** the user can see and audit what the agent is doing.

## ⬜ Phase 11 — Deployment
Self-hosting story: configuration, secrets handling, scheduling, and docs to run
it reliably on the user's own machine.
**Done when:** a new user can stand the agent up from the README.

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
