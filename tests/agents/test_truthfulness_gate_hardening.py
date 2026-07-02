"""The five compensating controls required around the gate's one probabilistic
component (ADR-0016), tested independently of the adversarial matrix.

This is the first safety-critical component resting on model judgment rather
than a structural guarantee, so it needs a harness matching that: a
low-confidence "yes" must not be trusted, a verifier failure must never be a
silent pass, and every verdict must be reproducible against the prompt that
produced it.
"""

from __future__ import annotations

from career_agent.agents.resume.gate import LLMTruthfulnessGate
from career_agent.core.interfaces import ClaimVerdict
from career_agent.domain.models import (
    TailoredContent,
    TailoredResumeDraft,
    TailoredWorkEntry,
)
from tests._fakes import FakeClaimVerifier

from ._profile_fixture import sample_master_profile


def _draft_with_highlight(claim: str) -> TailoredResumeDraft:
    return TailoredResumeDraft(
        opportunity_id="opp-1",
        profile_version="profile-v1",
        content=TailoredContent(
            summary="x",
            work=[
                TailoredWorkEntry(
                    source_entry_id="work-techco",
                    position="Software Engineer",
                    highlights=[claim],
                )
            ],
        ),
    )


async def test_sub_threshold_confidence_overrides_verified_true() -> None:
    """A verifier saying verified=True with low confidence must not be trusted
    -- same discipline as Provenance/HeldCandidate confidence, not a third
    invented version of the idea."""
    claim = "Some plausible-sounding but weakly-supported claim"
    verifier = FakeClaimVerifier(
        {
            "Software Engineer": ClaimVerdict(verified=True, confidence=1.0),
            claim: ClaimVerdict(verified=True, confidence=0.3),  # below default 0.7
        }
    )
    gate = LLMTruthfulnessGate(verifier)  # default threshold 0.7
    result = await gate.verify(_draft_with_highlight(claim), sample_master_profile())
    assert result.approved is False
    statement = next(s for s in result.statements if s.text == claim)
    assert statement.verified is False
    rejection = next(r for r in result.rejections if r.statement_text == claim)
    assert "confidence" in rejection.detail.lower()


async def test_confidence_at_or_above_threshold_is_trusted() -> None:
    claim = "A confidently-verified claim"
    verifier = FakeClaimVerifier(
        {
            "Software Engineer": ClaimVerdict(verified=True, confidence=1.0),
            claim: ClaimVerdict(verified=True, confidence=0.7),  # exactly at threshold
        }
    )
    gate = LLMTruthfulnessGate(verifier, confidence_threshold=0.7)
    result = await gate.verify(_draft_with_highlight(claim), sample_master_profile())
    assert result.approved is True


async def test_verifier_exception_is_an_explicit_block_not_a_silent_pass() -> None:
    """Infrastructure failure (timeout, API error) must never be evidence of
    truthfulness. The gate must not crash either -- it produces a well-formed,
    blocked TruthfulnessResult."""
    claim = "A claim whose verification call fails"
    verifier = FakeClaimVerifier(
        {
            "Software Engineer": ClaimVerdict(verified=True, confidence=1.0),
            claim: TimeoutError("simulated verifier timeout"),
        }
    )
    gate = LLMTruthfulnessGate(verifier)
    result = await gate.verify(_draft_with_highlight(claim), sample_master_profile())
    assert result.approved is False
    rejection = next(r for r in result.rejections if r.statement_text == claim)
    assert rejection.category == "verification_failed"
    assert "timeout" in rejection.detail.lower()


async def test_one_verifier_failure_does_not_block_the_others() -> None:
    """A single failing call must not abort the whole verification run."""
    ok_claim = "Cut pipeline runtime 40%"
    failing_claim = "A claim whose verification call fails"
    verifier = FakeClaimVerifier(
        {
            "Software Engineer": ClaimVerdict(verified=True, confidence=1.0),
            ok_claim: ClaimVerdict(verified=True, confidence=0.95),
            failing_claim: RuntimeError("simulated API error"),
        }
    )
    gate = LLMTruthfulnessGate(verifier)
    draft = TailoredResumeDraft(
        opportunity_id="opp-1",
        profile_version="profile-v1",
        content=TailoredContent(
            summary="x",
            work=[
                TailoredWorkEntry(
                    source_entry_id="work-techco",
                    position="Software Engineer",
                    highlights=[ok_claim, failing_claim],
                )
            ],
        ),
    )
    result = await gate.verify(draft, sample_master_profile())
    ok_statement = next(s for s in result.statements if s.text == ok_claim)
    failed_statement = next(s for s in result.statements if s.text == failing_claim)
    assert ok_statement.verified is True
    assert failed_statement.verified is False
    assert result.approved is False  # the one failure still blocks the whole draft


async def test_prompt_version_propagates_to_the_result() -> None:
    """Every TruthfulnessResult is reproducible against the exact prompt that
    produced it (ADR-0016)."""
    verifier = FakeClaimVerifier(
        {"Software Engineer": ClaimVerdict(verified=True, confidence=1.0)},
        prompt_version="truthfulness-gate-v1",
    )
    gate = LLMTruthfulnessGate(verifier)
    draft = TailoredResumeDraft(
        opportunity_id="opp-1",
        profile_version="profile-v1",
        content=TailoredContent(
            summary="x",
            work=[
                TailoredWorkEntry(
                    source_entry_id="work-techco",
                    position="Software Engineer",
                    highlights=[],
                )
            ],
        ),
    )
    result = await gate.verify(draft, sample_master_profile())
    assert result.prompt_version == "truthfulness-gate-v1"


async def test_result_profile_version_matches_the_profile_verified_against() -> None:
    gate = LLMTruthfulnessGate(FakeClaimVerifier({}))
    draft = TailoredResumeDraft(
        opportunity_id="opp-1",
        profile_version="profile-v1",
        content=TailoredContent(summary="x", skills=["Python"]),
    )
    result = await gate.verify(draft, sample_master_profile())
    assert result.profile_version == sample_master_profile().version
