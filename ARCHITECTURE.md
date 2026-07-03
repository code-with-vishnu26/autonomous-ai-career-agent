# Architecture

This document describes the high-level architecture of the Autonomous AI Career
Agent. It is the canonical reference for *how the system is shaped*; specific
decisions and their rationale are recorded as ADRs in [`docs/adr/`](docs/adr/).

> **Status:** This describes the *target* architecture. It is being realized one
> phase at a time (see [`ROADMAP.md`](ROADMAP.md)). Interfaces named here are
> finalized in Phase 2.

---

## 1. Design philosophy

The project's mission, goals, non-goals, and golden rules are fixed in
[ADR-0000](docs/adr/0000-project-philosophy.md) — the root every other decision
serves. The system is **agent-oriented, not a fixed pipeline** (see
[ADR-0001](docs/adr/0001-agent-oriented-architecture.md)). Rather than hard-coding
a linear `discover → decide → apply → learn` flow, a central **Planner Agent**
reasons about state and decides what to do next, dispatching work to specialized
agents. This lets the system reprioritize, retry, and incorporate new capabilities
without rewriting a brittle pipeline.

Two cross-cutting commitments shape everything:

1. **Truthfulness is non-negotiable.** All applicant-facing content is grounded in
   the user's structured master profile. A fabrication-detection gate is a hard
   blocker, not a warning.
2. **Human-in-the-loop where it matters.** Applying is supervised. The agent
   pauses for the human on CAPTCHAs, verifications, and final submission per the
   user's policy.

## 2. System overview

```
                          ┌─────────────────────────┐
                          │      Planner Agent       │
                          │  (the brain: plan, route │
                          │   prioritize, retry)     │
                          └────────────┬─────────────┘
                                       │ dispatches tasks
        ┌──────────────┬───────────────┼───────────────┬──────────────┐
        ▼              ▼               ▼               ▼              ▼
 ┌────────────┐ ┌────────────┐  ┌────────────┐  ┌────────────┐  (future
 │ Discovery  │ │  Resume    │  │   Apply    │  │ Learning   │   agents
 │  Agent     │ │  Agent     │  │   Agent    │  │  Agent     │   register
 └─────┬──────┘ └─────┬──────┘  └─────┬──────┘  └─────┬──────┘   here)
       │              │               │               │
       └──────────────┴───────┬───────┴───────────────┘
                              ▼
        ┌───────────────────────────────────────────────┐
        │       Plugin Registry  +  Event Bus            │
        │  (capabilities self-register; agents talk via  │
        │   published/subscribed events, not direct calls)│
        └───────────────────────┬───────────────────────┘
                                ▼
   ┌───────────┬───────────┬───────────┬───────────┬───────────┐
   │ ATS       │ Opportunity│ Search    │ LLM       │ Storage / │
   │ adapters  │ sources    │ providers │ (Claude   │ Gmail /   │
   │ (GH/Lever │ (YC, HN,   │ (Exa,     │ cascade)  │ Browser   │
   │  /Ashby)  │ career pgs)│ Google)   │           │           │
   └───────────┴───────────┴───────────┴───────────┴───────────┘
```

## 3. Agents

### Planner Agent (the brain)
Decides *what to do next* given current state: which opportunities to discover,
which are worth pursuing, when to tailor a résumé, when to apply, and how to react
to failures. Owns prioritization, retry/backoff policy, and the cost cascade
budget. Implemented on **LangGraph** so its decision loop is inspectable and
resumable.

### Discovery Agent
Finds real openings. Strategy order (open-ended; web-search layer is specified in
[ADR-0002](docs/adr/0002-search-provider-abstraction.md)):
1. Public ATS JSON APIs — **Greenhouse, Lever, Ashby**.
2. **YC `hiring.json`** and **Hacker News "Who's Hiring."**
3. Company **career pages** found via a *Career Page Finder* + *ATS Detector*.
4. Provider-abstracted **web search** (Exa + Google CSE, with failover).
Job boards are used **only within their ToS**.

### Resume Agent
Tailors a résumé for a specific opportunity using **only** facts from the master
profile (JSON Resume schema). Routes generation through the Claude cost cascade.
Every output passes the **fabrication-detection gate** before it can be used.

### Apply Agent
Submits applications through a **tiered applicator**:
1. **Direct ATS API** where available.
2. **Driven browser** (Playwright + Browser-Use) otherwise.
3. **Email-to-apply** via the Gmail connector as a fallback.
Throttled and supervised: pauses for the human to clear CAPTCHA/verification,
reuses a session established by manual login, and never automates Google OAuth.

### Learning Agent
Records outcomes (responses, rejections, interviews) and feeds them back into
scoring, targeting, and résumé-tailoring quality. Closes the loop.

## 4. Communication: Plugin Registry + Event Bus

Agents do **not** call each other directly. They communicate through an **event
bus** (publish/subscribe) and discover capabilities through a **plugin registry**.

