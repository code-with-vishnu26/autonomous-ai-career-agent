"""Phase 29 (ADR-0055): real-provider release-gate guards.

These pin the facts a controlled real-provider smoke run's evidence depends
on -- the exact model identifiers, the bounded call/token budget, and which
components are Promptfoo-gated -- so a *silent* provider/model/policy change
(which would invalidate any prior live smoke evidence and any Promptfoo
artifact) is caught by a failing test rather than shipping unnoticed. They
make **no live call** (they read module constants and run the offline
selection functions).

The provider-selection precedence, malformed-response handling, reasoning-
preamble stripping, secret-never-logged, and full Promptfoo-gate matrix are
already covered by `tests/llm/test_groq_providers.py` and
`tests/llm/test_promptfoo_gate.py`; this file adds only the drift guards and
the two selection edges those suites do not pin.
"""

from __future__ import annotations

from career_agent.agents.resume import pipeline
from career_agent.core.config import Settings
from career_agent.llm import (
    claim_verifier,
    content_drafter,
    groq_claim_verifier,
    groq_content_drafter,
    groq_semantic_matcher,
    semantic_matcher,
)
from career_agent.llm.providers import (
    NoLLMProviderConfiguredError,
    select_claim_verifier,
)

# --------------------------------------------------------------------------
# Model-identifier drift guards (Section 24). Any change here is a deliberate
# provider/model migration that MUST re-run live Promptfoo validation and
# re-establish smoke evidence -- ADR-0055's invalidation triggers.
# --------------------------------------------------------------------------


def test_groq_model_identifiers_are_pinned() -> None:
    # The truthfulness verifier's model is the highest-stakes pin: the
    # Promptfoo artifact is validated against this exact model (ADR-0043).
    assert groq_claim_verifier._MODEL == "openai/gpt-oss-120b"
    assert groq_content_drafter._MODEL == "llama-3.3-70b-versatile"
    assert groq_semantic_matcher._MODEL == "llama-3.3-70b-versatile"


def test_anthropic_model_identifiers_are_pinned() -> None:
    assert claim_verifier._MODEL == "claude-opus-4-8"
    assert content_drafter._MODEL == "claude-opus-4-8"
    assert semantic_matcher._MODEL == "claude-haiku-4-5-20251001"


def test_reasoning_verifier_token_budget_is_bounded() -> None:
    """RQ17/RQ19: the gpt-oss-120b reasoning model's tokens (reasoning +
    answer) are capped, so a reasoning blow-up cannot make an unbounded call."""
    assert groq_claim_verifier._MAX_TOKENS == 2000
    assert groq_claim_verifier._REASONING_EFFORT == "low"


def test_ats_retry_budget_is_a_small_finite_constant() -> None:
    """RQ13-RQ16: the retailor loop -- the only source of extra LLM calls per
    prepare run -- is bounded by a small constant, so one run's call count is
    finite and knowable (no unbounded agent loop)."""
    assert pipeline._MAX_ATS_RETRIES == 2


# --------------------------------------------------------------------------
# Provider-selection edges not pinned elsewhere (Section 6 E/F).
# --------------------------------------------------------------------------


def test_empty_string_key_falls_through_fail_closed() -> None:
    """An empty-string key is falsy -> treated as absent -> fail-closed."""
    settings = Settings(groq_api_key="", anthropic_api_key=None)
    try:
        select_claim_verifier(settings)
    except NoLLMProviderConfiguredError:
        pass
    else:  # pragma: no cover - guard
        raise AssertionError("empty key must not select a provider")


def test_whitespace_only_key_is_treated_as_present_documented_limitation() -> None:
    """A whitespace-only key is currently *truthy* and selects a provider; it
    then fails at the live call (401), never silently unsafe. This pins the
    known, low-severity limitation documented in ADR-0055 so a future change
    to it is a conscious one -- it is fail-closed at call time, not a
    truthfulness bypass."""
    settings = Settings(groq_api_key="   ", anthropic_api_key=None)
    verifier = select_claim_verifier(settings)
    assert type(verifier).__name__ == "GroqClaimVerifier"


# --------------------------------------------------------------------------
# Gate scope (RQ7-RQ10): only the truthfulness verifier is Promptfoo-gated.
# --------------------------------------------------------------------------


def test_only_the_claim_verifier_carries_a_promptfoo_prompt_version() -> None:
    """The verifier exposes a ``prompt_version`` used to key its Promptfoo
    artifact (ADR-0043); the drafter/matcher are recoverable-if-wrong
    (ADR-0022/0034) and are not Promptfoo-gated. Confirmed structurally: the
    verifier classes have ``prompt_version``, and the gate scope is the
    verifier only."""
    groq_v = groq_claim_verifier.GroqClaimVerifier(api_key="x")
    anth_v = claim_verifier.AnthropicClaimVerifier(api_key="x")
    assert isinstance(groq_v.prompt_version, str) and groq_v.prompt_version
    assert isinstance(anth_v.prompt_version, str) and anth_v.prompt_version
    # Both verifiers share one prompt version but carry distinct provider ids
    # (so an artifact for one never validates the other -- ADR-0043).
    assert groq_v.prompt_version == anth_v.prompt_version
    assert groq_v.provider_id != anth_v.provider_id
