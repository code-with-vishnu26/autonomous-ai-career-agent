"""The load-bearing test for Phase 5: the reviewer-defined 12-case adversarial
fabrication matrix (ADR-0016).

The matrix is the reviewer's, not the implementer's -- same governance as the
HN held-candidate matrix and the cross-source dedup branches. Each case is
checked against ``FakeClaimVerifier``'s canned, deterministic verdicts, proving
the gate's *orchestration* (evidence assembly, category mapping, fail-closed
aggregation) is correct. It does NOT prove a real model judges these claims
correctly -- that is the promptfoo suite's job (see ``promptfoo/``), and the
distinction is deliberate, not an oversight.

Approve: #1, #8, #9, #11. Block: #2, #3, #4, #5, #6, #7, #10, #12.
"""

from __future__ import annotations

from career_agent.agents.resume.gate import LLMTruthfulnessGate
from career_agent.core.interfaces import ClaimVerdict, TruthfulnessGate
from career_agent.domain.models import (
    TailoredContent,
    TailoredProjectEntry,
    TailoredResumeDraft,
    TailoredWorkEntry,
)
from tests._fakes import FakeClaimVerifier

from ._profile_fixture import sample_master_profile


def _draft(content: TailoredContent) -> TailoredResumeDraft:
    return TailoredResumeDraft(
        opportunity_id="opp-1", profile_version="profile-v1", content=content
    )


def test_gate_satisfies_the_truthfulness_gate_protocol() -> None:
    gate = LLMTruthfulnessGate(FakeClaimVerifier({}))
    assert isinstance(gate, TruthfulnessGate)


# ---------------------------------------------------------------------------
# #1 -- clean honest rephrase (APPROVE, false-positive guard)
# ---------------------------------------------------------------------------


async def test_case_1_honest_rephrase_is_approved() -> None:
    claim = "Architected high-throughput REST APIs handling 2M+ daily requests"
    verifier = FakeClaimVerifier(
        {
            claim: ClaimVerdict(verified=True, confidence=0.95),
            "Software Engineer": ClaimVerdict(verified=True, confidence=1.0),
            "Cut pipeline runtime 40%": ClaimVerdict(verified=True, confidence=0.95),
        }
    )
    gate = LLMTruthfulnessGate(verifier)
    draft = _draft(
        TailoredContent(
            summary="x",
            work=[
                TailoredWorkEntry(
                    source_entry_id="work-techco",
                    position="Software Engineer",
                    highlights=[claim, "Cut pipeline runtime 40%"],
                )
            ],
        )
    )
    result = await gate.verify(draft, sample_master_profile())
    assert result.approved is True
    assert result.rejections == []


# ---------------------------------------------------------------------------
# #2 -- unsupported skill (BLOCK, skill_not_found)
# ---------------------------------------------------------------------------


async def test_case_2_unsupported_skill_is_blocked() -> None:
    gate = LLMTruthfulnessGate(FakeClaimVerifier({}))  # no LLM call needed: structural
    draft = _draft(TailoredContent(summary="x", skills=["Python", "AWS"]))
    result = await gate.verify(draft, sample_master_profile())
    assert result.approved is False
    assert result.rejections[0].category == "skill_not_found"
    assert "AWS" in result.rejections[0].detail


# ---------------------------------------------------------------------------
# #3 -- inflated metric (BLOCK, metric_unsupported)
# ---------------------------------------------------------------------------


async def test_case_3_inflated_metric_is_blocked() -> None:
    claim = "Cut pipeline runtime 90%"
    verifier = FakeClaimVerifier(
        {
            "Software Engineer": ClaimVerdict(verified=True, confidence=1.0),
            claim: ClaimVerdict(
                verified=False,
                confidence=0.9,
                category="metric_unsupported",
                detail="90% not supported; profile states 40%",
            ),
        }
    )
    gate = LLMTruthfulnessGate(verifier)
    draft = _draft(
        TailoredContent(
            summary="x",
            work=[
                TailoredWorkEntry(
                    source_entry_id="work-techco",
                    position="Software Engineer",
                    highlights=[claim],
                )
            ],
        )
    )
    result = await gate.verify(draft, sample_master_profile())
    assert result.approved is False
    assert result.rejections[0].category == "metric_unsupported"
    assert "90" in result.rejections[0].detail or "40" in result.rejections[0].detail


# ---------------------------------------------------------------------------
# #4 -- fabricated employer (BLOCK, employer_mismatch, structural)
# ---------------------------------------------------------------------------


async def test_case_4_fabricated_employer_is_blocked() -> None:
    gate = LLMTruthfulnessGate(FakeClaimVerifier({}))  # no LLM call: entry not found
    draft = _draft(
        TailoredContent(
            summary="x",
            work=[
                TailoredWorkEntry(
                    source_entry_id="work-google",  # not in the profile
                    position="Software Engineer",
                    highlights=["Worked on search infrastructure"],
                )
            ],
        )
    )
    result = await gate.verify(draft, sample_master_profile())
    assert result.approved is False
    assert result.rejections[0].category == "employer_mismatch"
    assert "work-google" in result.rejections[0].detail


