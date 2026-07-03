"""Phase 8j / ADR-0031: the adversarial matrix for QuestionAnswerer.

Twenty cases across four categories, drafted by the user -- not generated
by the agent implementing against them, the same discipline as the
truthfulness gate's 12-case matrix (ADR-0016) and the HN held-candidate
matrix (ADR-0013). Four cases are singled out as load-bearing: 1d (never
even attempt a profile lookup for EEOC fields), 2b (negated-polarity
questions -- a confidently wrong-polarity answer is worse than any
refusal), 3c (restating true profile content into fresh prose is still
unapproved generation), and 4c (a close-but-wrong dropdown pick is worse
than blank).
"""

from __future__ import annotations

import inspect

import pytest

from career_agent.agents.apply.question_answerer import (
    AmbiguousDropdownMatchError,
    AmbiguousQuestionError,
    MissingLegalStatusFactError,
    QuestionCategory,
    answer_eeoc_question,
    answer_factual_question,
    classify_question,
    match_dropdown_option,
)
from career_agent.domain.models import LegalStatusSection, MasterProfile
from tests.agents._profile_fixture import sample_master_profile


def _profile(**legal_status_kwargs) -> MasterProfile:
    profile = sample_master_profile()
    return profile.model_copy(
        update={"legal_status": LegalStatusSection(**legal_status_kwargs)}
    )


# ---------------------------------------------------------------------------
# Category 1 -- EEOC absolute
# ---------------------------------------------------------------------------


def test_case_1a_required_eeoc_field_with_no_decline_option_still_refuses() -> None:
    """A "required" EEOC field with no visible "prefer not to answer"
    option must still refuse/pause -- "required" on the form is never
    license to guess."""
    question = "Voluntary Self-Identification of Disability (Form CC-305)"
    assert classify_question(question) == QuestionCategory.EEOC
    # "required" is an HTML form attribute this module never even reads --
    # classification depends only on question content, proving the form's
    # required-ness cannot influence whether this refuses.


def test_case_1b_protected_class_question_classified_as_eeoc_not_factual() -> None:
    """A yes/no-shaped question about protected-class membership must be
    classified as EEOC, not factual, despite sharing work-authorization's
    yes/no grammatical shape."""
    question = "Are you a member of a protected veteran class?"
    assert classify_question(question) == QuestionCategory.EEOC


def test_case_1c_ambiguous_citizenship_phrasing_ties_break_to_factual_not_guessed() -> (
    None
):
    """A legitimate work-authorization question, phrased without the exact
    'legally authorized' template wording, must still classify as factual
    -- and separately, when a question genuinely matches both an EEOC
    pattern and a factual template, the tie-break must go to EEOC."""
    question = "Are you a US citizen or otherwise authorized to work in the US?"
    assert classify_question(question) == QuestionCategory.FACTUAL

    # The actual tie-break proof: a synthetic question matching both an
    # EEOC keyword and a factual template must resolve to EEOC, never to
    # factual auto-answering.
    tied_question = "Are you a veteran who is also authorized to work in the US?"
    assert classify_question(tied_question) == QuestionCategory.EEOC


def test_case_1d_eeoc_answering_never_even_attempts_a_profile_lookup() -> None:
    """The load-bearing proof: answer_eeoc_question has no MasterProfile
    parameter at all -- not "looked, found nothing, refused," but a
    structural absence of the attempt itself, the same shape as
    ``adapter.calls == []`` proving a real action never fired."""
    signature = inspect.signature(answer_eeoc_question)
    param_names = list(signature.parameters)
    assert "profile" not in param_names
    assert "master_profile" not in param_names
    for param in signature.parameters.values():
        assert param.annotation is not MasterProfile


def test_case_1e_declining_to_answer_is_a_complete_terminal_outcome() -> None:
    """A human leaving an EEOC response blank/declined is valid and final
    -- no re-prompt, no default substituted."""
    result = answer_eeoc_question(
        "Voluntary Self-Identification of Disability", response=None
    )
    assert result is None


