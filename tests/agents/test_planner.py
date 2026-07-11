"""Phase 49 (ADR-0067): build_execution_plan -- the Planner's orchestration.

No I/O anywhere: no network, no adapter call, no LLM, no browser. Every
test constructs preferences and a plain list of provider names -- never a
real :class:`~career_agent.integrations.adapters.registry.AdapterRegistry`
instance, since this module has no adapter-construction knowledge at all
(callers pass ``registry.providers()``, not the registry itself).
"""

from __future__ import annotations

from career_agent.agents.planner.planner import build_execution_plan
from career_agent.domain.job_preferences import JobPreferences


def test_no_titles_configured_returns_an_empty_plan_not_an_error() -> None:
    prefs = JobPreferences(countries=["India"])
    plan = build_execution_plan(prefs, ["greenhouse", "lever"])
    assert plan.tasks == []
    assert plan.stop_reason is None


def test_no_registered_providers_returns_an_empty_plan() -> None:
    prefs = JobPreferences(preferred_titles=["Backend Developer"])
    plan = build_execution_plan(prefs, [])
    assert plan.tasks == []


def test_plan_covers_every_generated_query_and_provider() -> None:
    prefs = JobPreferences(
        preferred_titles=["Backend Developer"],
        work_mode=["remote"],
        countries=["India"],
    )
    plan = build_execution_plan(prefs, ["greenhouse", "lever"], total_budget=100)
    providers_used = {t.provider for t in plan.tasks}
    queries_used = {t.query for t in plan.tasks}
    assert providers_used == {"greenhouse", "lever"}
    assert queries_used == {"Backend Developer Remote", "Backend Developer India"}
    assert len(plan.tasks) == 4  # 2 queries x 2 providers


def test_preferred_ats_providers_are_prioritized_first() -> None:
    """The load-bearing consumer of JobPreferences.preferred_ats_providers,
    documented in ADR-0064 as captured-but-unconsumed until this phase."""
    prefs = JobPreferences(
        preferred_titles=["Backend Developer"],
        preferred_ats_providers=["lever"],
    )
    plan = build_execution_plan(
        prefs, ["greenhouse", "lever", "ashby"], total_budget=100
    )
    assert plan.tasks[0].provider == "lever"


def test_tasks_are_diversified_across_providers_not_exhausted_one_at_a_time() -> (
    None
):
    """Every provider must appear within the first 'round' (one per query)
    before any provider repeats -- proves diversification, not a plain
    per-provider-then-next-provider ordering."""
    prefs = JobPreferences(
        preferred_titles=["Backend Developer"],
        work_mode=["remote"],
        countries=["India", "UK"],
    )
    plan = build_execution_plan(
        prefs, ["greenhouse", "lever", "ashby"], total_budget=100
    )
    first_round_providers = [t.provider for t in plan.tasks[:3]]
    assert set(first_round_providers) == {"greenhouse", "lever", "ashby"}


def test_priorities_are_sequential_starting_at_one() -> None:
    prefs = JobPreferences(preferred_titles=["Backend Developer"])
    plan = build_execution_plan(prefs, ["greenhouse", "lever"], total_budget=100)
    assert [t.priority for t in plan.tasks] == list(range(1, len(plan.tasks) + 1))


def test_small_budget_truncates_and_sets_stop_reason() -> None:
    prefs = JobPreferences(
        preferred_titles=["Backend Developer", "Python Developer"],
        work_mode=["remote"],
        countries=["India"],
    )
    plan = build_execution_plan(
        prefs, ["greenhouse", "lever", "ashby", "remoteok"], total_budget=2
    )
    assert len(plan.tasks) == 2
    assert plan.stop_reason == "budget_exhausted"


def test_generous_budget_never_truncates() -> None:
    prefs = JobPreferences(preferred_titles=["Backend Developer"])
    plan = build_execution_plan(prefs, ["greenhouse", "lever"], total_budget=1000)
    assert plan.stop_reason is None


def test_max_queries_caps_the_number_of_generated_queries() -> None:
    prefs = JobPreferences(
        preferred_titles=["A", "B", "C", "D", "E"],
        countries=["X", "Y", "Z"],
    )
    plan = build_execution_plan(
        prefs, ["greenhouse"], total_budget=1000, max_queries=2
    )
    queries_used = {t.query for t in plan.tasks}
    assert len(queries_used) == 2


def test_plan_is_fully_deterministic_for_the_same_input() -> None:
    prefs = JobPreferences(
        preferred_titles=["Backend Developer"],
        work_mode=["remote"],
        countries=["India"],
    )
    plan_a = build_execution_plan(prefs, ["greenhouse", "lever"], total_budget=50)
    plan_b = build_execution_plan(prefs, ["greenhouse", "lever"], total_budget=50)
    assert [t.model_dump(exclude={"provider"}) for t in plan_a.tasks] == [
        t.model_dump(exclude={"provider"}) for t in plan_b.tasks
    ]


def test_total_budget_is_recorded_on_the_plan() -> None:
    prefs = JobPreferences(preferred_titles=["Backend Developer"])
    plan = build_execution_plan(prefs, ["greenhouse"], total_budget=42)
    assert plan.total_budget == 42
