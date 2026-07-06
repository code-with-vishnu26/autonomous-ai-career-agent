"""Phase 10 / ADR-0034: the ATS gate + auto-retailor loop, matrix cases A1,
B1-B5, D3, plus the "one text, one truth" identity proof.

Reviewer-drafted matrix, implemented verbatim -- same discipline as the
truthfulness gate (ADR-0016) and QuestionAnswerer (ADR-0031). The scoring
fixture is real end-to-end arithmetic, not mocks of the scorer: draft 1
genuinely scores 60.0 against the JD below, the Docker-only retry 69.0,
and the Docker+PostgreSQL retry 78.0 -- pass/fail transitions come from
real thresholds against real computed scores.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from career_agent.agents.resume import pipeline as pipeline_module
from career_agent.agents.resume.gate import LLMTruthfulnessGate
from career_agent.agents.resume.generator import LLMResumeGenerator
from career_agent.agents.resume.pipeline import ResumeTailoringPipeline
from career_agent.core.bus import EventBus
from career_agent.core.interfaces import ClaimVerdict
from career_agent.domain.ats_scoring import (
    AtsScoreBelowThresholdError,
    SemanticKeywordClaim,
)
from career_agent.domain.models import (
    DraftedTailoring,
    Opportunity,
    Provenance,
    TailoredWorkEntry,
)
from tests._fakes import FakeClaimVerifier, FakeContentDrafter

from ._profile_fixture import sample_master_profile

_JD = (
    "Backend Engineer. Python, Django, PostgreSQL, Docker, and Kubernetes "
    "experience required."
)

_BASE_HIGHLIGHT = "Built REST APIs serving 2M requests/day"
# ADR-0044: "Containerized services with Docker" (a skill-only technology
# paired with an accomplishment verb) is now itself an unsupported-action
# claim, caught by the truthfulness gate's own precheck -- these fixtures
# use a familiarity phrasing ("Skilled in") instead, which keeps the exact
# same keyword-coverage credit (ATS scoring counts literal keyword
# occurrence, not surrounding verb) while remaining truthful under the
# stricter standard.
_DOCKER_HIGHLIGHT = "Skilled in Docker"
_DOCKER_PG_HIGHLIGHT = "Skilled in Docker and PostgreSQL"
_FABRICATED_HIGHLIGHT = "Ran the Kubernetes platform team"

_VERDICTS = {
    "Software Engineer": ClaimVerdict(verified=True, confidence=1.0),
    _BASE_HIGHLIGHT: ClaimVerdict(verified=True, confidence=0.95),
    _DOCKER_HIGHLIGHT: ClaimVerdict(verified=True, confidence=0.95),
    _DOCKER_PG_HIGHLIGHT: ClaimVerdict(verified=True, confidence=0.95),
    # The fabrication a keyword-chasing retry might attempt (case B3):
    _FABRICATED_HIGHLIGHT: ClaimVerdict(verified=False, confidence=0.95),
}


def _opportunity() -> Opportunity:
    return Opportunity(
        id="opp-1",
        company_id="acme",
        canonical_company="acme.com",
        title="Backend Engineer",
        source="ats_api",
        source_url="https://boards.greenhouse.io/acme/jobs/12345",
        provenance=Provenance(
            method="structured_api",
            reference="https://boards.greenhouse.io/acme/jobs/12345",
            extraction_confidence=1.0,
        ),
        description_raw=_JD,
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _profile():
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer."
    return profile


def _drafted(highlights: list[str]) -> DraftedTailoring:
    return DraftedTailoring(
        work=[
            TailoredWorkEntry(
                source_entry_id="work-techco",
                position="Software Engineer",
                highlights=highlights,
            )
        ],
        skills=["Python", "Django"],
    )


# Real computed scores against _JD (see module docstring): 60.0 / 69.0 / 78.0
_DRAFT_60 = _drafted([_BASE_HIGHLIGHT])
_DRAFT_69 = _drafted([_BASE_HIGHLIGHT, _DOCKER_HIGHLIGHT])
_DRAFT_78 = _drafted([_BASE_HIGHLIGHT, _DOCKER_PG_HIGHLIGHT])
_DRAFT_FABRICATED = _drafted([_BASE_HIGHLIGHT, _FABRICATED_HIGHLIGHT])


def _pipeline(
    drafter: FakeContentDrafter,
    *,
    ats_threshold: float | None = 75.0,
    semantic_matcher=None,
) -> ResumeTailoringPipeline:
    return ResumeTailoringPipeline(
        LLMResumeGenerator(drafter),
        LLMTruthfulnessGate(FakeClaimVerifier(dict(_VERDICTS))),
        EventBus(),
        ats_threshold=ats_threshold,
        semantic_matcher=semantic_matcher,
    )


class _FakeSemanticMatcher:
    """Returns canned claims; records calls (advisory layer test double)."""

    def __init__(self, claims: list[SemanticKeywordClaim]) -> None:
        self._claims = claims
        self.calls: list[list[str]] = []

    async def propose_matches(
        self, missing_keywords: list[str], resume_text: str
    ) -> list[SemanticKeywordClaim]:
        self.calls.append(list(missing_keywords))
        return self._claims


# ---------------------------------------------------------------------------
# Case A1 -- the semantic layer can never alter the pass/fail outcome
# ---------------------------------------------------------------------------


async def test_case_a1_semantic_claims_never_push_a_failing_score_past_the_gate():
    """Verifiable claims for every missing keyword, threshold the
    deterministic score can't reach: the gate must still refuse -- the
    semantic layer's only observable effect is pruning the gap report the
    drafter sees, never the decision."""
    # Every claim quotes a phrase genuinely present verbatim in the resume,
    # so all of them verify -- the strongest possible semantic input.
    claims = [
        SemanticKeywordClaim(keyword="Kubernetes", quoted_phrase=_BASE_HIGHLIGHT),
        SemanticKeywordClaim(keyword="Docker", quoted_phrase=_BASE_HIGHLIGHT),
        SemanticKeywordClaim(keyword="PostgreSQL", quoted_phrase=_BASE_HIGHLIGHT),
    ]
    matcher = _FakeSemanticMatcher(claims)
    drafter = FakeContentDrafter(results=[_DRAFT_60, _DRAFT_60])  # converges
    pipeline = _pipeline(drafter, ats_threshold=99.0, semantic_matcher=matcher)

    with pytest.raises(AtsScoreBelowThresholdError) as excinfo:
        await pipeline.run(_opportunity(), _profile())

    # The deterministic score is untouched by the verified claims:
    assert excinfo.value.trajectory[0].total == pytest.approx(60.0)
    assert matcher.calls  # the semantic layer genuinely ran
    # Its only effect: the pruned keywords are absent from the injected
    # gap report (observable via what the drafter was shown).
    retry_gap = drafter.calls[1][2]
    assert retry_gap is not None
    shown = {item.keyword for item in retry_gap.surfaceable}
    assert "Kubernetes" not in shown
    assert "Docker" not in shown


# ---------------------------------------------------------------------------
# Case B1 -- GENUINE gaps never reach the drafter, across every retry
# ---------------------------------------------------------------------------


async def test_case_b1_genuine_gap_never_surfaced_in_any_retry_and_reported_honestly():
    """Kubernetes has zero evidence anywhere in the profile. It must never
    appear in any gap report the drafter is shown, on any attempt, and the
    final refusal must name it as a GENUINE skill gap -- not a tailoring
    failure."""
    drafter = FakeContentDrafter(results=[_DRAFT_60, _DRAFT_69, _DRAFT_78])
    pipeline = _pipeline(drafter, ats_threshold=99.0)  # nothing can pass

    with pytest.raises(AtsScoreBelowThresholdError) as excinfo:
        await pipeline.run(_opportunity(), _profile())

    # Across EVERY recorded drafter call, no gap report ever carried
    # Kubernetes -- proving absence of the channel, not absence of use.
    for _opp_id, _version, gap_report in drafter.calls:
        if gap_report is None:
            continue
        assert "Kubernetes" not in {
            item.keyword for item in gap_report.surfaceable
        }
    assert excinfo.value.genuine_gaps == ["Kubernetes"]
    assert "not tailoring failures" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Case B2 -- the honest positive case: surfaceable keywords get promoted
# ---------------------------------------------------------------------------


async def test_case_b2_surfaceable_keywords_promoted_by_retry_and_gate_passes():
    """Docker/PostgreSQL are in the profile but weren't surfaced at first.
    The retry promotes them into a highlight, passes the full truthfulness
    gate, and the ATS gate passes at the default threshold."""
    drafter = FakeContentDrafter(results=[_DRAFT_60, _DRAFT_78])
    pipeline = _pipeline(drafter, ats_threshold=75.0)

    result = await pipeline.run(_opportunity(), _profile())

    assert result.submittable is not None
    # The retry was shown Docker/PostgreSQL as surfaceable (with profile
    # evidence), which is exactly what it honestly promoted.
    retry_gap = drafter.calls[1][2]
    shown = {item.keyword for item in retry_gap.surfaceable}
    assert {"Docker", "PostgreSQL"} <= shown
    assert result.application.resume.truthfulness.approved is True
    assert _DOCKER_PG_HIGHLIGHT in (result.application.resume.rendered_text or "")


# ---------------------------------------------------------------------------
# Case B3 -- truthfulness gate before every re-score, no exceptions
# ---------------------------------------------------------------------------


async def test_case_b3_truthfulness_rejected_retry_is_never_ats_scored():
    """Retry 1 fabricates a Kubernetes claim (which WOULD score 78, above
    threshold, if scored). The truthfulness gate rejects it -- so it must
    never be scored at all: a high ATS number cannot exist for an
    unapproved draft, which is what makes bypass impossible rather than
    merely forbidden. Retry 2 is honest and passes."""
    drafter = FakeContentDrafter(
        results=[_DRAFT_60, _DRAFT_FABRICATED, _DRAFT_78]
    )
    scored_texts: list[str] = []
    real_score = pipeline_module.score_resume

    def recording_score(rendered_text, *args, **kwargs):
        scored_texts.append(rendered_text)
        return real_score(rendered_text, *args, **kwargs)

    pipeline = _pipeline(drafter, ats_threshold=75.0)
    with patch.object(pipeline_module, "score_resume", recording_score):
        result = await pipeline.run(_opportunity(), _profile())

    assert result.submittable is not None
    # Exactly two drafts were ever scored: the initial one and the honest
    # retry 2. The fabricated retry was gated out BEFORE scoring existed.
    assert len(scored_texts) == 2
    assert not any(_FABRICATED_HIGHLIGHT in text for text in scored_texts)
    # And the fabricated draft did consume a retry (three drafter calls).
    assert len(drafter.calls) == 3


# ---------------------------------------------------------------------------
# Case B4 -- exhausted retries: trajectory + honest gap split in the refusal
# ---------------------------------------------------------------------------


async def test_case_b4_refusal_reports_the_full_trajectory_and_gap_split():
    drafter = FakeContentDrafter(results=[_DRAFT_60, _DRAFT_69, _DRAFT_78])
    pipeline = _pipeline(drafter, ats_threshold=99.0)

    with pytest.raises(AtsScoreBelowThresholdError) as excinfo:
        await pipeline.run(_opportunity(), _profile())

    totals = [report.total for report in excinfo.value.trajectory]
    assert totals == pytest.approx([60.0, 69.0, 78.0])  # improvement, visible
    message = str(excinfo.value)
    assert "60.00 -> 69.00 -> 78.00" in message
    assert "GENUINE" in message
    assert excinfo.value.genuine_gaps == ["Kubernetes"]
    assert excinfo.value.converged_early is False


# ---------------------------------------------------------------------------
# Case B5 -- convergence stops the loop early and says so
# ---------------------------------------------------------------------------


async def test_case_b5_identical_retry_stops_early_with_an_honest_report():
    drafter = FakeContentDrafter(results=[_DRAFT_60, _DRAFT_60])
    pipeline = _pipeline(drafter, ats_threshold=99.0)

    with pytest.raises(AtsScoreBelowThresholdError) as excinfo:
        await pipeline.run(_opportunity(), _profile())

    assert excinfo.value.converged_early is True
    assert "no further truthful improvement available" in str(excinfo.value)
    # Only 2 drafter calls -- the second retry was never burned on a
    # guaranteed-identical draft.
    assert len(drafter.calls) == 2
    assert len(excinfo.value.trajectory) == 1  # only one draft ever scored


# ---------------------------------------------------------------------------
# Case D3 -- the threshold is genuinely read from config at evaluation time
# ---------------------------------------------------------------------------


async def test_case_d3_configured_threshold_changes_the_gate_outcome():
    """The same draft that fails at the default 75 passes with the
    threshold configured to 60 -- proving the value is read at
    gate-evaluation time, not a compiled-in constant."""
    failing = _pipeline(
        FakeContentDrafter(results=[_DRAFT_60, _DRAFT_60]), ats_threshold=75.0
    )
    with pytest.raises(AtsScoreBelowThresholdError):
        await failing.run(_opportunity(), _profile())

    passing = _pipeline(
        FakeContentDrafter(result=_DRAFT_60), ats_threshold=60.0
    )
    result = await passing.run(_opportunity(), _profile())
    assert result.submittable is not None


# ---------------------------------------------------------------------------
# "One text, one truth": the scorer and the human preview consume the
# literal same rendered string -- reviewer-required explicit proof
# ---------------------------------------------------------------------------


async def test_scorer_and_preview_consume_the_literal_same_rendered_string():
    """One render_tailored_resume call per accepted draft, and the exact
    object it returned is both what the scorer received and what lands on
    TailoredResume.rendered_text -- not two calls that happen to agree
    today and could drift apart later."""
    render_calls: list[str] = []
    real_render = pipeline_module.render_tailored_resume

    def recording_render(*args, **kwargs):
        text = real_render(*args, **kwargs)
        render_calls.append(text)
        return text

    scored_texts: list[str] = []
    real_score = pipeline_module.score_resume

    def recording_score(rendered_text, *args, **kwargs):
        scored_texts.append(rendered_text)
        return real_score(rendered_text, *args, **kwargs)

    pipeline = _pipeline(
        FakeContentDrafter(result=_DRAFT_78), ats_threshold=75.0
    )
    with (
        patch.object(pipeline_module, "render_tailored_resume", recording_render),
        patch.object(pipeline_module, "score_resume", recording_score),
    ):
        result = await pipeline.run(_opportunity(), _profile())

    assert len(render_calls) == 1  # one render, period
    assert len(scored_texts) == 1
    stored = result.application.resume.rendered_text
    assert scored_texts[0] is render_calls[0]  # scorer got THE string
    assert stored is render_calls[0]  # preview stores THE string
