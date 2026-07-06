"""Formal execution-safety boundary for irreversible application actions.

Phase 24 / ADR-0050. Pure domain layer: stdlib only, no I/O, no LLM, no
network, no dependency on any other project layer (domain-purity
import-linter contract). This module is the deterministic gate that any
future real ``Applicator`` wiring MUST pass through before an irreversible
external submission -- the exact prerequisite ADR-0049 named as deferred.

**Nothing in this repository submits an application today.** A repository
audit (Phase 24) confirmed no composition-root command (`career-agent
apply`/`auto`) imports or calls any concrete ``Applicator`` -- the three
applicators exist and are unit-tested against fakes, but are unreachable
from the CLI. This module therefore does not *enable* execution; it
defines, in one deterministic place, the conditions under which execution
would be permitted, so that a future phase wiring a real executor cannot
do so without satisfying every condition here. Until then the CLI wires
this gate with ``executor_available=False``, so it always refuses -- which
is exactly today's behavior ("Nothing was actually sent"), now made
explicit, reasoned, and journaled rather than implicit.

Design rules (from the Phase 24 brief):
- fail closed: ``execute_allowed`` returns ``allowed=True`` only when every
  positive condition holds; any single adverse condition refuses.
- ``OUTCOME_UNCERTAIN`` never automatically permits a retry. An ambiguous
  external outcome stays ambiguous; only a separately-established
  definite-non-submission (or human resolution, out of this module's
  scope) could re-open a retry, never this module on its own.
- no fabricated certainty: acknowledgement evidence maps to an outcome by
  a fixed, total function (``outcome_from_ack``) in which ``AMBIGUOUS``
  can only become ``OUTCOME_UNCERTAIN``, never a definite result.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum


class SubmissionOutcome(Enum):
    """The outcome of an external submission attempt.

    ``OUTCOME_UNCERTAIN`` is deliberately distinct from
    ``DEFINITELY_NOT_SUBMITTED``: a timeout, a lost connection after the
    request was sent, or a crash mid-acknowledgement leaves the remote
    system possibly-submitted. Collapsing that into "failed" would license
    an unsafe retry (a duplicate real application), which this whole module
    exists to prevent.
    """

    NOT_ATTEMPTED = "not_attempted"
    DEFINITELY_NOT_SUBMITTED = "definitely_not_submitted"
    DEFINITELY_SUBMITTED = "definitely_submitted"
    OUTCOME_UNCERTAIN = "outcome_uncertain"


class SourcePolicy(Enum):
    """What automation a source permits, by project policy (not capability).

    ``MANUAL_ONLY`` covers ADR-0036's Tier-C sources (LinkedIn/Indeed/etc.,
    no permitted programmatic path -- standing invariant 7) and anything
    else the project has not explicitly cleared for automation.
    ``ASSISTED`` is a human-in-the-loop browser flow (confirmation +
    live-page pauses, ADR-0020/0032). ``AUTOMATED`` is fully unattended
    submission -- **no source currently maps here**, since ADR-0027
    recorded every Tier-1 direct-API path dead across Greenhouse/Lever/
    Ashby. ``UNKNOWN`` is the fail-closed default for an unrecognized
    source and is treated exactly as ``MANUAL_ONLY`` for permission.
    """

    MANUAL_ONLY = "manual_only"
    ASSISTED = "assisted"
    AUTOMATED = "automated"
    UNKNOWN = "unknown"


class AckClass(Enum):
    """Deterministic classification of an executor's acknowledgement.

    A browser click is not proof of submission; a 2xx is not always
    semantic success; a timeout is not proof of failure. Only
    provider-specific positive evidence (a confirmation receipt, an
    application id) may yield ``DEFINITE_SUCCESS``; only positive evidence
    of non-submission may yield ``DEFINITE_FAILURE``; everything else --
    including "no exception was raised" -- is ``AMBIGUOUS``.
    """

    DEFINITE_SUCCESS = "definite_success"
    DEFINITE_FAILURE = "definite_failure"
    AMBIGUOUS = "ambiguous"


#: The one safety-critical, total mapping from evidence to outcome. The
#: load-bearing line is ``AMBIGUOUS -> OUTCOME_UNCERTAIN``: ambiguous
#: evidence can never become a definite result. There is no default-to-
#: success and no default-to-failure path.
_ACK_TO_OUTCOME: dict[AckClass, SubmissionOutcome] = {
    AckClass.DEFINITE_SUCCESS: SubmissionOutcome.DEFINITELY_SUBMITTED,
    AckClass.DEFINITE_FAILURE: SubmissionOutcome.DEFINITELY_NOT_SUBMITTED,
    AckClass.AMBIGUOUS: SubmissionOutcome.OUTCOME_UNCERTAIN,
}


def outcome_from_ack(ack: AckClass) -> SubmissionOutcome:
    """Map an acknowledgement class to a submission outcome, totally."""
    return _ACK_TO_OUTCOME[ack]


#: Prior outcomes from which a fresh attempt is *never* automatically
#: safe, regardless of anything else. Submitting again after a definite
#: submission is a guaranteed duplicate; submitting again after an
#: uncertain outcome risks one.
_RETRY_UNSAFE_PRIOR: frozenset[SubmissionOutcome] = frozenset(
    {SubmissionOutcome.DEFINITELY_SUBMITTED, SubmissionOutcome.OUTCOME_UNCERTAIN}
)

#: Policies under which no automated execution is ever permitted.
_NON_AUTOMATABLE_POLICY: frozenset[SourcePolicy] = frozenset(
    {SourcePolicy.MANUAL_ONLY, SourcePolicy.UNKNOWN}
)


# Closed-vocabulary reason codes. Every refusal names exactly one.
REASON_ALLOWED = "ALLOWED"
REASON_NO_EXECUTOR = "REFUSED_NO_EXECUTOR"
REASON_MANUAL_ONLY_SOURCE = "REFUSED_MANUAL_ONLY_SOURCE"
REASON_UNKNOWN_SOURCE_POLICY = "REFUSED_UNKNOWN_SOURCE_POLICY"
REASON_NO_CONFIRMATION = "REFUSED_NO_CONFIRMATION"
REASON_ARTIFACT_MISMATCH = "REFUSED_ARTIFACT_MISMATCH"
REASON_PRIOR_SUBMITTED = "REFUSED_PRIOR_SUBMITTED"
REASON_PRIOR_UNCERTAIN = "REFUSED_PRIOR_UNCERTAIN"
REASON_UNRESOLVED_INTENT = "REFUSED_UNRESOLVED_INTENT"


@dataclass(frozen=True)
class ExecutionRequest:
    """Every factor the execution boundary considers, and nothing else.

    Deliberately all-primitive: the boundary consumes *verdicts* (a bool
    for artifact integrity, an enum for the prior outcome), never raw
    resumes/tokens/credentials -- so it stays pure, exhaustively
    enumerable, and impossible to make a network or LLM call from.
    """

    source_policy: SourcePolicy
    executor_available: bool
    confirmation_present: bool
    artifact_matches: bool
    prior_outcome: SubmissionOutcome
    journal_has_unresolved_intent: bool


@dataclass(frozen=True)
class ExecutionDecision:
    """The boundary's verdict: whether to execute, and the single reason."""

    allowed: bool
    reason: str