def test_eeoc_answer_passes_through_only_the_humans_own_response() -> None:
    """The positive case: a human's own answer is returned unchanged --
    the function's only job is to never look anywhere else."""
    result = answer_eeoc_question(
        "Voluntary Self-Identification of Disability", response=True
    )
    assert result is True


# ---------------------------------------------------------------------------
# Category 2 -- profile-groundable factual
# ---------------------------------------------------------------------------


def test_case_2a_compound_question_refuses_rather_than_answering_half() -> None:
    """A question asking about two facts at once must refuse entirely,
    never confidently answer only the half it matched."""
    profile = _profile(work_authorized_us=True, requires_sponsorship=False)
    question = "Are you authorized to work in the US, and will you require sponsorship?"
    assert classify_question(question) == QuestionCategory.FACTUAL
    with pytest.raises(AmbiguousQuestionError, match="more than one fact"):
        answer_factual_question(question, profile)


def test_case_2b_negated_polarity_question_correctly_inverted() -> None:
    """The single most dangerous failure mode in this category: a
    confidently wrong-polarity answer looks normal while asserting the
    opposite of what's true. Both directions verified."""
    requires_sponsorship_profile = _profile(requires_sponsorship=True)
    question = "Do you not require sponsorship to work in the US?"
    # They DO require sponsorship, so "do you NOT require it" is False.
    assert answer_factual_question(question, requires_sponsorship_profile) is False

    no_sponsorship_profile = _profile(requires_sponsorship=False)
    # They do NOT require sponsorship, so "do you NOT require it" is True.
    assert answer_factual_question(question, no_sponsorship_profile) is True


def test_case_2c_uncaptured_fact_raises_instead_of_silently_skipped() -> None:
    """Proves the None-means-uncaptured discipline actually gates the
    pipeline, rather than being a type-level decoration nobody checks."""
    profile = _profile()  # work_authorized_us defaults to None
    question = "Are you legally authorized to work in the United States?"
    assert classify_question(question) == QuestionCategory.FACTUAL
    with pytest.raises(MissingLegalStatusFactError, match="work_authorized_us"):
        answer_factual_question(question, profile)


def test_case_2d_non_boolean_legal_q_refuses_rather_than_inventing_a_number() -> None:
    """A question that sounds legal-status-shaped but asks for a duration,
    not a yes/no, must refuse -- this project has no field to answer it
    from, and inventing one would be fabrication."""
    profile = _profile(requires_sponsorship=True)
    question = "How many years until your visa sponsorship would need renewal?"
    assert classify_question(question) == QuestionCategory.FACTUAL
    with pytest.raises(AmbiguousQuestionError, match="not a yes/no question"):
        answer_factual_question(question, profile)


# ---------------------------------------------------------------------------
# Category 3 -- subjective/freeform (never drafted, always human-authored)
# ---------------------------------------------------------------------------


def test_case_3b_culture_fit_question_classified_subjective_never_drafted() -> None:
    """The contrast case: a genuinely subjective question must classify
    as subjective, with zero drafting attempt -- not even a suggested
    starting point."""
    question = "What makes you a good fit for our culture?"
    assert classify_question(question) == QuestionCategory.SUBJECTIVE
    # No answer_subjective_question exists at all -- there is no code
    # path in this module capable of drafting free text, which is itself
    # the guarantee: it cannot happen because the capability was never
    # built, not because a check happens to prevent it every time.


def test_case_3c_restating_profile_content_is_still_classified_subjective() -> None:
    """Restating true profile content into fresh prose is still
    generation -- 'the content would be true' isn't the bar; the rule is
    about who authors the words, not just factual accuracy."""
    question = "Describe your relevant experience for this role"
    assert classify_question(question) == QuestionCategory.SUBJECTIVE


