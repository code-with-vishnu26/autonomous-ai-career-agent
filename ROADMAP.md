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

## ⬜ Phase 6 — JSON Resume master profile
The structured master profile (JSON Resume schema) and its loader/validator —
now built with the gate's real `verify()` already in hand, so the profile model
is validated against what the gate actually needs, not a scaffolding guess.
**Done when:** a validated profile loads and the grounding contract is defined.

## ⬜ Phase 7 — ATS adapters
Concrete ATS adapters registered as plugins for reading postings and (where
supported) submitting applications.
**Done when:** adapters plug in via the registry with no core changes, with tests.

## ⬜ Phase 8 — Application engine
Resume Agent + Apply Agent: truthful tailoring through the cost cascade, the
fabrication gate (Phase 5) as a hard blocker, and the tiered/supervised applicator
(API → browser → email), with throttling and human-in-the-loop pauses.
**Done when:** an application can be assembled, gated for truthfulness, and
submitted under supervision.

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