def retry_allowed(
    prior_outcome: SubmissionOutcome,
    *,
    unresolved_intent: bool,
    source_policy: SourcePolicy,
) -> bool:
    """Is a fresh external attempt admissible given only prior state?

    The mandatory safety property (Phase 24 Section 3):
    ``OUTCOME_UNCERTAIN`` and ``DEFINITELY_SUBMITTED`` both yield ``False``
    unconditionally. A definite *pre-effect* failure
    (``DEFINITELY_NOT_SUBMITTED``) or a never-attempted opportunity is
    retryable, but only under an automatable policy and with no dangling
    execution-intent event -- "retryable according to policy," never
    "retryable because the last thing failed."
    """
    if source_policy in _NON_AUTOMATABLE_POLICY:
        return False
    if unresolved_intent:
        return False
    return prior_outcome not in _RETRY_UNSAFE_PRIOR


def execute_allowed(request: ExecutionRequest) -> ExecutionDecision:
    """Fail-closed permission decision for one irreversible external action.

    Checks adverse conditions in a fixed priority order and returns the
    first one that fires as the (single) refusal reason. Returns
    ``allowed=True`` only when none fire -- i.e. an executor exists, the
    source policy permits automation, a human confirmation is present, the
    confirmed artifact still matches, there is no dangling execution
    intent, and the prior outcome is retry-safe. The boolean is robust to
    reason-ordering: every adverse condition is independently sufficient
    to refuse.
    """
    if not request.executor_available:
        return ExecutionDecision(False, REASON_NO_EXECUTOR)
    if request.source_policy == SourcePolicy.UNKNOWN:
        return ExecutionDecision(False, REASON_UNKNOWN_SOURCE_POLICY)
    if request.source_policy == SourcePolicy.MANUAL_ONLY:
        return ExecutionDecision(False, REASON_MANUAL_ONLY_SOURCE)
    if not request.confirmation_present:
        return ExecutionDecision(False, REASON_NO_CONFIRMATION)
    if not request.artifact_matches:
        return ExecutionDecision(False, REASON_ARTIFACT_MISMATCH)
    if request.prior_outcome == SubmissionOutcome.DEFINITELY_SUBMITTED:
        return ExecutionDecision(False, REASON_PRIOR_SUBMITTED)
    if request.prior_outcome == SubmissionOutcome.OUTCOME_UNCERTAIN:
        return ExecutionDecision(False, REASON_PRIOR_UNCERTAIN)
    if request.journal_has_unresolved_intent:
        return ExecutionDecision(False, REASON_UNRESOLVED_INTENT)
    return ExecutionDecision(True, REASON_ALLOWED)


