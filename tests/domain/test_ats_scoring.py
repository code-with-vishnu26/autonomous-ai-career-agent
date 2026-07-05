"""Phase 10 / ADR-0034: the deterministic ATS scoring layer.

Implements the reviewer-drafted 14-case adversarial matrix's pure-scoring
cases (A2/A3, C1/C2, D1/D2) plus the classification foundations of B1/B2.
The loop-level cases (A1, B1-B5, D3) live in
``tests/agents/test_ats_gate_loop.py``. Matrix drafted by the reviewer,
not the implementer -- same discipline as the truthfulness gate (ADR-0016)
and QuestionAnswerer (ADR-0031).
"""

from __future__ import annotations

from career_agent.domain.ats_scoring import (
    AtsScoreReport,
    MissingKeyword,
    SemanticKeywordClaim,
    classify_missing_keywords,
    extract_jd_keywords,
    score_resume,
    verified_semantic_keywords,
)
from career_agent.domain.models import TailoredContent, TailoredWorkEntry
from tests.agents._profile_fixture import sample_master_profile

_JD = (
    "Backend Engineer. Python, Django, PostgreSQL, Docker, and Kubernetes "
    "experience required."
)


def _profile():
    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer."
    return profile


def _content(highlights: list[str], skills: list[str]) -> TailoredContent:
    return TailoredContent(
        summary="Backend engineer.",
        work=[
            TailoredWorkEntry(
                source_entry_id="work-techco",
                position="Software Engineer",
                highlights=highlights,
            )
        ],
        skills=skills,
    )


def _rendered(content: TailoredContent) -> str:
    from career_agent.domain.rendering import render_tailored_resume

    return render_tailored_resume(content, _profile())


def _report(**overrides) -> AtsScoreReport:
    defaults = dict(
        total=80.0,
        threshold=75.0,
        keyword_coverage=80.0,
        title_alignment=80.0,
        section_completeness=80.0,
        format_safety=100.0,
        matched=[],
        missing_keywords=[],
    )
    defaults.update(overrides)
    return AtsScoreReport(**defaults)


# ---------------------------------------------------------------------------
# Case A2 -- hard format failure overrides the numeric score
# ---------------------------------------------------------------------------


def test_case_a2_hard_format_failure_fails_gate_despite_score_above_threshold():
    report = _report(total=80.0, format_hard_failures=["empty text layer"])
    assert report.total > report.threshold
    assert report.passed is False  # the override lives in the type itself


def test_case_a2_empty_rendered_text_is_a_hard_failure_from_score_resume():
    content = _content(["Built REST APIs serving 2M requests/day"], ["Python"])
    report = score_resume(
        "",  # a self-inflicted empty text layer
        content,
        _profile(),
        opportunity_title="Backend Engineer",
        jd_text=_JD,
        threshold=75.0,
    )
    assert report.format_hard_failures
    assert report.passed is False


# ---------------------------------------------------------------------------
# Case A3 -- semantic credit requires a literal, verbatim supporting phrase
# ---------------------------------------------------------------------------


def test_case_a3_plausible_claim_without_verbatim_phrase_earns_nothing():
    resume_text = "Experienced with containerization and container orchestration."
    missing = [MissingKeyword(keyword="Kubernetes", kind="hard")]
    claims = [
        # Plausible-sounding, but the quoted phrase does not literally
        # exist in the resume -- plausibility alone is not evidence.
        SemanticKeywordClaim(
            keyword="Kubernetes", quoted_phrase="managed Kubernetes clusters"
        )
    ]
    assert verified_semantic_keywords(claims, missing, resume_text) == []


def test_case_a3_verbatim_phrase_verifies_and_case_is_forgiven_nothing_else():
    resume_text = "Deployed workloads via container orchestration on EKS."
    missing = [MissingKeyword(keyword="Kubernetes", kind="hard")]
    claims = [
        SemanticKeywordClaim(
            keyword="Kubernetes",
            quoted_phrase="container orchestration on EKS",
        )
    ]
    assert verified_semantic_keywords(claims, missing, resume_text) == ["Kubernetes"]


