"""The search Planner (Phase 49, ADR-0067).

Turns preferences into an executable, budget-bounded plan.

**What this is, precisely -- and what it is not.** ADR-0007 named
``agents.planner`` "the Planner boundary" and described ``Decide``
(``decide.py``, ranking *discovered* opportunities) as its first
concrete, delegated implementation. This module is a second, distinct
capability inside that same boundary: deciding *what to search for*,
*before* discovery runs, not what to do with results after. It is
**not** the LangGraph-based, LLM-cost-cascade coordinator ADR-0007's
original vision described (Plan -> Delegate -> Monitor -> Recover ->
Complete over the whole agent lifecycle) -- that was never built
anywhere in this codebase (confirmed: no ``langgraph``/``langchain``
import exists under ``src/``), and this phase does not build it either.
This is a small, **purely deterministic** function -- no LLM call, no
network, no adapter call, no browser -- consistent with how ``Decide``
itself already works (ADR-0038: "deterministic, weighted, zero LLM
calls").

**Reuses, does not duplicate:** query generation is
:func:`~career_agent.domain.job_preferences.generate_search_queries`
(Phase 46) -- there is no separate ``keyword_expander.py`` in this
package; a second module that only called that one function would be a
pass-through wrapper, not a real capability. Provider awareness is
:class:`~career_agent.integrations.adapters.registry.AdapterRegistry`
(Phase 48) -- callers pass ``registry.providers()``, this module has no
adapter-construction knowledge of its own.
"""

from __future__ import annotations

from career_agent.agents.planner.budget import apply_budget
from career_agent.agents.planner.execution_plan import ExecutionPlan, SearchTask
from career_agent.agents.planner.planning_rules import deduplicate_tasks
from career_agent.agents.planner.provider_selector import order_providers
from career_agent.domain.job_preferences import JobPreferences, generate_search_queries

_DEFAULT_TOTAL_BUDGET = 100


def build_execution_plan(
    preferences: JobPreferences,
    registered_providers: list[str],
    *,
    total_budget: int = _DEFAULT_TOTAL_BUDGET,
    max_queries: int = 10,
) -> ExecutionPlan:
    """Build an :class:`ExecutionPlan` from preferences and known providers.

    Returns an empty plan (``tasks=[]``, ``stop_reason=None``) if
    ``generate_search_queries`` yields nothing (no titles configured) or
    ``registered_providers`` is empty -- nothing to search for or nowhere
    to search is not an error at the planning layer, the same "no
    preference means no constraint, not a failure" discipline
    ``JobPreferences`` itself follows.

    Task ordering diversifies across providers by design (a named Planner
    responsibility per ADR-0067): queries are the outer loop, providers
    (already priority-ordered) the inner loop, so early priorities spread
    across every provider in one "round" before repeating for the next
    query, rather than exhausting one provider's whole query list first
    and starving every other provider if the budget runs out early.
    """
    queries = generate_search_queries(preferences, max_queries=max_queries)
    ordered_providers = order_providers(
        list(preferences.preferred_ats_providers), registered_providers
    )
    if not queries or not ordered_providers:
        return ExecutionPlan(tasks=[], total_budget=total_budget)

    raw_tasks: list[SearchTask] = []
    priority = 1
    for query in queries:
        for provider in ordered_providers:
            raw_tasks.append(
                SearchTask(
                    provider=provider,
                    query=query,
                    limit=0,  # placeholder; apply_budget sets the real limit
                    priority=priority,
                )
            )
            priority += 1

    deduped = deduplicate_tasks(raw_tasks)
    tasks, stop_reason = apply_budget(deduped, total_budget)
    return ExecutionPlan(
        tasks=tasks, total_budget=total_budget, stop_reason=stop_reason
    )