#: Sources that never have a permitted programmatic apply path (ADR-0036
#: Tier C, standing invariant 7). Kept as a named set so the mapping is
#: auditable, not buried in branches.
_MANUAL_ONLY_SOURCES: frozenset[str] = frozenset(
    {"web_search", "career_page", "hn", "yc"}
)

#: ATS kinds with a human-in-the-loop browser flow in this codebase
#: (Greenhouse real, Lever real per ADR-0035, Ashby stub) -- ASSISTED, not
#: AUTOMATED, because a human still confirms and clears live-page pauses.
_ASSISTED_ATS_KINDS: frozenset[str] = frozenset({"greenhouse", "lever", "ashby"})


def resolve_source_policy(source: str, ats_kind: str | None) -> SourcePolicy:
    """Classify a source's automation policy, deterministically, fail-closed.

    ``ats_kind`` is the result of ``domain.ats_urls.resolve_ats_kind`` on
    the opportunity's ``source_url`` (resolved by the caller so this module
    stays free of URL-parsing concerns). No source maps to ``AUTOMATED``:
    every automatable target this codebase knows is a human-in-the-loop
    browser flow (``ASSISTED``), because ADR-0027 recorded every Tier-1
    fully-automated direct-API path dead. An unrecognized source is
    ``UNKNOWN`` -- treated as manual-only for permission, never guessed
    into automatability.
    """
    if source in _MANUAL_ONLY_SOURCES:
        return SourcePolicy.MANUAL_ONLY
    if ats_kind in _ASSISTED_ATS_KINDS:
        return SourcePolicy.ASSISTED
    if source in {"ats_api", "job_board"}:
        # A recognized structured source, but with no resolvable automatable
        # ATS target -- fail closed to manual rather than assume a path.
        return SourcePolicy.MANUAL_ONLY
    return SourcePolicy.UNKNOWN


def confirmed_artifact_digest(
    *,
    opportunity_id: str,
    rendered_content: str,
    target: str,
    tier: str,
    normalized_answers: dict[str, str] | None = None,
) -> str:
    """Reference canonical digest of what a human confirmed for submission.

    Provided as the concrete contract a future executor uses to detect
    post-confirmation mutation (Phase 24 Section 4): the boundary itself
    consumes only the resulting ``artifact_matches`` boolean, never
    recomputes this. Canonicalization is order-independent for
    ``normalized_answers`` (a mapping's insertion order must not change the
    digest -- tested) and uses an unambiguous field separator so distinct
    field boundaries cannot collide. This is an integrity digest for
    equality comparison, **not** a cryptographic authenticity claim.
    """
    answers = normalized_answers or {}
    canonical = "\x1f".join(
        [
            opportunity_id,
            rendered_content,
            target,
            tier,
            *(f"{k}={answers[k]}" for k in sorted(answers)),
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
