"""Provider selection for all three real LLM ports (ADR-0042, ADR-0043).

ADR-0042 gave ``ContentDrafter`` and ``SemanticKeywordMatcher`` a free-tier
Groq branch because their own ADRs (0022, 0034) already ruled a
false-approve on either recoverable. ADR-0016 originally kept
``ClaimVerifier`` out of this module entirely, on the reasoning that a
false-approve there is not recoverable. ADR-0043 revisited that on direct
user instruction to run the whole project at zero ongoing cost: the
asymmetry is real, but it is now compensated for structurally instead --
``GroqClaimVerifier`` exists as a distinct, separately promptfoo-gated
class (``provider_id="groq"``), so a live-validated pass for Anthropic can
never silently authorize it. See ``promptfoo_gate.py``.

There is no runtime fallback between providers for any of the three ports:
a provider is chosen once, at composition time, from whichever API key is
configured, and used for the whole run -- a mid-run Groq failure never
silently reroutes to a paid Anthropic call behind the user's back.
"""

from __future__ import annotations

from career_agent.core.config import Settings
from career_agent.core.interfaces import (
    ClaimVerifier,
    ContentDrafter,
    SemanticKeywordMatcher,
)
from career_agent.llm.claim_verifier import AnthropicClaimVerifier
from career_agent.llm.content_drafter import AnthropicContentDrafter
from career_agent.llm.groq_claim_verifier import GroqClaimVerifier
from career_agent.llm.groq_content_drafter import GroqContentDrafter
from career_agent.llm.groq_semantic_matcher import GroqSemanticKeywordMatcher
from career_agent.llm.semantic_matcher import AnthropicSemanticKeywordMatcher


class NoLLMProviderConfiguredError(Exception):
    """Neither a free (Groq) nor a paid (Anthropic) API key is configured."""


def select_content_drafter(settings: Settings) -> ContentDrafter:
    """Groq first (free), Anthropic second (paid) -- chosen once, not per-call.

    Groq is preferred when its key is present because this port's own
    exemption analysis (ADR-0022) already established that a false-approve
    here is recoverable: the unchanged, Anthropic-backed truthfulness gate
    catches it downstream regardless of which model drafted the content.
    """
    if settings.groq_api_key:
        return GroqContentDrafter(api_key=settings.groq_api_key)
    if settings.anthropic_api_key:
        return AnthropicContentDrafter(api_key=settings.anthropic_api_key)
    raise NoLLMProviderConfiguredError(
        "Set GROQ_API_KEY (free) or ANTHROPIC_API_KEY (paid) to draft tailored "
        "resume content."
    )


def select_semantic_matcher(settings: Settings) -> SemanticKeywordMatcher | None:
    """Groq first (free), Anthropic second (paid), ``None`` if neither is set.

    ``None`` is a legitimate answer here (unlike ``ContentDrafter``): the
    semantic layer is purely advisory (ADR-0034) -- the ATS gate runs
    correctly without it, just without the extra pruning pass.
    """
    if settings.groq_api_key:
        return GroqSemanticKeywordMatcher(api_key=settings.groq_api_key)
    if settings.anthropic_api_key:
        return AnthropicSemanticKeywordMatcher(api_key=settings.anthropic_api_key)
    return None


def select_claim_verifier(settings: Settings) -> ClaimVerifier:
    """Groq first (free), Anthropic second (paid) -- the truthfulness gate.

    Unlike the other two ports, swapping this one's provider is not a
    "recoverable false-approve" call -- it changes what judges the single
    highest-stakes decision in the system. ADR-0043's compensating control
    lives downstream of this function, in ``cli.py``: whichever class this
    returns, its ``prompt_version``/``provider_id`` must have a live
    promptfoo pass on disk (``verify_promptfoo_results``) before it is ever
    wired into a real submission path. This function only chooses which
    class; it never decides that choice is safe to use yet.
    """
    if settings.groq_api_key:
        return GroqClaimVerifier(api_key=settings.groq_api_key)
    if settings.anthropic_api_key:
        return AnthropicClaimVerifier(api_key=settings.anthropic_api_key)
    raise NoLLMProviderConfiguredError(
        "Set GROQ_API_KEY (free) or ANTHROPIC_API_KEY (paid) for the "
        "truthfulness gate's verifier."
    )
