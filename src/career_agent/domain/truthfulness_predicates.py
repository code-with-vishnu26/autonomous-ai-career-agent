r"""Deterministic claim-evidence prechecks (ADR-0044): Layer 1 of the gate.

Formalizes a narrow but principled slice of claim-evidence entailment as
**typed predicate checks over a closed vocabulary**, run before any LLM
call. This is a scope-bounded, deterministic stand-in for full predicate
decomposition (subject/action/object/technology/metric/scope/ownership/
seniority/outcome/employer/temporal/causal, per ADR-0044's research
survey): real NLP would be needed to decompose all twelve reliably, and
this project's own ATS gate already rejected a model-dependent NLP
pipeline (spaCy) in favor of curated-taxonomy, pure-Python matching for
exactly the same determinism reason (ADR-0034). Four predicates are
checked deterministically here -- **technology**, **metric**, **action
verb strength**, **seniority** -- because a closed-vocabulary, regex-based
check on these is reliable and reproducible; **object/scope/causal
relation** are not attempted here and remain Layer 4's (the LLM's) job.

Three-valued output, never a fourth "definitely true" value this module
cannot actually earn:

- ``"safe"``     -- deterministically supported; the gate may approve
  without ever calling the LLM verifier for this claim.
- ``"unsafe"``   -- deterministically contains an unsupported
  escalation/mutation; the gate blocks without calling the LLM verifier.
- ``"ambiguous"`` -- neither rule fires; falls through to the existing
  LLM-backed :class:`~career_agent.core.interfaces.ClaimVerifier`
  (Layer 4), exactly as before ADR-0044.

**Open-world semantics throughout**: absence of a rule firing is not
evidence of truth, only "deterministic rules did not resolve this claim."
``"ambiguous"`` is the honest default; ``"safe"`` requires a rule to
positively earn it.

Rules, in the order applied (first match wins):

1. **Unsupported technology** (``unsafe``, category ``evidence_missing``):
   the claim names a curated-taxonomy technology absent from the evidence
   entirely (not even as a bare skill). The free-text analogue of the
   skills-list structural check the gate already does for ``skills``.
2. **Metric mutation** (``unsafe``, ``metric_unsupported``): the claim
   contains a number not present anywhere in the evidence (a trailing
   ``+`` on an evidenced number is tolerated -- "2M+" is a compatible
   reading of an evidenced "2M", not a mutation).
3. **Seniority escalation** (``unsafe``, ``unsupported_seniority``): the
   claim contains a title/seniority word absent from the evidence.
4. **Unsupported action inference** (``unsafe``,
   ``unsupported_action_inference``): the claim pairs an action/competency
   word (a verb, or a competency noun like "design"/"architecture") with a
   technology that is evidenced *only* as a bare skills-list token --
   never co-occurring with any verb/competency word in the contextual
   (position/highlights) evidence. A skill noun alone does not prove an
   action (ADR-0044) -- this is the rule that reverses the two matrix
   cases (#9 Docker, #11 PostgreSQL) that used to assume it did.
5. **Ownership-verb escalation** (``unsafe``,
   ``unsupported_action_inference``): the claim's strongest action verb
   outranks the strongest verb evidenced anywhere in the contextual text
   (see ``_VERB_RANK`` -- "architected"/"led"/"owned" outrank
   "built"/"used"). Catches matrix case #1 (built -> architected).
6. **Safe abstraction** (``safe``): none of the above fired, the claim
   introduces no technology/number/seniority word beyond the evidence,
   and its strongest verb (if any) does not exceed the evidence's
   strongest verb rank. A specific, supported claim weakened into a
   vaguer, non-quantified generalization that preserves direction and
   introduces nothing new -- matrix case #8 ("cut runtime 40%" ->
   "improved performance").
7. Otherwise: ``ambiguous``.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from .skills_taxonomy import HARD_SKILLS, SOFT_SKILLS

_ALL_TECH = sorted(HARD_SKILLS | SOFT_SKILLS, key=len, reverse=True)

#: Action/ownership strength, low to high. A claim's strongest verb must
#: not exceed the strongest verb evidenced anywhere in the contextual
#: text -- exceeding it is an unsupported ownership/scope escalation.
#: Multi-word keys are checked before single-word ones (sorted by length).
_VERB_RANK: dict[str, int] = {
    "used": 1,
    "worked with": 1,
    "worked on": 1,
    "improved": 1,
    "supported": 1,
    "helped": 1,
    "assisted": 1,
    "built": 2,
    "developed": 2,
    "implemented": 2,
    "created": 2,
    "wrote": 2,
    "containerized": 2,
    "deployed": 2,
    "integrated": 2,
    "maintained": 2,
    "designed": 3,
    "engineered": 3,
    "architected": 4,
    "led": 4,
    "owned": 4,
    "managed": 4,
    "directed": 4,
    "headed": 4,
}
_VERBS_BY_LENGTH = sorted(_VERB_RANK, key=len, reverse=True)

#: Competency/action *nouns* -- "database design (PostgreSQL)" makes an
#: action-shaped claim (did design work) without using a verb at all.
#: Treated as rank-3 (same as "designed") wherever they appear.
_ACTION_NOUNS = {"design", "architecture", "engineering", "administration"}

#: Rule 4 (skill-only action inference) is bounded to claims this short --
#: see the rule's own comment for why.
_RULE4_MAX_WORDS = 6

#: Rule 4 only fires at this verb rank or above: rank-1 verbs ("used",
#: "worked with", "improved") are near-synonyms of "has this skill" and a
#: bare skills-list mention reasonably supports them; rank >= 2 verbs
#: ("built", "containerized", "designed", "architected", ...) assert a
#: specific accomplishment a skill-list entry alone does not evidence.
_RULE4_MIN_VERB_RANK = 2

#: Closed vocabulary of vague, non-quantified outcome words a "safe
#: abstraction" (Rule 6) is allowed to introduce without literal evidence
#: -- "improved system performance" is a legitimate weakening of a
#: specific evidenced fact even though the word "performance" itself
#: never appears in the evidence.
_NEUTRAL_OUTCOME_WORDS = {
    "performance",
    "efficiency",
    "quality",
    "reliability",
    "scalability",
    "productivity",
    "throughput",
    "system",
    "systems",
    "process",
    "processes",
    "workflow",
    "workflows",
    "speed",
    "stability",
}

_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it of on or the to "
    "with we you your our their this that will would using use via under "
    "over across through into onto".split()
)
_WORD = re.compile(r"[a-zA-Z][a-zA-Z\-]{2,}")

_SENIORITY_TERMS = {
    "senior",
    "staff",
    "principal",
    "lead",
    "director",
    "head",
    "vp",
    "vice president",
    "chief",
    "manager",
}

_NUMBER = re.compile(r"\d+(?:\.\d+)?\s*[%kmb]?", re.IGNORECASE)
_WORD_BOUNDARY_CACHE: dict[str, re.Pattern[str]] = {}


def _casefold(text: str) -> str:
    return " ".join(text.casefold().split())


def _contains_phrase(haystack: str, phrase: str) -> bool:
    """Word-boundary match, tolerating one trailing 's'.

    Same convention as ``ats_scoring._keyword_pattern`` -- "REST API" must
    match "REST APIs", "Docker" must match a stray "Dockers" typo the
    same way.
    """
    pattern = _WORD_BOUNDARY_CACHE.get(phrase)
    if pattern is None:
        pattern = re.compile(rf"(?<!\w){re.escape(phrase)}s?(?!\w)")
        _WORD_BOUNDARY_CACHE[phrase] = pattern
    return pattern.search(haystack) is not None


def _technologies_in(text: str) -> set[str]:
    normalized = _casefold(text)
    return {
        tech for tech in _ALL_TECH if _contains_phrase(normalized, tech.casefold())
    }


def _numbers_in(text: str) -> set[str]:
    return {
        match.group(0).replace(" ", "").casefold() for match in _NUMBER.finditer(text)
    }


def _numbers_compatible(claim_numbers: set[str], evidence_numbers: set[str]) -> bool:
    """Whether every claim number is evidenced, tolerating a trailing '+'."""
    for number in claim_numbers:
        bare = number.rstrip("+")
        if number in evidence_numbers or bare in evidence_numbers:
            continue
        return False
    return True


def _strongest_verb_rank(text: str) -> int:
    """Highest verb/action-noun rank found in ``text``; 0 if none at all."""
    normalized = _casefold(text)
    best = 0
    for verb in _VERBS_BY_LENGTH:
        if _contains_phrase(normalized, verb):
            best = max(best, _VERB_RANK[verb])
    for noun in _ACTION_NOUNS:
        if _contains_phrase(normalized, noun):
            best = max(best, 3)
    return best


def _content_words(text: str) -> set[str]:
    """Lower-cased, non-stopword alphabetic words (length >= 3)."""
    return {w for w in _WORD.findall(text.casefold()) if w not in _STOPWORDS}


def _words_in_phrases(phrases: set[str] | frozenset[str]) -> set[str]:
    """Individual words making up a set of (possibly multi-word) phrases.

    E.g. {"worked with"} -> {"worked", "with"} -- so a phrase-level
    vocabulary (technologies, verb keys) can be checked against
    single-token content words.
    """
    words: set[str] = set()
    for phrase in phrases:
        words.update(_WORD.findall(phrase.casefold()))
    return words


class PrecheckResult(BaseModel):
    """One deterministic Layer-1 verdict on a single claim (ADR-0044)."""

    verdict: Literal["safe", "unsafe", "ambiguous"]
    category: (
        Literal[
            "skill_not_found",
            "evidence_missing",
            "metric_unsupported",
            "unsupported_action_inference",
            "unsupported_seniority",
        ]
        | None
    ) = None
    detail: str = ""


_AMBIGUOUS = PrecheckResult(verdict="ambiguous")


def precheck_claim(
    claim_text: str, contextual_text: str, skills_text: str
) -> PrecheckResult:
    """Layer 1: resolve ``claim_text`` deterministically, or defer to the LLM.

    ``contextual_text`` is the evidence actually describing *work done*
    (position titles, work/project highlights) -- the only place an
    action can be considered demonstrated. ``skills_text`` is the bare
    skills list: real evidence that a technology is known, but never by
    itself evidence that it was used to do anything (ADR-0044).
    """
    full_evidence = f"{contextual_text} {skills_text}"
    claim_tech = _technologies_in(claim_text)
    evidence_tech = _technologies_in(full_evidence)

    # Rule 1: a named technology with zero evidence anywhere.
    unsupported_tech = claim_tech - evidence_tech
    if unsupported_tech:
        return PrecheckResult(
            verdict="unsafe",
            category="evidence_missing",
            detail=(
                f"claim names {sorted(unsupported_tech)!r}, absent from all "
                f"evidence (not even as a skill)"
            ),
        )

    # Rule 2: a number the evidence never states (tolerating a trailing '+').
    claim_numbers = _numbers_in(claim_text)
    evidence_numbers = _numbers_in(full_evidence)
    if not _numbers_compatible(claim_numbers, evidence_numbers):
        unsupported = {
            n
            for n in claim_numbers
            if n not in evidence_numbers and n.rstrip("+") not in evidence_numbers
        }
        return PrecheckResult(
            verdict="unsafe",
            category="metric_unsupported",
            detail=f"claim states {sorted(unsupported)!r}, not present in evidence",
        )

    # Rule 3: a seniority/title word the evidence never uses.
    claim_cf = _casefold(claim_text)
    evidence_cf = _casefold(full_evidence)
    unsupported_seniority = {
        term
        for term in _SENIORITY_TERMS
        if _contains_phrase(claim_cf, term) and not _contains_phrase(evidence_cf, term)
    }
    if unsupported_seniority:
        return PrecheckResult(
            verdict="unsafe",
            category="unsupported_seniority",
            detail=(
                f"claim asserts seniority {sorted(unsupported_seniority)!r} "
                f"absent from evidence"
            ),
        )

    # Rule 4: an action/competency word (rank >= _RULE4_MIN_VERB_RANK --
    # familiarity verbs like "used" are exempt, see the constant's own
    # comment) paired with a technology that is only ever a bare
    # skills-list entry -- never demonstrated in context. Bounded to short
    # claims (<= _RULE4_MAX_WORDS) on purpose: this project has no parser
    # to tell whether a technology token in a longer claim is actually the
    # object of the action word or an incidental modifier of some other,
    # separately-fabricatable object (matrix case #10's "Built a
    # Django-based microservices platform..." -- Django is real and
    # skill-only, but the disputed content is "microservices platform",
    # not Django; a longer claim is deliberately left to Layer 4 rather
    # than guessed at here).
    claim_action_rank = _strongest_verb_rank(claim_text)
    if (
        claim_tech
        and claim_action_rank >= _RULE4_MIN_VERB_RANK
        and len(claim_text.split()) <= _RULE4_MAX_WORDS
    ):
        skill_only = {
            tech
            for tech in claim_tech
            if not _contains_phrase(_casefold(contextual_text), tech.casefold())
        }
        if skill_only:
            return PrecheckResult(
                verdict="unsafe",
                category="unsupported_action_inference",
                detail=(
                    f"claim asserts an action/competency involving "
                    f"{sorted(skill_only)!r}, which appears only in the "
                    f"skills list, never in any work/project evidence -- a "
                    f"skill noun alone does not prove the action was performed"
                ),
            )

    # Rule 5: an ownership/action verb stronger than anything evidenced.
    claim_rank = _strongest_verb_rank(claim_text)
    evidence_rank = _strongest_verb_rank(contextual_text)
    if claim_rank > evidence_rank:
        return PrecheckResult(
            verdict="unsafe",
            category="unsupported_action_inference",
            detail=(
                f"claim's strongest action word outranks (level {claim_rank}) "
                f"anything evidenced (level {evidence_rank}) -- e.g. "
                f"'architected'/'led' claimed where evidence only shows "
                f"'built'/'used'"
            ),
        )

    # Rule 6: safe abstraction -- nothing new introduced, direction
    # preserved, AND every remaining content word is explained (either it
    # is a recognized vague outcome word, or it is literally evidenced).
    # This last requirement is what keeps "ambiguous" reachable: without
    # it, ANY claim that merely avoids rules 1-5's violations would
    # qualify as "safe" -- exactly the "absence of contradiction is
    # evidence of support" mistake open-world reasoning forbids. Any
    # claim number reaching this point already passed Rule 2 (evidenced).
    no_new_tech = not (claim_tech - evidence_tech)
    no_verb_escalation = claim_rank <= evidence_rank
    if no_new_tech and no_verb_escalation:
        excluded_words = (
            _words_in_phrases(claim_tech)
            | _words_in_phrases(frozenset(_VERB_RANK))
            | _ACTION_NOUNS
            | _SENIORITY_TERMS
        )
        unexplained = {
            word
            for word in _content_words(claim_text)
            if word not in excluded_words
            and word not in _NEUTRAL_OUTCOME_WORDS
            and word not in _content_words(full_evidence)
        }
        if not unexplained:
            return PrecheckResult(
                verdict="safe",
                detail=(
                    "vaguer generalization introducing no new technology, "
                    "metric, escalated verb, or unexplained content word"
                ),
            )

    return _AMBIGUOUS
