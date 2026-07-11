# ADR-0067: Search Planner — a second capability inside the existing Planner boundary

- **Status:** Accepted
- **Date:** 2026-07-11
- **References:** [ADR-0007](0007-planner-agent.md) (Planner boundary,
  Decide as its first delegated capability), [ADR-0038](0038-decide-layer.md)
  (deterministic Decide scoring), [ADR-0064](0064-job-search-preferences-separate-from-profile.md)
  (Phase 46, `JobPreferences`/`generate_search_queries`), [ADR-0066](0066-website-adapter-framework.md)
  (Phase 48, `AdapterRegistry`)

## Context

Phase 49 asks for an "AI Planner": given `JobPreferences`, decide which
providers to search, which keywords, in what priority order, and when to
stop — producing an inspectable `ExecutionPlan` a future executor walks,
rather than a caller blindly calling every source. Explicitly no browser,
no Playwright, no AI/LLM, no form-filling, no submission — "Only
planning."

The repository-reality audit found the name "Planner" is not free to
claim here — `agents/planner/` already exists, and
[ADR-0007](0007-planner-agent.md) (Phase 2, one of this project's
earliest decisions) already named it **"the Planner boundary."** That ADR
described a much larger vision: a LangGraph-based coordinator running
Plan → Delegate → Monitor → Recover → Complete over the *whole* agent
lifecycle, owning a cost-cascade LLM budget (Haiku → Sonnet → Opus),
dispatching typed tasks over the event bus. **That vision was never
built** — confirmed directly: no `langgraph`/`langchain` import exists
anywhere under `src/`. What actually got built and shipped (Phase 14) is
`agents/planner/decide.py`: a small, deterministic, zero-LLM scoring
step, explicitly documented as "the first concrete implementation" of a
"delegated, swappable scoring step" inside that boundary — a much
narrower realization of ADR-0007's original idea, and the one this
project actually kept building on.

## Decision

**A second, distinct capability inside the same existing `agents/planner/`
boundary — not a new top-level `planner/` package, and not the LangGraph
coordinator ADR-0007 originally envisioned.** `Decide` ranks opportunities
*after* discovery; this Planner decides what to search *before* discovery
runs. Both are deterministic, delegated capabilities inside the boundary
ADR-0007 drew, matching how `Decide` itself already narrowed that ADR's
original scope down to something real and shippable.

New modules, flat under `agents/planner/` (matching `decide.py`'s
existing convention, not a subpackage):

- **`execution_plan.py`** — `SearchTask`/`ExecutionPlan`: pure data, the
  plan's own shape.
- **`provider_selector.py`** — `order_providers()`: finally consumes
  `JobPreferences.preferred_ats_providers`, captured in Phase 46
  (ADR-0064) but explicitly documented there as "not yet consumed" —
  this is that named, deferred gap, closed.
- **`budget.py`** — `allocate_limits()`/`apply_budget()`: how many jobs a
  plan targets, and truncation (lowest-priority tasks dropped, never
  silently zeroed) when task count exceeds budget.
- **`planning_rules.py`** — `deduplicate_tasks()`: drops exact
  `(provider, query)` duplicate *tasks* — a different, narrower concern
  than opportunity dedup, which already exists unchanged at
  `SqliteOpportunityRepository.add` (ADR-0014).
- **`planner.py`** — `build_execution_plan()`: the orchestrator tying the
  above together.

### No `keyword_expander.py`

The brief's file list includes one. **Deliberately not created.**
`domain.job_preferences.generate_search_queries` (Phase 46) already *is*
keyword expansion (title × location combinations, exclude-keyword
filtering, capped and deterministic) — a second module that only called
that one function would be a pass-through wrapper adding a name, not a
capability, the same "don't add an abstraction with nothing behind it"
discipline this project applies everywhere. `planner.py` imports and
calls it directly.

### No `strategy.py`

Diversification (the brief's explicit "search diversification"
responsibility) is folded into `build_execution_plan`'s own task-assembly
loop rather than a separate file: queries are the outer loop, providers
(already priority-ordered) the inner loop, so priority 1..N spreads
across every provider once before repeating for the next query — a
provider never accidentally consumes the whole budget just by appearing
first in a flat list. This is one cohesive assembly step, not a
independently-swappable "strategy," so it did not earn its own module.

### Budget is not `max_applications_per_day`

`JobPreferences.max_applications_per_day` (Phase 46) governs real
applications *submitted* per day — not yet enforced anywhere.
`SearchBudget`/`apply_budget` here govern how many job postings one
*discovery planning cycle* targets *fetching*. These are deliberately
kept separate: a user could easily want to discover 200 postings to
review while only applying to 3 a day. Conflating them would silently
misapply an application-rate limit to an unrelated search-volume
decision.

### Retry policy: declared, not enforced

`SearchTask.max_retries` exists on the model (the brief names "retry
policy" as a Planner responsibility) but nothing in this phase executes
a plan at all — there is no I/O anywhere in this package, verified by a
purity test (below). Declaring it now, unenforced, matches
`JobPreferences.max_applications_per_day`/`require_human_confirmation`'s
own "captured now, not yet wired" precedent from Phase 46 — never a
silent overclaim.

### Purity, enforced not asserted

Every new module is provably free of I/O: an AST-based test scans for
`httpx`/`requests`/`playwright`/`asyncio`/`socket` imports and any
`async def` across all five files — none exist. No adapter is
constructed anywhere in this package; `build_execution_plan` takes a
plain `list[str]` of provider names (typically
`AdapterRegistry.providers()`), never the registry itself, so this
package has zero adapter-construction knowledge.

## What this phase explicitly does not do

No executor — nothing in this codebase walks an `ExecutionPlan` and
actually calls an adapter's `search()` yet; that is a deliberate, future,
separate decision (wiring `career-agent discover` to consume plans
requires its own composition-root design, the same reasoning Phase 48
gave for not wiring `AdapterRegistry` into `build_discovery_sources`
either). No CLI command. No AI/LLM call of any kind. No change to
`Decide`, `BrowserApplicator`, `AdapterRegistry`, or the execution-safety
boundary.

## Consequences

- Five new modules under `src/career_agent/agents/planner/`.
- 33 new tests, flat under `tests/agents/` (matching `test_decide.py`'s
  existing location convention, not a new subdirectory): per-module unit
  tests, `build_execution_plan` integration tests (diversification,
  priority ordering, budget truncation, determinism), and two purity
  tests.
- No new dependency, no version bump, no change to `domain/
  job_preferences.py`, `integrations/adapters/`, or `agents/planner/
  decide.py`.

## Future revisit criteria

Revisit when a future phase builds the executor that actually walks an
`ExecutionPlan` and calls `AdapterRegistry`-resolved adapters — that is
the natural point to decide whether `max_retries` becomes real, whether
`career-agent discover` is rewired to consume plans instead of
`build_discovery_sources`'s current independent wiring, and whether the
originally-envisioned LangGraph coordinator (ADR-0007) is ever actually
warranted, now that two real, deterministic Planner capabilities exist to
evaluate that question against.
