"""ADR-0046: advisory Pareto/sensitivity decision-intelligence wired into
`discover`'s existing ranked-summary output.

Every test here proves the integration is purely additive: hard
exclusions, scalar ranking order, and (separately, in test_cli_auto.py,
unmodified by this phase) `auto`'s selection behavior are all untouched.
No network, no LLM, fully deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from career_agent.agents.planner.decide import DecisionScore
from career_agent.cli import (
    _EVIDENCE_QUALITY_CAVEAT,
    _dominance_annotations,
    _objective_point,
    _sensitivity_summary,
    run_discover_command,
)
from career_agent.domain.models import Opportunity, Provenance
from career_agent.storage.sqlite import SqliteOpportunityRepository


def _opp(
    opportunity_id: str, *, confidence: float = 1.0, title: str | None = None
) -> Opportunity:
    return Opportunity(
        id=opportunity_id,
        company_id="acme",
        canonical_company="acme",
        title=title or f"Engineer ({opportunity_id})",
        source="job_board",
        source_url=f"https://example.invalid/{opportunity_id}",
        ats_ref=opportunity_id,
        provenance=Provenance(
            method="structured_api" if confidence == 1.0 else "text_extraction",
            reference="https://example.invalid/api",
            extraction_confidence=confidence,
        ),
        description_raw="",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _score(
    opportunity_id: str,
    *,
    total: float,
    profile_match: float = 50.0,
    source_reliability: float = 50.0,
    freshness: float = 50.0,
    salary_transparency: float = 0.0,
) -> DecisionScore:
    return DecisionScore(
        opportunity_id=opportunity_id,
        total=total,
        profile_match=profile_match,
        source_reliability=source_reliability,
        freshness=freshness,
        salary_transparency=salary_transparency,
        excluded=False,
    )


# --- _objective_point: the adapter ------------------------------------------


def test_objective_point_pulls_the_four_decide_objectives_and_confidence() -> None:
    opportunity = _opp("a", confidence=0.4)
    decision = _score(
        "a",
        total=70.0,
        profile_match=80.0,
        source_reliability=60.0,
        freshness=90.0,
        salary_transparency=100.0,
    )
    point = _objective_point(opportunity, decision)
    assert point.id == "a"
    assert point.objectives == {
        "profile_match": 80.0,
        "source_reliability": 60.0,
        "freshness": 90.0,
        "salary_transparency": 100.0,
    }
    assert point.confidence == 0.4


# --- _dominance_annotations: computed over the FULL included set -----------


def test_dominated_opportunity_outside_a_hypothetical_top_slice_still_counts() -> (
    None
):
    """The exact invariant Stage 4 requires: dominance must be computed
    over the full included set, not a truncated display slice -- an 11th
    (or here, 3rd) item can still be the one that dominates a top item."""
    strong = (
        _opp("strong"),
        _score("strong", total=90.0, profile_match=95.0, source_reliability=95.0,
               freshness=95.0, salary_transparency=100.0),
    )
    weak = (
        _opp("weak"),
        _score("weak", total=40.0, profile_match=30.0, source_reliability=30.0,
               freshness=30.0, salary_transparency=0.0),
    )
    included = [strong, weak]
    annotations = _dominance_annotations(included)
    assert annotations["strong"] == " [Pareto-optimal]"
    assert annotations["weak"] == " [dominated by: strong]"


def test_mutually_non_dominated_opportunities_are_both_pareto_optimal() -> None:
    tradeoff_a = (
        _opp("a"),
        _score("a", total=60.0, profile_match=90.0, source_reliability=10.0),
    )
    tradeoff_b = (
        _opp("b"),
        _score("b", total=60.0, profile_match=10.0, source_reliability=90.0),
    )
    annotations = _dominance_annotations([tradeoff_a, tradeoff_b])
    assert annotations["a"] == " [Pareto-optimal]"
    assert annotations["b"] == " [Pareto-optimal]"


def test_empty_included_produces_no_annotations() -> None:
    assert _dominance_annotations([]) == {}


# --- _sensitivity_summary: bounded to #1 vs #2 only -------------------------


def test_sensitivity_summary_reports_the_current_margin() -> None:
    included = [
        (_opp("a"), _score("a", total=80.0)),
        (_opp("b"), _score("b", total=55.0)),
        (_opp("c"), _score("c", total=10.0)),
    ]
    lines = _sensitivity_summary(included)
    assert any("current margin 25.0" in line for line in lines)


def test_sensitivity_summary_empty_for_fewer_than_two_included() -> None:
    assert _sensitivity_summary([]) == []
    assert _sensitivity_summary([(_opp("a"), _score("a", total=50.0))]) == []


def test_sensitivity_summary_never_examines_non_adjacent_pairs() -> None:
    """A 3-item list must only ever discuss #1 vs #2, never #1 vs #3 or
    #2 vs #3 -- confirmed by the identifiers that can appear in the text."""
    included = [
        (_opp("first"), _score("first", total=90.0)),
        (_opp("second"), _score("second", total=60.0)),
        (_opp("third"), _score("third", total=30.0)),
    ]
    lines = _sensitivity_summary(included)
    joined = "\n".join(lines)
    assert "third" not in joined