def test_case_a3_claim_for_a_keyword_not_actually_missing_is_ignored():
    resume_text = "Python everywhere."
    missing = [MissingKeyword(keyword="Kubernetes", kind="hard")]
    claims = [SemanticKeywordClaim(keyword="Docker", quoted_phrase="Python")]
    assert verified_semantic_keywords(claims, missing, resume_text) == []


# ---------------------------------------------------------------------------
# Case C1 -- repetition beyond the cap earns nothing and flags
# ---------------------------------------------------------------------------


def test_case_c1_score_does_not_scale_with_repetition_and_flags_stuffing():
    natural = _content(
        ["Built Python services with Python APIs"], ["Python"]
    )  # 3 occurrences incl. skills line
    stuffed = _content(
        [
            "Built Python services with Python APIs in Python",
            "Python Python tooling for Python teams",
        ],
        ["Python"],
    )  # 8 occurrences
    kwargs = dict(
        profile=_profile(),
        opportunity_title="Backend Engineer",
        jd_text=_JD,
        threshold=75.0,
    )
    natural_report = score_resume(_rendered(natural), natural, **kwargs)
    stuffed_report = score_resume(_rendered(stuffed), stuffed, **kwargs)

    assert stuffed_report.keyword_coverage == natural_report.keyword_coverage
    assert any("stuffing" in flag.lower() for flag in stuffed_report.stuffing_flags)
    assert not any(
        "cap" in flag for flag in natural_report.stuffing_flags
    )  # natural usage is not flagged


# ---------------------------------------------------------------------------
# Case C2 -- a bare keyword dump in the skills list is not a clean match
# ---------------------------------------------------------------------------


def test_case_c2_skills_list_only_matches_get_half_credit_and_flag():
    dump = _content(
        ["Shipped internal tooling"],  # zero keyword context anywhere
        ["Python", "Django", "PostgreSQL", "Docker", "Kubernetes"],
    )
    report = score_resume(
        _rendered(dump),
        dump,
        _profile(),
        opportunity_title="Backend Engineer",
        jd_text=_JD,
        threshold=75.0,
    )
    # Every required keyword string-matches, but none contextually: the
    # coverage must reflect the anti-stuffing penalty (half credit), never
    # read as a clean 100%.
    assert report.keyword_coverage == 50.0
    assert all(match.credit == 0.5 for match in report.matched)
    assert any("only in the skills list" in flag for flag in report.stuffing_flags)


# ---------------------------------------------------------------------------
# Cases D1/D2 -- exact threshold boundary, both directions
# ---------------------------------------------------------------------------


def test_case_d1_74_99_fails():
    assert _report(total=74.99, threshold=75.0).passed is False


def test_case_d2_75_00_passes():
    assert _report(total=75.00, threshold=75.0).passed is True


# ---------------------------------------------------------------------------
# B1/B2 foundations -- GENUINE vs SURFACEABLE classification
# ---------------------------------------------------------------------------


def test_genuine_vs_surfaceable_classification_against_the_real_profile():
    missing = [
        MissingKeyword(keyword="Docker", kind="hard"),  # in profile skills
        MissingKeyword(keyword="PostgreSQL", kind="hard"),  # in profile skills
        MissingKeyword(keyword="Kubernetes", kind="hard"),  # nowhere in profile
    ]
    surfaceable, genuine = classify_missing_keywords(missing, _profile())
    assert {item.keyword for item in surfaceable} == {"Docker", "PostgreSQL"}
    assert all(item.profile_evidence for item in surfaceable)  # real evidence text
    assert genuine == ["Kubernetes"]


def test_gap_report_type_structurally_cannot_carry_genuine_gaps():
    """The B1 channel restriction at its strongest: AtsGapReport has exactly
    one content field (surfaceable) -- there is no field through which a
    GENUINE gap could ever reach the drafter. Structural, not a check."""
    from career_agent.domain.ats_scoring import AtsGapReport

    assert set(AtsGapReport.model_fields) == {"surfaceable"}


def test_extract_jd_keywords_finds_taxonomy_skills_hard_first():
    keywords = extract_jd_keywords(_JD)
    names = [keyword.keyword for keyword in keywords]
    assert {"Python", "Django", "PostgreSQL", "Docker", "Kubernetes"} <= set(names)
    kinds = [keyword.kind for keyword in keywords]
    assert kinds == sorted(kinds, key=lambda kind: kind != "hard")  # hard first
