"""The Planner's output shape (Phase 49, ADR-0067).

An inspectable, replayable search plan. Pure data -- no I/O, no adapter
calls, no network. ``ExecutionPlan`` is
what :func:`~career_agent.agents.planner.planner.build_execution_plan`
produces; a future executor (not this phase -- see ADR-0067's non-goals)
walks it and actually calls each ``SearchTask``'s named provider via
:class:`~career_agent.integrations.adapters.registry.AdapterRegistry`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class SearchTask(BaseModel):
    """One planned search: which provider, what query, how many jobs, when.

    ``priority`` is ascending (1 = first); ties are broken by list order.
    ``max_retries`` is declared plan metadata only -- **not enforced by
    anything in this phase**, the same "captured now, not yet wired"
    discipline :class:`~career_agent.domain.job_preferences.JobPreferences`
    already applies to `max_applications_per_day`. There is no execution
    loop anywhere in this codebase yet for a retry policy to govern.
    """

    provider: str
    query: str
    limit: int
    priority: int
    max_retries: int = 0


class ExecutionPlan(BaseModel):
    """An ordered, budget-bounded set of :class:`SearchTask` objects.

    ``stop_reason`` is ``None`` unless the budget actually truncated the
    plan (:mod:`~career_agent.agents.planner.budget`) -- distinguishing
    "every generated task fit" from "some tasks were dropped to stay
    within budget" is the whole reason this field exists rather than a
    caller having to infer it by comparing lengths.
    """

    tasks: list[SearchTask] = Field(default_factory=list)
    total_budget: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    stop_reason: str | None = None
