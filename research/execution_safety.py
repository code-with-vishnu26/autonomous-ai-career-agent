"""Phase 24 (ADR-0050): exhaustive verification of the execution boundary.

Mirrors ``research/decision_benchmarks.py``'s precedent: a top-level,
offline module (not part of the shipped ``career_agent`` package) that
imports the production execution boundary *unmodified* and enumerates its
entire finite input space to check safety invariants exhaustively -- not a
sample, the whole space. Nothing here makes a network call, an LLM call,
or costs money.

The input space is small enough to enumerate completely:

    |SourcePolicy| * |executor_available| * |confirmation_present|
        * |artifact_matches| * |SubmissionOutcome| * |unresolved_intent|
    = 4 * 2 * 2 * 2 * 4 * 2 = 256 combinations.

Every combination is checked against the Section-12 safety invariants and
the Section-10 metamorphic properties. A returned empty counterexample
list is an exhaustive proof over this space, not evidence from examples.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from career_agent.domain.execution import (
    AckClass,
    ExecutionRequest,
    SourcePolicy,
    SubmissionOutcome,
    execute_allowed,
    outcome_from_ack,
    retry_allowed,
)

_POLICIES = tuple(SourcePolicy)
_OUTCOMES = tuple(SubmissionOutcome)
_BOOLS = (False, True)

#: The outcomes from which a fresh attempt must never be auto-permitted.
_RETRY_UNSAFE = frozenset(
    {SubmissionOutcome.DEFINITELY_SUBMITTED, SubmissionOutcome.OUTCOME_UNCERTAIN}
)
_AUTOMATABLE = frozenset({SourcePolicy.ASSISTED, SourcePolicy.AUTOMATED})


def all_requests() -> list[ExecutionRequest]:
    """Every point in the boundary's finite input space (exactly 256)."""
    combos = itertools.product(
        _POLICIES, _BOOLS, _BOOLS, _BOOLS, _OUTCOMES, _BOOLS
    )
    return [
        ExecutionRequest(
            source_policy=policy,
            executor_available=executor,
            confirmation_present=confirmation,
            artifact_matches=artifact,
            prior_outcome=prior,
            journal_has_unresolved_intent=intent,
        )
        for policy, executor, confirmation, artifact, prior, intent in combos
    ]


@dataclass(frozen=True)
class InvariantViolation:
    """One request that violated a named safety invariant. Never expected."""

    invariant: str
    request: ExecutionRequest
    allowed: bool
    reason: str


def _positive_characterization_holds(req: ExecutionRequest, allowed: bool) -> bool:
    """``allowed`` iff every positive precondition holds -- the fail-closed law."""
    expected = (
        req.executor_available
        and req.confirmation_present
        and req.artifact_matches
        and req.source_policy in _AUTOMATABLE
        and req.prior_outcome not in _RETRY_UNSAFE
        and not req.journal_has_unresolved_intent
    )
    return allowed == expected


def exhaustive_invariant_search() -> list[InvariantViolation]:
    """Check every request against every Section-12 refusal invariant.

    Returns an empty list iff the boundary satisfies all of them across the
    whole 512-point space.
    """
    violations: list[InvariantViolation] = []
    for req in all_requests():
        decision = execute_allowed(req)
        allowed = decision.allowed
        # (invariant name, condition under which `allowed` must be False)
        must_refuse: list[tuple[str, bool]] = [
            ("I1_no_confirmation", not req.confirmation_present),
            ("I2_manual_only", req.source_policy == SourcePolicy.MANUAL_ONLY),
            (
                "I3_prior_submitted",
                req.prior_outcome == SubmissionOutcome.DEFINITELY_SUBMITTED,
            ),
            (
                "I4_prior_uncertain",
                req.prior_outcome == SubmissionOutcome.OUTCOME_UNCERTAIN,
            ),
            ("I5_artifact_mismatch", not req.artifact_matches),
            ("I6_unresolved_intent", req.journal_has_unresolved_intent),
            ("no_executor", not req.executor_available),
            ("unknown_policy_fail_closed", req.source_policy == SourcePolicy.UNKNOWN),
        ]
        for name, adverse in must_refuse:
            if adverse and allowed:
                violations.append(
                    InvariantViolation(name, req, allowed, decision.reason)
                )
        # The complete positive characterization (fail-closed both ways).
        if not _positive_characterization_holds(req, allowed):
            violations.append(
                InvariantViolation(
                    "positive_characterization", req, allowed, decision.reason
                )
            )
    return violations


@dataclass(frozen=True)
class MetamorphicViolation:
    """A pair where hardening an input made the boundary *more* permissive."""

    property_name: str
    base: ExecutionRequest
    mutated: ExecutionRequest


def exhaustive_metamorphic_search() -> list[MetamorphicViolation]:
    """Adding risk / removing safety evidence must never increase permission.

    Section 10(F). For every request, apply each risk-increasing mutation
    and assert ``allowed`` never flips False -> True. Exhaustive over the
    full space.
    """
    violations: list[MetamorphicViolation] = []
    for req in all_requests():
        base_allowed = execute_allowed(req).allowed
        # Each mutation only *increases risk* / *removes safety evidence*;
        # none may ever flip a refusal into an allow.
        mutations: list[tuple[str, ExecutionRequest]] = [
            (
                "M1_worse_prior_outcome",
                ExecutionRequest(
                    req.source_policy,
                    req.executor_available,
                    req.confirmation_present,
                    req.artifact_matches,
                    worse,
                    req.journal_has_unresolved_intent,
                ),
            )
            for worse in _RETRY_UNSAFE
        ]
        mutations += [
            (
                "M3_artifact_broken",
                ExecutionRequest(
                    req.source_policy,
                    req.executor_available,
                    req.confirmation_present,
                    False,
                    req.prior_outcome,
                    req.journal_has_unresolved_intent,
                ),
            ),
            (
                "M4_policy_to_manual",
                ExecutionRequest(
                    SourcePolicy.MANUAL_ONLY,
                    req.executor_available,
                    req.confirmation_present,
                    req.artifact_matches,
                    req.prior_outcome,
                    req.journal_has_unresolved_intent,
                ),
            ),
            (
                "M5_remove_confirmation",
                ExecutionRequest(
                    req.source_policy,
                    req.executor_available,
                    False,
                    req.artifact_matches,
                    req.prior_outcome,
                    req.journal_has_unresolved_intent,
                ),
            ),
        ]
        for name, mutated in mutations:
            if execute_allowed(mutated).allowed and not base_allowed:
                violations.append(MetamorphicViolation(name, req, mutated))
    return violations


def retry_admissibility_table() -> dict[SubmissionOutcome, bool]:
    """``retry_allowed`` per prior outcome under the friendliest other inputs.

    Fixes ``source_policy=AUTOMATED`` and ``unresolved_intent=False`` (the
    most permissive non-adverse context) and reports whether each prior
    outcome is retryable. The load-bearing rows: OUTCOME_UNCERTAIN and
    DEFINITELY_SUBMITTED are ``False`` even here.
    """
    return {
        outcome: retry_allowed(
            outcome, unresolved_intent=False, source_policy=SourcePolicy.AUTOMATED
        )
        for outcome in _OUTCOMES
    }


def ack_outcome_table() -> dict[AckClass, SubmissionOutcome]:
    """The full acknowledgement -> outcome mapping, for the record.

    The safety-critical row is ``AMBIGUOUS -> OUTCOME_UNCERTAIN``.
    """
    return {ack: outcome_from_ack(ack) for ack in AckClass}