- **Plugin registry** — ATS adapters, opportunity sources, and search providers
  register themselves against well-known extension points. Adding a new provider
  is a plugin, not a core edit.
- **Event bus** — agents emit events (e.g. `OpportunityDiscovered`,
  `ResumeTailored`, `ApplicationSubmitted`, `OutcomeRecorded`) and subscribe to
  the ones they care about. This keeps agents decoupled and the system extensible.

These two mechanisms are the heart of "no core rewrites" and are built in
**Phase 3**, before any capability agent.

## 5. LLM usage — cost cascade

All model calls go through a single Claude client that implements a
**Haiku → Sonnet → Opus** cost cascade: cheap models handle routine work and the
system escalates to more capable (more expensive) models only when a task needs
it. Prompts are **versioned in git** and guarded by **promptfoo** regression
tests so prompt changes can't silently regress behavior.

## 6. Data & integrations

- **Storage:** SQLite is the system of record; **openpyxl** produces
  human-readable spreadsheet exports (application tracker, pipeline).
- **Master profile:** a single structured **JSON Resume** document — the sole
  source of truth for anything that appears in an application.
- **Gmail connector:** sending email-to-apply and (later) reading responses.
- **Browser:** Playwright + Browser-Use, driven under human supervision.

## 7. Extensibility model (the contract)

A new capability should require **only**:
1. A plugin that registers against an existing extension point, and
2. Subscribing/publishing the relevant events.

If adding an ATS, a source, or a search provider ever requires editing core
orchestration code, that is a design smell to be recorded and corrected via an
ADR. Major interface or structural changes are discussed before implementation.

## 8. Repository layout

See [`ROADMAP.md`](ROADMAP.md) for the phase that introduces each part.

```
src/career_agent/
├── domain/        # pure data models + business rules, zero I/O (ADR-0006, ADR-0011)
├── core/          # event bus, plugin registry, interfaces, config
├── agents/        # planner + discovery/resume/apply/learning
├── plugins/       # ats adapters, opportunity sources, search providers
├── llm/           # Claude client + Haiku→Sonnet→Opus cascade
├── storage/       # SQLite repositories + openpyxl exports
├── integrations/  # Gmail, browser (Playwright/Browser-Use)
└── cli.py         # entry point
tests/             # mirrors src/
docs/adr/          # architecture decision records
```

## 9. Decision records

The architecture above is the consequence of a set of explicit, recorded
decisions. Read the ADRs for the *why*; they are the contract every feature and
pull request is checked against.

