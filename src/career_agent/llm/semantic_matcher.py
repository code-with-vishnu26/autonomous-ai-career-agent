"""The real, Claude-backed :class:`SemanticKeywordMatcher` (Phase 10, ADR-0034).

Never imported on the test path -- tests inject a fake, the same offline
discipline as every other real-network component here.

Deliberately NOT cost-cascade-exempt, unlike ``AnthropicClaimVerifier``
(ADR-0016), and the reasoning is recorded because it will look
inconsistent to a future reader otherwise: the ``ClaimVerifier`` exemption
exists to protect *judgments that gate something*, where a cheaper model's
false approval is unrecoverable downstream. This port gates nothing. Its
every claim is deterministically re-verified
(:func:`~career_agent.domain.ats_scoring.verified_semantic_keywords`
requires the quoted phrase to exist verbatim in the resume text), and
nothing it produces can reach the ATS gate's pass/fail decision (matrix
case A1) -- a wrong answer costs at most one wasted retailor suggestion.
The exemption's purpose does not apply, so the exemption is not granted.

A malformed or non-JSON response returns no claims rather than raising:
this layer is advisory, and "the advisor said nothing useful" is a
complete, safe outcome -- the retailor loop simply proceeds with the
unpruned deterministic missing list.
"""

from __future__ import annotations

import json
import logging

import anthropic

from career_agent.domain.ats_scoring import SemanticKeywordClaim
from career_agent.llm.prompts import (
    SEMANTIC_KEYWORD_PROMPT,
    SEMANTIC_KEYWORD_PROMPT_VERSION,
)

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"


class AnthropicSemanticKeywordMatcher:
    """Advisory-only semantic keyword matching via one Claude call."""

    prompt_version = SEMANTIC_KEYWORD_PROMPT_VERSION

    def __init__(self, *, api_key: str, model: str = _MODEL) -> None:
        """Configure with a bare API key (config-flows-inward, as everywhere)."""
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def propose_matches(
        self, missing_keywords: list[str], resume_text: str
    ) -> list[SemanticKeywordClaim]:
        """Propose (keyword, quoted phrase) pairs; [] on any failure.

        Failing open-to-empty is safe *here specifically* because this
        layer can only ever prune the retailor gap report -- an empty
        answer means "no pruning," which is the conservative default. This
        is the opposite of the truthfulness gate's fail-closed rule, and
        correctly so: that gate blocks submission, this advisor merely
        trims a suggestion list.
        """
        if not missing_keywords:
            return []
        prompt = SEMANTIC_KEYWORD_PROMPT.format(
            missing_keywords="\n".join(f"- {kw}" for kw in missing_keywords),
            resume_text=resume_text,
        )
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=1000,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(
                block.text for block in response.content if hasattr(block, "text")
            )
            payload = json.loads(text)
            return [SemanticKeywordClaim.model_validate(item) for item in payload]
        except Exception as exc:  # noqa: BLE001 -- advisory layer, fail to empty
            logger.warning("semantic keyword matching unavailable: %s", exc)
            return []