# ---------------------------------------------------------------------------
# #5 -- real employer, inflated title (BLOCK, employer_mismatch)
# ---------------------------------------------------------------------------


async def test_case_5_inflated_title_is_blocked() -> None:
    verifier = FakeClaimVerifier(
        {
            "Senior Software Engineer": ClaimVerdict(
                verified=False,
                confidence=0.9,
                category="employer_mismatch",
                detail="title inflated: profile states Software Engineer",
            ),
        }
    )
    gate = LLMTruthfulnessGate(verifier)
    draft = _draft(
        TailoredContent(
            summary="x",
            work=[
                TailoredWorkEntry(
                    source_entry_id="work-techco",
                    # profile says "Software Engineer"
                    position="Senior Software Engineer",
                    highlights=[],
                )
            ],
        )
    )
    result = await gate.verify(draft, sample_master_profile())
    assert result.approved is False
    assert result.rejections[0].category == "employer_mismatch"


# ---------------------------------------------------------------------------
# #6 -- extended dates: structurally impossible, not behaviorally caught
# ---------------------------------------------------------------------------


def test_case_6_tailored_work_entry_cannot_carry_dates_at_all() -> None:
    """Dates are always the linked profile entry's own, by construction --
    TailoredWorkEntry has no date field, so date fabrication in structured
    content is impossible to construct, not merely caught by the gate. This is
    a STRONGER guarantee than a behavioral check."""
    assert "start_date" not in TailoredWorkEntry.model_fields
    assert "end_date" not in TailoredWorkEntry.model_fields
    assert set(TailoredWorkEntry.model_fields) == {
        "source_entry_id",
        "position",
        "highlights",
    }


# ---------------------------------------------------------------------------
# #7 -- invented detail, nothing to compare against (BLOCK, metric_unsupported)
# ---------------------------------------------------------------------------


async def test_case_7_invented_team_size_is_blocked() -> None:
    claim = "Led a team of 8 engineers"
    verifier = FakeClaimVerifier(
        {
            "Software Engineer": ClaimVerdict(verified=True, confidence=1.0),
            claim: ClaimVerdict(
                verified=False,
                confidence=0.9,
                category="metric_unsupported",
                detail="team size of 8 not supported by any profile evidence",
            ),
        }
    )
    gate = LLMTruthfulnessGate(verifier)
    draft = _draft(
        TailoredContent(
            summary="x",
            work=[
                TailoredWorkEntry(
                    source_entry_id="work-techco",
                    position="Software Engineer",
                    highlights=[claim],
                )
            ],
        )
    )
    result = await gate.verify(draft, sample_master_profile())
    assert result.approved is False
    assert result.rejections[0].category == "metric_unsupported"


# ---------------------------------------------------------------------------
# #8 -- honest generalization / vagueness (APPROVE, false-positive guard)
# ---------------------------------------------------------------------------


async def test_case_8_honest_generalization_is_approved() -> None:
    claim = "Improved system performance"
    verifier = FakeClaimVerifier(
        {
            "Software Engineer": ClaimVerdict(verified=True, confidence=1.0),
            claim: ClaimVerdict(verified=True, confidence=0.85),
        }
    )
    gate = LLMTruthfulnessGate(verifier)
    draft = _draft(
        TailoredContent(
            summary="x",
            work=[
                TailoredWorkEntry(
                    source_entry_id="work-techco",
                    position="Software Engineer",
                    highlights=[claim],
                )
            ],
        )
    )
    result = await gate.verify(draft, sample_master_profile())
    assert result.approved is True


# ---------------------------------------------------------------------------
# #9 -- skill listed but never demonstrated in a bullet (APPROVE -- resolved
# explicitly: the skills list is first-class evidence in its own right)
# ---------------------------------------------------------------------------


async def test_case_9_skill_list_alone_is_sufficient_evidence() -> None:
    claim = "Containerized services using Docker"
    verifier = FakeClaimVerifier(
        {
            "Software Engineer": ClaimVerdict(verified=True, confidence=1.0),
            claim: ClaimVerdict(verified=True, confidence=0.9),
        }
    )
    gate = LLMTruthfulnessGate(verifier)
    draft = _draft(
        TailoredContent(
            summary="x",
            work=[
                TailoredWorkEntry(
                    source_entry_id="work-techco",
                    position="Software Engineer",
                    highlights=[claim],
                )
            ],
        )
    )
    result = await gate.verify(draft, sample_master_profile())
    assert result.approved is True
    # confirms the skills list was actually included in the evidence the
    # verifier saw, not just coincidentally approved
    _, evidence_seen = verifier.calls[-1]
    assert "Docker" in evidence_seen


# ---------------------------------------------------------------------------
# #10 -- composite fabrication: real facts stitched into an untrue combined
# claim (BLOCK, evidence_missing -- caught by entailment, not keyword luck)
# ---------------------------------------------------------------------------


