"""The load-bearing test for Phase 5: the reviewer-defined 12-case adversarial
fabrication matrix (ADR-0016), revised by ADR-0044's deterministic precheck
layer.

The matrix is the reviewer's, not the implementer's -- same governance as the
HN held-candidate matrix and the cross-source dedup branches. Each case is
checked against ``FakeClaimVerifier``'s canned, deterministic verdicts, proving
the gate's *orchestration* (evidence assembly, category mapping, fail-closed
aggregation) is correct. It does NOT prove a real model judges these claims
correctly -- that is the promptfoo suite's job (see ``promptfoo/``), and the
distinction is deliberate, not an oversight.

**ADR-0044 revised three of this matrix's original verdicts**, on the
explicit, documented finding that "a skill noun alone proves an action" and
"any honest-sounding rephrase is entailed" were themselves under-specified
policy, not settled fact -- see ADR-0044 for the full audit and reasoning:

- #1 (built -> architected) now BLOCKS: an unsupported ownership/verb
  escalation, not a "false-positive guard" case.
- #9 (Docker skill -> "containerized ... Docker") now BLOCKS: a skill
  listed but never demonstrated does not prove the action.
- #11 (PostgreSQL skill -> "database design (PostgreSQL)") now BLOCKS, for
  the same reason as #9.
- #10 (Django-based "microservices platform") still BLOCKS, but now at
  Layer 1 (``Microservices`` is a named, curated-taxonomy technology with
  zero evidence anywhere -- not even a skill), before the LLM is ever
  called, rather than at Layer 4 via the model's semantic judgment.
- #5 (title escalation) still BLOCKS, now with the more precise
  ``unsupported_seniority`` category instead of the overloaded
  ``employer_mismatch``.

#8 (a specific, evidenced improvement generalized into vaguer wording,
introducing nothing new) is the one matrix case ADR-0044 explicitly
confirmed as a genuine safe abstraction, not merely un-rejected -- see
``domain/truthfulness_predicates.py``'s Rule 6 and its own test suite.

Approve: #8. Block: #1, #2, #3, #4, #5, #6, #7, #9, #10, #11, #12.
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


async def test_case_1_built_to_architected_is_now_blocked() -> None:
    """ADR-0044 revised this from APPROVE to BLOCK: "architected" outranks
    the evidenced "built" for the same object, an unsupported ownership
    escalation -- not merely a stylistic rephrase. Resolved entirely at
    Layer 1 (precheck); the FakeClaimVerifier is never even called for
    this claim (empty verdict map proves it -- a call would raise)."""
    claim = "Architected high-throughput REST APIs handling 2M+ daily requests"
    verifier = FakeClaimVerifier({})
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
    assert result.approved is False
    assert result.rejections[0].category == "unsupported_action_inference"
    assert verifier.calls == []


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
# #5 -- real employer, inflated title (BLOCK, unsupported_seniority)
# ---------------------------------------------------------------------------


async def test_case_5_inflated_title_is_blocked() -> None:
    """ADR-0044: resolved at Layer 1 now, with the more precise
    ``unsupported_seniority`` category -- "employer_mismatch" was always an
    overloaded label for a title/seniority claim, not an actual employer
    dispute (the employer, Techco, is correct; only the title is
    inflated)."""
    verifier = FakeClaimVerifier({})
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
    assert result.rejections[0].category == "unsupported_seniority"
    assert verifier.calls == []


# ---------------------------------------------------------------------------
# #6 -- extended dates: structurally impossible for the generator to write,
# not caught behaviorally -- but NOT absent from the resume either. Real
# dates are resolved downstream (see tests/domain/test_rendering.py).
# ---------------------------------------------------------------------------


def test_case_6_tailored_work_entry_cannot_carry_dates_at_all() -> None:
    """The generator cannot fabricate a date because TailoredWorkEntry has no
    date field to write into -- date fabrication in structured content is
    impossible to construct, not merely caught by the gate. This is a
    stronger guarantee than a behavioral check, but it is NOT a guarantee
    that the rendered resume has no dates: those are resolved downstream from
    ``source_entry_id`` via ``domain.rendering.resolve_work_dates``, read-only,
    never generator-writable (ADR-0016's "Case #6 revisited" note)."""
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
# #9 -- skill listed but never demonstrated in a bullet (BLOCK, ADR-0044 --
# a skill noun alone does not prove an action was performed with it)
# ---------------------------------------------------------------------------


async def test_case_9_skill_list_alone_does_not_prove_the_action() -> None:
    """ADR-0044 revised this from APPROVE to BLOCK: Docker is a real skill,
    but "containerized services" asserts a specific action never
    demonstrated anywhere in the work/project evidence -- only in the bare
    skills list. Resolved at Layer 1; the verifier is never called."""
    claim = "Containerized services using Docker"
    verifier = FakeClaimVerifier({})
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
    assert result.rejections[0].category == "unsupported_action_inference"
    assert "Docker" in result.rejections[0].detail
    assert verifier.calls == []


# ---------------------------------------------------------------------------
# #10 -- composite fabrication: real facts stitched into an untrue combined
# claim (BLOCK, evidence_missing -- now caught at Layer 1, ADR-0044)
# ---------------------------------------------------------------------------


async def test_case_10_composite_fabrication_is_blocked_for_the_right_reason() -> None:
    """Django is a real skill; the REST-API highlight is real. "Microservices"
    is a curated-taxonomy technology with zero evidence anywhere -- not the
    LLM's semantic judgment call this used to be, but Layer 1's Rule 1
    (unsupported technology), resolved before the verifier is ever reached.
    The block is specifically about "Microservices", not a naive
    skill-presence miss on Django -- proven by the case immediately below,
    where a Django-only claim of the same shape is NOT blocked."""
    claim = "Built a Django-based microservices platform serving 2M requests"
    verifier = FakeClaimVerifier({})
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
    assert "Microservices" in result.rejections[0].detail
    assert verifier.calls == []


async def test_case_10b_a_genuinely_evidenced_technology_is_not_blocked() -> None:
    """The companion proof for #10: a claim naming ONLY Django (genuinely
    evidenced, if only as a skill) is not blocked by Rule 1 -- the previous
    test's block is specifically about "Microservices", not an accidental
    Django false-positive."""
    claim = "Used Django"
    verifier = FakeClaimVerifier({})
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
# #11 -- PostgreSQL skill does not prove design competency (BLOCK, ADR-0044)
# ---------------------------------------------------------------------------


async def test_case_11_skill_does_not_prove_design_competency() -> None:
    """ADR-0044 revised this from APPROVE to BLOCK: PostgreSQL is a real
    skill, but "database design" asserts a competency never demonstrated
    anywhere in the work/project evidence -- the same shape as #9, applied
    to a competency noun ("design") rather than a verb."""
    claim = "relational database design (PostgreSQL)"
    verifier = FakeClaimVerifier({})
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
    assert result.rejections[0].category == "unsupported_action_inference"
    assert verifier.calls == []


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
    """#8 must approve; #1, #2-#7, #9, #10, #11, #12 must block (ADR-0044
    revised #1/#9/#11 from approve to block -- see the module docstring).
    A gate that blocks the one honest case is uselessly strict; a gate
    that approves any fabrication case has failed at the one thing it
    exists to do. Every claim here resolves at Layer 1 -- the verifier is
    never called at all, proven by ``FakeClaimVerifier({})`` plus the
    empty-calls assertion."""
    profile = sample_master_profile()
    approve_claims = ["Improved system performance"]
    block_claims = [
        "Architected high-throughput REST APIs handling 2M+ daily requests",
        "Containerized services using Docker",
        "relational database design (PostgreSQL)",
        "Cut pipeline runtime 90%",
        "Led a team of 8 engineers",
        "Built a Django-based microservices platform serving 2M requests",
    ]
    verifier = FakeClaimVerifier({})
    gate = LLMTruthfulnessGate(verifier)
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
    assert verifier.calls == []