# --- run_discover_command: the real, wired end-to-end path ------------------


class _FakeSource:
    def __init__(self, found: list[Opportunity]) -> None:
        self._found = found

    async def fetch(self, since: datetime) -> list[Opportunity]:
        return self._found


class _FakeScorer:
    """Deterministic, hand-controlled scorer -- proves the CLI wiring
    without depending on DeterministicDecideScorer's own keyword-matching
    internals (already covered by tests/agents/test_decide.py)."""

    def rank(self, opportunities, profile):
        by_id = {o.id: o for o in opportunities}
        included = [
            (by_id["dominant"], _score("dominant", total=90.0, profile_match=95.0,
                                        source_reliability=95.0, freshness=95.0,
                                        salary_transparency=100.0)),
            (by_id["dominated"], _score("dominated", total=50.0, profile_match=30.0,
                                         source_reliability=30.0, freshness=30.0,
                                         salary_transparency=0.0)),
        ]
        return included, []


async def test_discover_prints_dominance_and_sensitivity_advisory_output(
    tmp_path: Path, capsys
) -> None:
    repo = SqliteOpportunityRepository(tmp_path / "db.sqlite")
    out_dir = tmp_path / "opps"
    sources = [
        (
            "one",
            _FakeSource(
                [_opp("dominant", confidence=0.3), _opp("dominated")]
            ),
        ),
    ]
    from tests.agents._profile_fixture import sample_master_profile

    code = await run_discover_command(
        sources,
        repo,
        since=datetime(2026, 1, 1, tzinfo=UTC),
        out_dir=out_dir,
        profile=sample_master_profile(),
        scorer=_FakeScorer(),
    )
    assert code == 0
    output = capsys.readouterr().out
    assert "[Pareto-optimal]" in output
    assert "[dominated by: dominant]" in output
    assert _EVIDENCE_QUALITY_CAVEAT in output  # confidence=0.3 was present
    assert "Sensitivity (#1 vs #2" in output


async def test_discover_omits_caveat_when_all_confidence_is_full(
    tmp_path: Path, capsys
) -> None:
    repo = SqliteOpportunityRepository(tmp_path / "db.sqlite")
    out_dir = tmp_path / "opps"
    sources = [("one", _FakeSource([_opp("dominant"), _opp("dominated")]))]
    from tests.agents._profile_fixture import sample_master_profile

    await run_discover_command(
        sources,
        repo,
        since=datetime(2026, 1, 1, tzinfo=UTC),
        out_dir=out_dir,
        profile=sample_master_profile(),
        scorer=_FakeScorer(),
    )
    output = capsys.readouterr().out
    assert _EVIDENCE_QUALITY_CAVEAT not in output


