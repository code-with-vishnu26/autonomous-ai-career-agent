"""ADR-0044: the deterministic Layer-1 claim-evidence prechecks.

Covers each rule directly, the four worked examples from the policy
discussion that motivated this module (A: Docker, B: PostgreSQL, C: Built
-> Architected, D: the safe-abstraction rule), and the metamorphic
properties named as required test coverage: escalating a verb, mutating a
metric, claiming a skill-only technology as an action, and escalating
seniority must never leave a claim ``safe``; a faithful, non-escalating
generalization may remain ``safe``.
"""

from __future__ import annotations

from career_agent.domain.truthfulness_predicates import PrecheckResult, precheck_claim

_EVIDENCE = "Built REST APIs serving 2M requests/day Cut pipeline runtime 40%"
_SKILLS = "Python, Django, PostgreSQL, Docker"


def _check(
    claim: str, contextual: str = _EVIDENCE, skills: str = _SKILLS
) -> PrecheckResult:
    return precheck_claim(claim, contextual, skills)


# ---------------------------------------------------------------------------
# Worked example A: a skill noun alone does not prove an action (Docker)
# ---------------------------------------------------------------------------


def test_worked_example_a_docker_skill_does_not_prove_containerizing():
    result = _check("Containerized services using Docker")
    assert result.verdict == "unsafe"
    assert result.category == "unsupported_action_inference"


def test_docker_action_is_safe_once_genuinely_contextually_evidenced():
    """The same claim is fine once Docker actually appears in context, not
    only the skills list -- the rule targets skill-only evidence, not
    Docker itself."""
    result = _check(
        "Containerized services using Docker",
        contextual=_EVIDENCE + " Containerized services with Docker",
    )
    assert result.verdict != "unsafe"


# ---------------------------------------------------------------------------
# Worked example B: PostgreSQL skill does not prove database design
# ---------------------------------------------------------------------------


def test_worked_example_b_postgresql_skill_does_not_prove_design_competency():
    result = _check("relational database design (PostgreSQL)")
    assert result.verdict == "unsafe"
    assert result.category == "unsupported_action_inference"


# ---------------------------------------------------------------------------
# Worked example C: built -> architected is not automatically entailed
# ---------------------------------------------------------------------------


def test_worked_example_c_built_to_architected_is_unsafe_strengthening():
    result = _check("Architected high-throughput REST APIs handling 2M+ daily requests")
    assert result.verdict == "unsafe"
    assert result.category == "unsupported_action_inference"


def test_matching_verb_strength_is_not_flagged():
    """The same object, claimed with a verb no stronger than evidenced, is
    not an escalation."""
    result = _check("Built REST APIs handling 2M+ daily requests")
    assert result.verdict != "unsafe"


# ---------------------------------------------------------------------------
# Worked example D: a safe, direction-preserving abstraction
# ---------------------------------------------------------------------------


def test_worked_example_d_runtime_cut_to_improved_performance_is_safe():
    result = _check("Improved system performance")
    assert result.verdict == "safe"


def test_safe_abstraction_requires_no_new_technology():
    """Direction-preserving wording that also sneaks in an unevidenced
    technology is not safe -- new technology is a real escalation, not a
    vaguer restatement."""
    result = _check("Improved system performance using Kubernetes")
    assert result.verdict != "safe"


# ---------------------------------------------------------------------------
# Rule 1: technology named with zero evidence anywhere (not even as a skill)
# ---------------------------------------------------------------------------


def test_rule1_unsupported_technology_blocks_even_in_a_longer_claim():
    """Matrix case #10: 'Microservices' never appears anywhere in evidence
    (not even the skills list) -- caught here, deterministically, before
    Rule 4's word-count cap would even apply."""
    result = _check("Built a Django-based microservices platform serving 2M requests")
    assert result.verdict == "unsafe"
    assert result.category == "evidence_missing"
    assert "Microservices" in result.detail


def test_rule1_does_not_fire_for_a_genuinely_evidenced_technology():
    result = _check("Used Django")
    assert result.category != "evidence_missing" or result.verdict != "unsafe"


# ---------------------------------------------------------------------------
# Rule 2: metric mutation
# ---------------------------------------------------------------------------


