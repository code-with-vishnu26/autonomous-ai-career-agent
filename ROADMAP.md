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

## ⬜ Phase 4 — Discovery Engine
Discovery Agent + first opportunity sources: Greenhouse / Lever / Ashby ATS APIs,
then YC `hiring.json` + Hacker News, then Career Page Finder + ATS Detector, then
the provider-abstracted search layer (Exa + Google CSE failover).
**Done when:** real openings can be discovered and normalized into `Opportunity`
records, ToS-respecting, with tests.

## ⬜ Phase 5 — JSON Resume master profile
The structured master profile (JSON Resume schema), its loader/validator, and the
**fabrication-detection gate** scaffolding that later grounds all generated
content.
**Done when:** a validated profile loads and the grounding contract is defined.

## ⬜ Phase 6 — ATS adapters
Concrete ATS adapters registered as plugins for reading postings and (where
supported) submitting applications.
**Done when:** adapters plug in via the registry with no core changes, with tests.

## ⬜ Phase 7 — Application engine
Resume Agent + Apply Agent: truthful tailoring through the cost cascade, the
fabrication gate as a hard blocker, and the tiered/supervised applicator
(API → browser → email), with throttling and human-in-the-loop pauses.
**Done when:** an application can be assembled, gated for truthfulness, and
submitted under supervision.

## ⬜ Phase 8 — Learning engine
Learning Agent: capture outcomes and feed them back into scoring, targeting, and
tailoring.
**Done when:** outcomes are recorded and demonstrably influence prioritization.

## ⬜ Phase 9 — Dashboard
Local visibility into the pipeline: status, decisions, and exports (SQLite +
openpyxl spreadsheet).
**Done when:** the user can see and audit what the agent is doing.

## ⬜ Phase 10 — Deployment
Self-hosting story: configuration, secrets handling, scheduling, and docs to run
it reliably on the user's own machine.
**Done when:** a new user can stand the agent up from the README.