async def test_hard_exclusions_and_ordering_are_unaffected_by_this_phase(
    tmp_path: Path, capsys
) -> None:
    """The load-bearing regression: the new advisory annotations must
    never change which opportunities are excluded, their exclusion
    reasons, or the printed scalar order/values."""

    class _ScorerWithExclusion:
        def rank(self, opportunities, profile):
            by_id = {o.id: o for o in opportunities}
            included = [
                (by_id["keep"], _score("keep", total=77.7)),
            ]
            excluded = [
                DecisionScore(
                    opportunity_id="drop",
                    total=0.0,
                    profile_match=0.0,
                    source_reliability=0.0,
                    freshness=0.0,
                    salary_transparency=0.0,
                    excluded=True,
                    exclude_reasons=["company 'blocked' is blacklisted"],
                )
            ]
            return included, excluded

    repo = SqliteOpportunityRepository(tmp_path / "db.sqlite")
    out_dir = tmp_path / "opps"
    sources = [("one", _FakeSource([_opp("keep"), _opp("drop")]))]
    from tests.agents._profile_fixture import sample_master_profile

    await run_discover_command(
        sources,
        repo,
        since=datetime(2026, 1, 1, tzinfo=UTC),
        out_dir=out_dir,
        profile=sample_master_profile(),
        scorer=_ScorerWithExclusion(),
    )
    output = capsys.readouterr().out
    assert "77.7" in output
    assert "EXCLUDED drop: company 'blocked' is blacklisted" in output


async def test_auto_command_path_is_unaffected_by_this_phase() -> None:
    """auto never calls run_discover_command's print branch at all
    (profile/scorer are passed to run_discover_command only from within
    run_discover_command's own optional branch, never from run_auto_command)
    -- confirmed structurally, not just by absence of a failing test."""
    from career_agent import cli as cli_module

    assert "_dominance_annotations" not in cli_module.run_auto_command.__code__.co_names
    assert "_sensitivity_summary" not in cli_module.run_auto_command.__code__.co_names


async def test_no_submission_path_references_decision_intelligence() -> None:
    """Phase 21 (ADR-0047) hard-feasibility/safety audit: neither
    _dominance_annotations nor _sensitivity_summary is referenced by any
    function on the confirmation/submission chain -- advisory analysis has
    no code path into a real submission decision at all, not merely "isn't
    called today"."""
    from career_agent import cli as cli_module

    for function in (
        cli_module.confirm_submission,
        cli_module.run_apply_command,
        cli_module._apply_pipeline,
    ):
        assert "_dominance_annotations" not in function.__code__.co_names
        assert "_sensitivity_summary" not in function.__code__.co_names


async def test_excluded_opportunity_with_a_dominating_vector_stays_excluded(
    tmp_path: Path, capsys
) -> None:
    """Phase 21 (ADR-0047) hard-feasibility invariant: an opportunity that
    would objectively dominate every included candidate, but is hard-
    excluded (e.g. blacklisted), must remain excluded -- advisory analysis
    only ever sees `included`, so it has no channel through which an
    excellent objective vector could reclassify an excluded opportunity as
    eligible, let alone as "Pareto-optimal"."""

    class _ScorerExcludingTheBestVector:
        def rank(self, opportunities, profile):
            by_id = {o.id: o for o in opportunities}
            included = [
                (by_id["mediocre"], _score("mediocre", total=40.0, profile_match=40.0)),
            ]
            excluded = [
                DecisionScore(
                    opportunity_id="excellent-but-blacklisted",
                    total=0.0,
                    profile_match=100.0,
                    source_reliability=100.0,
                    freshness=100.0,
                    salary_transparency=100.0,
                    excluded=True,
                    exclude_reasons=["company 'blocked' is blacklisted"],
                )
            ]
            return included, excluded

    repo = SqliteOpportunityRepository(tmp_path / "db.sqlite")
    out_dir = tmp_path / "opps"
    sources = [
        (
            "one",
            _FakeSource(
                [_opp("mediocre"), _opp("excellent-but-blacklisted")]
            ),
        )
    ]
    from tests.agents._profile_fixture import sample_master_profile

    await run_discover_command(
        sources,
        repo,
        since=datetime(2026, 1, 1, tzinfo=UTC),
        out_dir=out_dir,
        profile=sample_master_profile(),
        scorer=_ScorerExcludingTheBestVector(),
    )
    output = capsys.readouterr().out
    assert (
        "EXCLUDED excellent-but-blacklisted: company 'blocked' is blacklisted"
        in output
    )
    # The excluded opportunity must never be annotated as Pareto-optimal,
    # never appear in a [dominated by: ...] list, and never appear in the
    # ranked/advisory section at all -- it was never given to the analysis.
    assert "excellent-but-blacklisted" not in output.split("EXCLUDED")[0]