| ADR | Decision |
|-----|----------|
| [0000](docs/adr/0000-project-philosophy.md) | Project philosophy — mission, goals, non-goals, golden rules (the root) |
| [0001](docs/adr/0001-agent-oriented-architecture.md) | Agent-oriented architecture; agent design principles + lifecycle |
| [0002](docs/adr/0002-search-provider-abstraction.md) | Search provider abstraction; capability discovery + health-based ranking |
| [0003](docs/adr/0003-truthfulness-gate.md) | Truthfulness gate; per-statement evidence, confidence, explainability |
| [0004](docs/adr/0004-plugin-architecture.md) | Plugin architecture; everything external is replaceable |
| [0005](docs/adr/0005-event-bus.md) | Event bus; loose coupling, no direct agent-to-agent calls |
| [0006](docs/adr/0006-json-resume-master-profile.md) | JSON Resume master profile; single source of truth |
| [0007](docs/adr/0007-planner-agent.md) | Planner Agent; coordinator only, Decide as a swappable step |
| [0008](docs/adr/0008-human-in-the-loop.md) | Human-in-the-loop applying; pause, never bypass |
| [0009](docs/adr/0009-learning-engine.md) | Learning engine; improve from real outcomes |
| [0010](docs/adr/0010-hybrid-application-strategy.md) | Hybrid tiered applicator; ATS API → browser → email |
| [0011](docs/adr/0011-structured-tailored-content.md) | Structured tailored resume content; not free text |
| [0012](docs/adr/0012-opportunity-provenance-and-confidence.md) | Opportunity provenance + extraction confidence; honest uncertainty for freeform sources |
| [0013](docs/adr/0013-held-candidate-mechanism.md) | Held-candidate mechanism; freeform sources hold ambiguous input with a visible discard pile |
| [0014](docs/adr/0014-cross-source-opportunity-identity.md) | Cross-source opportunity identity; two-key dedup + canonical company, decided against real multi-source data |
| [0015](docs/adr/0015-web-search-classification.md) | Web-search results are classified, not trusted; a matched ATS URL is confirmed by re-parsing, never trusted on shape alone |
| [0016](docs/adr/0016-truthfulness-gate-verification.md) | Truthfulness gate verification; entailment over keyword matching, the category rubric, and the five-control harness around the first model-judged safety component |
| [0017](docs/adr/0017-master-profile-loader.md) | Master profile loader; required per-entry ids rejected-not-inferred, version scoped to grounding fields only, plain function over a speculative Protocol |
| [0018](docs/adr/0018-submission-safety.md) | Submission safety; SubmittableApplication makes an unapproved submission type-level impossible, confirmation is a token bound to one exact preview, AnthropicClaimVerifier isolation is import-linter-enforced |
| [0019](docs/adr/0019-ats-kind-resolution-and-tier-fallback.md) | ATS-kind resolution via the reused ADR-0015 URL pattern-match (no new CompanyRepository); tier fallback never auto-cascades under one confirmation |
| [0020](docs/adr/0020-browser-tier-session-and-pause.md) | Browser-tier session encryption (OS-keychain key, fail-closed on unavailability) and a token-bound pause/resume that re-verifies the live page, not just the acknowledgment |
| [0021](docs/adr/0021-email-tier-draft-only.md) | Email tier is draft-only by interface design (EmailDraftSink has no send method); submit() always returns HumanActionRequired, never claims ApplicationSubmitted |
| [0022](docs/adr/0022-resume-generator.md) | ResumeGenerator; summary sourced read-only from the profile (never drafted), missing summary rejected loudly not derived, ContentDrafter scoped narrow but not permanently cascade-exempt, no self-verification |
| [0023](docs/adr/0023-resume-tailoring-pipeline.md) | Resume-tailoring pipeline; composition stops before Applicator (canary-checked), Application gains a "rejected" status distinct from "failed", dormant Phase 2 events (ResumeTailored/TruthfulnessRejected) finally get emitted |
| [0024](docs/adr/0024-real-confirmation-and-submission-wiring.md) | Real human confirmation (cli.confirm_submission, verified no default-to-yes) drives a real, single-tier SubmissionPipeline for the first time; multi-tier selection confirmed never built, named as deferred work |
| [0025](docs/adr/0025-resume-renderer.md) | Resume renderer; computed once where content+profile are both in scope (ResumeTailoringPipeline, no Applicator changes needed), raises loudly on an unresolvable entry rather than silently dropping it (verified to catch a regression) |
| [0026](docs/adr/0026-real-apply-command-and-promptfoo-enforcement.md) | Real `career-agent apply` command; --opportunity-file JSON handoff (no premature storage design), promptfoo pass positively verified against a results artifact keyed to the exact prompt version (never a claimed flag) before AnthropicClaimVerifier is constructed, stops cleanly at confirmation since no real ATSAdapter exists yet |
| [0027](docs/adr/0027-applicant-identity-snapshot.md) | Applicant identity snapshot; Application.applicant is a required, frozen BasicsSection preventing prepare/submit identity drift, BrowserApplicator._fill_form now uses real profile data with a documented known-imprecise name split, and Tier 1 direct-API submission is confirmed dead (employer-issued credentials required) across Greenhouse/Lever/Ashby |
| [0028](docs/adr/0028-browser-tier-dispatch-and-unsupported-field-refusal.md) | Browser-tier per-ATS dispatch via resolve_ats_kind (Lever/Ashby stubbed, real selectors unverifiable from two independent attempts); live-DOM-verified refusal of any required field no FormFiller knows how to fill; custom-questions/EEOC answering explicitly deferred to its own ADR, with an absolute leave-blank-or-human-originates-only rule stated now for EEOC fields |
| [0029](docs/adr/0029-per-filler-challenge-and-submit-selectors.md) | Per-FormFiller challenge_selector/submit_selector and name-based field matching, both justified by a real, human-inspected live Lever posting (real hCaptcha markup, no-id name-only fields); LeverFormFiller stays a stub pending the still-unconfirmed resume-field interaction shape |
| [0030](docs/adr/0030-greenhouse-coverage-is-narrow.md) | Corrects the record on real Greenhouse coverage: resume_text DOM-confirmed as a real form option, but an ordinary real posting requires Education/legal-status/Voluntary Self-ID/Veteran Status fields GreenhouseFormFiller doesn't fill -- "Tier 2 works" means narrow completion and correct refusal on most postings, not broad completion, re-prioritizing the deferred custom-questions/EEOC design pass |
| [0031](docs/adr/0031-question-answerer.md) | QuestionAnswerer: four custom-question categories built as one shared component (EEOC absolute with no MasterProfile access at all; LegalStatusSection-backed factual yes/no, None-means-uncaptured; always-human-authored subjective; deterministic no-guess dropdown matching with its own DropdownMatchResult type, distinct from ClaimVerdict); deterministic template matching chosen over an LLM call for all four categories; user-authored 20-case adversarial matrix with four load-bearing cases independently verified by injection; DOM-wiring into BrowserApplicator.submit() deliberately deferred |

Every ADR ends with **Future revisit criteria**, so the architecture stays open
to change instead of frozen forever.