def test_rule2_inflating_forty_percent_to_ninety_percent_fails():
    result = _check("Cut pipeline runtime 90%")
    assert result.verdict == "unsafe"
    assert result.category == "metric_unsupported"


def test_rule2_tolerates_a_trailing_plus_on_an_evidenced_number():
    result = _check("Handles 2M+ requests")
    assert result.verdict != "unsafe" or result.category != "metric_unsupported"


def test_rule2_an_evidenced_number_restated_exactly_is_not_flagged():
    result = _check("Cut pipeline runtime 40%")
    assert result.verdict == "safe"


# ---------------------------------------------------------------------------
# Rule 3: seniority escalation
# ---------------------------------------------------------------------------


def test_rule3_senior_title_without_evidence_is_unsafe():
    result = _check("Senior Software Engineer")
    assert result.verdict == "unsafe"
    assert result.category == "unsupported_seniority"


def test_rule3_title_present_in_evidence_is_not_flagged():
    result = _check("Software Engineer", contextual="Software Engineer. " + _EVIDENCE)
    assert result.category != "unsupported_seniority"


# ---------------------------------------------------------------------------
# Rule 4: bounded to short claims -- see the rule's own comment
# ---------------------------------------------------------------------------


def test_rule4_does_not_fire_on_a_long_claim_with_other_disputed_content():
    """A long claim's skill-only technology is not, by itself, grounds for
    a Layer-1 block -- deferred to Layer 4, unless (as in this fixture) a
    *different* rule (here, Rule 1's unsupported 'Microservices') resolves
    it first. Isolate Rule 4 specifically with a claim whose only taxonomy
    technology actually IS evidenced somewhere, so Rule 1 cannot pre-empt
    it, proving Rule 4 itself respects the word-count bound."""
    long_claim = "Built a robust Django powered internal reporting toolkit for finance"
    result = precheck_claim(long_claim, _EVIDENCE, _SKILLS)
    assert (
        result.verdict != "unsafe"
        or result.category != "unsupported_action_inference"
    )


# ---------------------------------------------------------------------------
# Metamorphic properties (required test coverage)
# ---------------------------------------------------------------------------


def test_metamorphic_escalating_a_verb_never_stays_safe():
    weak = _check("Used Django")
    strong = _check("Led Django")
    assert weak.verdict != "unsafe"
    assert strong.verdict == "unsafe"


def test_metamorphic_mutating_a_metric_never_stays_safe():
    exact = _check("Cut pipeline runtime 40%")
    mutated = _check("Cut pipeline runtime 90%")
    assert exact.verdict == "safe"
    assert mutated.verdict == "unsafe"


def test_metamorphic_removing_action_evidence_does_not_preserve_an_action_claim():
    """The same action claim is safe when the evidence contains that exact
    action, and unsafe once the evidence is stripped down to a bare skill
    mention -- removing the action evidence must flip the verdict, not
    leave it unchanged."""
    with_action = precheck_claim(
        "Containerized services using Docker",
        "Containerized services with Docker in production",
        _SKILLS,
    )
    without_action = precheck_claim(
        "Containerized services using Docker", "Built REST APIs", _SKILLS
    )
    assert with_action.verdict != "unsafe"
    assert without_action.verdict == "unsafe"


def test_metamorphic_adding_seniority_without_evidence_never_stays_safe():
    plain = _check("Software Engineer")
    escalated = _check("Staff Software Engineer")
    assert plain.verdict != "unsafe"
    assert escalated.verdict == "unsafe"


def test_metamorphic_faithful_generalization_may_remain_safe():
    specific = _check("Cut pipeline runtime 40%")
    generalized = _check("Improved system performance")
    assert specific.verdict == "safe"
    assert generalized.verdict == "safe"


# ---------------------------------------------------------------------------
# Open-world default: unresolved claims are ambiguous, not silently approved
# ---------------------------------------------------------------------------


def test_unresolved_claim_defaults_to_ambiguous_not_safe():
    """A claim that trips none of the deterministic rules must fall to the
    LLM layer, never be silently treated as approved -- absence of a
    detected violation is not evidence of truth."""
    result = _check("Collaborated with the platform team on reliability improvements")
    assert result.verdict == "ambiguous"
    assert result.category is None