async def test_case_10_composite_fabrication_is_blocked_for_the_right_reason() -> None:
    """Django is a real skill; the REST-API highlight is real. Only
    "microservices platform" is invented. This must be caught because the
    added detail is ungrounded -- not because some unrelated fragment (e.g.
    "Django" alone) happens to trip skill_not_found. The evidence the fake
    verifier receives includes Django, proving a naive skill-presence check
    could NOT have caused this block by accident."""
    claim = "Built a Django-based microservices platform serving 2M requests"
    verifier = FakeClaimVerifier(
        {
            "Software Engineer": ClaimVerdict(verified=True, confidence=1.0),
            claim: ClaimVerdict(
                verified=False,
                confidence=0.85,
                category="evidence_missing",
                detail="microservices platform architecture not supported by evidence",
            ),
        }
    )
    gate = LLMTruthfulnessGate(verifier)
    draft = _draft(
        TailoredContent(
            summary="x",
            work=[
                TailoredWorkEntry(
                    source_entry_id="work-techco",
                    position="Software Engineer",
                    highlights=[claim],
                )
            ],
        )
    )
    result = await gate.verify(draft, sample_master_profile())
    assert result.approved is False
    assert result.rejections[0].category == "evidence_missing"
    assert "microservices" in result.rejections[0].detail
    # Django genuinely was in the evidence the verifier judged against --
    # the block is despite that, not because Django was absent.
    _, evidence_seen = verifier.calls[-1]
    assert "Django" in evidence_seen


# ---------------------------------------------------------------------------
# #11 -- synonym / elaboration, not verbatim (APPROVE, false-positive guard)
# ---------------------------------------------------------------------------


async def test_case_11_synonym_elaboration_is_approved() -> None:
    claim = "relational database design (PostgreSQL)"
    verifier = FakeClaimVerifier(
        {
            "Software Engineer": ClaimVerdict(verified=True, confidence=1.0),
            claim: ClaimVerdict(verified=True, confidence=0.9),
        }
    )
    gate = LLMTruthfulnessGate(verifier)
    draft = _draft(
        TailoredContent(
            summary="x",
            work=[
                TailoredWorkEntry(
                    source_entry_id="work-techco",
                    position="Software Engineer",
                    highlights=[claim],
                )
            ],
        )
    )
    result = await gate.verify(draft, sample_master_profile())
    assert result.approved is True


# ---------------------------------------------------------------------------
# #12 -- real project, fabricated outcome (BLOCK, metric_unsupported)
# ---------------------------------------------------------------------------


async def test_case_12_fabricated_project_outcome_is_blocked() -> None:
    claim = "Built an internal tool that saved the company $200K annually"
    verifier = FakeClaimVerifier(
        {
            claim: ClaimVerdict(
                verified=False,
                confidence=0.9,
                category="metric_unsupported",
                detail="$200K figure not supported by any profile evidence",
            ),
        }
    )
    gate = LLMTruthfulnessGate(verifier)
    draft = _draft(
        TailoredContent(
            summary="x",
            projects=[
                TailoredProjectEntry(
                    source_entry_id="proj-internal",
                    name="Internal Tool",
                    highlights=[claim],
                )
            ],
        )
    )
    result = await gate.verify(draft, sample_master_profile())
    assert result.approved is False
    assert result.rejections[0].category == "metric_unsupported"


# ---------------------------------------------------------------------------
# The whole matrix, in one pass -- pairing approve-cases against block-cases
# ---------------------------------------------------------------------------


async def test_matrix_load_bearing_pairing() -> None:
    """#1, #8, #9, #11 must approve; #2-#7, #10, #12 must block. A gate that
    blocks the honest cases is uselessly strict; a gate that approves any
    fabrication case has failed at the one thing it exists to do."""
    profile = sample_master_profile()
    approve_claims = [
        "Architected high-throughput REST APIs handling 2M+ daily requests",
        "Improved system performance",
        "Containerized services using Docker",
        "relational database design (PostgreSQL)",
    ]
    block_claims = [
        "Cut pipeline runtime 90%",
        "Led a team of 8 engineers",
        "Built a Django-based microservices platform serving 2M requests",
    ]
    verdicts = {"Software Engineer": ClaimVerdict(verified=True, confidence=1.0)}
    for claim in approve_claims:
        verdicts[claim] = ClaimVerdict(verified=True, confidence=0.9)
    for claim in block_claims:
        verdicts[claim] = ClaimVerdict(
            verified=False, confidence=0.9, category="evidence_missing", detail="x"
        )
    gate = LLMTruthfulnessGate(FakeClaimVerifier(verdicts))
    draft = _draft(
        TailoredContent(
            summary="x",
            skills=["Python"],  # deliberately no AWS: skills check passes too
            work=[
                TailoredWorkEntry(
                    source_entry_id="work-techco",
                    position="Software Engineer",
                    highlights=approve_claims + block_claims,
                )
            ],
        )
    )
    result = await gate.verify(draft, profile)
    highlight_texts = set(approve_claims) | set(block_claims)
    verified_texts = {
        s.text for s in result.statements if s.verified and s.text in highlight_texts
    }
    blocked_texts = {
        s.text
        for s in result.statements
        if not s.verified and s.text in highlight_texts
    }
    assert verified_texts == set(approve_claims)
    assert blocked_texts == set(block_claims)
    # any single failing statement blocks the whole draft
    assert result.approved is False
