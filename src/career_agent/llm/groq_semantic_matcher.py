"""A free-tier, Groq-backed :class:`SemanticKeywordMatcher` (ADR-0042).

This port was already documented as the safest possible place to route to a
cheaper model (ADR-0034): it gates nothing, every claim is deterministically
re-verified as a literal substring of the resume text before it prunes
anything, and a wrong answer costs at most one wasted retailor suggestion.
That reasoning holds regardless of which model answers the question, so
Groq's free tier is a direct, no-compromise substitution here.
"""

from __future__ import annotations

import json
import logging

from career_agent.domain.ats_scoring import SemanticKeywordClaim
from career_agent.llm.groq_client import GroqCallError, groq_chat_completion
from career_agent.llm.prompts import (
    SEMANTIC_KEYWORD_PROMPT,
    SEMANTIC_KEYWORD_PROMPT_VERSION,
)

logger = logging.getLogger(__name__)

_MODEL = "llama-3.3-70b-versatile"


class GroqSemanticKeywordMatcher:
    """Advisory-only semantic keyword matching via one Groq call."""

    prompt_version = SEMANTIC_KEYWORD_PROMPT_VERSION

    def __init__(self, *, api_key: str, model: str = _MODEL) -> None:
        """Configure with a bare API key (config-flows-inward, as everywhere)."""
        self._api_key = api_key
        self._model = model

    async def propose_matches(
        self, missing_keywords: list[str], resume_text: str
    ) -> list[SemanticKeywordClaim]:
        """Propose (keyword, quoted phrase) pairs; [] on any failure.

        Same fail-open-to-empty contract as ``AnthropicSemanticKeywordMatcher``:
        an empty answer is the conservative default here specifically because
        this layer can only ever prune the retailor gap report.
        """
        if not missing_keywords:
            return []
        prompt = SEMANTIC_KEYWORD_PROMPT.format(
            missing_keywords="\n".join(f"- {kw}" for kw in missing_keywords),
            resume_text=resume_text,
        )
        try:
            text = await groq_chat_completion(
                api_key=self._api_key,
                model=self._model,
                prompt=prompt,
                max_tokens=1000,
            )
            payload = json.loads(text)
            return [SemanticKeywordClaim.model_validate(item) for item in payload]
        except (GroqCallError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("semantic keyword matching unavailable: %s", exc)
            return []