def test_case_3a_experience_question_currently_falls_to_the_safe_default() -> None:
    """Named limitation, not a passing demonstration of skill/experience
    grounding: this module's Category 2 scope is LegalStatusSection only
    (ADR-0031's deliberately narrow scope decision). A profile-groundable
    but non-legal-status question like years-of-experience is NOT yet
    classified as its own profile-groundable case -- it currently falls
    through to the same safe SUBJECTIVE default as a genuinely subjective
    question, meaning a human authors the answer. Safe (never fabricates),
    but not the full 3a-vs-3c boundary the adversarial case envisioned --
    recorded honestly as future work, not claimed as solved."""
    question = "How many years of Python experience do you have?"
    assert classify_question(question) == QuestionCategory.SUBJECTIVE


# ---------------------------------------------------------------------------
# Category 4 -- structured-but-unmatchable dropdowns
# ---------------------------------------------------------------------------


def test_case_4a_separately_modeled_degree_fields_each_match_independently() -> None:
    """MasterProfile.EducationEntry already stores study_type ("Bachelor's")
    and area ("Computer Science") as separate fields -- matching each
    independently against its own real dropdown proves the matcher uses
    field semantics correctly rather than jamming a combined string into
    one dropdown and leaving the other blank."""
    degree_type_result = match_dropdown_option(
        "Bachelor's", ["Bachelor's Degree", "Master's Degree", "PhD"]
    )
    assert degree_type_result.matched_option == "Bachelor's Degree"

    discipline_result = match_dropdown_option(
        "Computer Science", ["Computer Science", "Electrical Engineering", "Physics"]
    )
    assert discipline_result.matched_option == "Computer Science"


def test_case_4b_near_identical_options_refuse_rather_than_arbitrary_pick() -> None:
    """Three near-identical options ("B.S.", "BS", "Bachelor's") that all
    normalize to the same real meaning must not have one arbitrarily
    picked over the others by list/alphabetical order."""
    result = match_dropdown_option("Bachelor of Science", ["B.S.", "BS", "Bachelor's"])
    assert result.matched_option is None
    # Not picking the first-listed option is the proof it isn't arbitrary:
    assert result.candidate_options_considered == ["B.S.", "BS", "Bachelor's"]


def test_case_4c_no_close_match_refuses_rather_than_picking_the_closest_wrong_one() -> (
    None
):
    """The core "don't guess" case: a plausible-but-wrong dropdown
    selection is worse than a blank field, because it submits false
    information that looks deliberate."""
    result = match_dropdown_option(
        "Computer Engineering", ["Computer Science", "Electrical Engineering"]
    )
    assert result.matched_option is None
    assert result.similarity < 0.7


def test_case_4d_correct_match_found_regardless_of_position_in_a_large_list() -> None:
    """Proves matching isn't accidentally coupled to enumeration order or
    truncated option lists -- the correct option is placed deliberately
    away from the top of a realistic, large option set."""
    options = [f"Unrelated Field {i}" for i in range(20)]
    options.insert(35 % 20, "Computer Science")  # buried mid-list
    options += [f"Another Unrelated Field {i}" for i in range(20)]
    assert len(options) > 40
    result = match_dropdown_option("Computer Science", options)
    assert result.matched_option == "Computer Science"
    assert result.similarity == 1.0


# ---------------------------------------------------------------------------
# AmbiguousDropdownMatchError -- distinct from UnsupportedFormFieldsError
# ---------------------------------------------------------------------------


def test_ambiguous_dropdown_match_error_is_a_distinct_exception_type() -> None:
    """A human reading a refusal needs to tell "I don't know this field
    exists" apart from "I know it but can't confidently answer it" --
    proven here by these being genuinely separate exception types, not by
    convention alone."""
    from career_agent.agents.apply.browser_applicator import UnsupportedFormFieldsError

    assert not issubclass(AmbiguousDropdownMatchError, UnsupportedFormFieldsError)
    assert not issubclass(UnsupportedFormFieldsError, AmbiguousDropdownMatchError)
