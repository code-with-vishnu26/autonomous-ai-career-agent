"""Provider selection for the two non-cost-cascade-exempt LLM ports (ADR-0042).

``ClaimVerifier`` is deliberately absent from this module: it is
permanently pinned to Anthropic's most capable tier (ADR-0016) and nothing
here is allowed to change that. ``ContentDrafter`` and
``SemanticKeywordMatcher`` were already documented as safe to route to a
cheaper (or free) model, so this is where that choice actually happens --
once, at composition time, from whichever API key is configured. There is
no runtime fallback between providers: a provider is chosen once and used
for the whole run, so a mid-run Groq failure never silently reroutes to a
paid Anthropic call behind the user's back.
"""

from __future__ import annotations

from career_agent.core.config import Settings
from career_agent.core.interfaces import ContentDrafter, SemanticKeywordMatcher
from career_agent.llm.claim_verifier import AnthropicClaimVerifier
from career_agent.llm.content_drafter import AnthropicContentDrafter
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


def build_claim_verifier(settings: Settings) -> AnthropicClaimVerifier:
    """The truthfulness gate's verifier: Anthropic only, never routed to Groq.

    Not a "selection" at all -- present here only so callers have one place
    to build every LLM-backed port, without ever being tempted to add a
    free-tier branch to this specific function. ADR-0016's cost-cascade
    exemption and its promptfoo gate apply to this port and no other.
    """
    if not settings.anthropic_api_key:
        raise NoLLMProviderConfiguredError(
            "ANTHROPIC_API_KEY is not set -- required for the truthfulness "
            "gate's verifier, which is never routed to a free provider."
        )
    return AnthropicClaimVerifier(api_key=settings.anthropic_api_key)
