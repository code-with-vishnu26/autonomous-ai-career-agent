"""The real, Claude-backed :class:`ClaimVerifier` (ADR-0016).

This was the only concrete production implementation of the port defined in
``core/interfaces.py`` until ADR-0043 added ``GroqClaimVerifier`` as a
free-tier alternative on direct user instruction to run at zero ongoing
cost. Never imported on the test path -- tests inject ``FakeClaimVerifier``
(``tests/_fakes.py``) instead, the same offline-testing discipline every
other real-network component in this project follows.

Two hard constraints, stated in code as well as in ADR-0016 so they cannot
silently regress:

1. **Pinned to the most capable Anthropic tier, still used as the fallback
   when ``GROQ_API_KEY`` is unset.** A false-approve here is catastrophic; a
   false-block merely means an honest claim is held back for the user to
   notice and fix. ADR-0016's "never cost-cascade this" reasoning is exactly
   why ADR-0043 did not simply reroute this class's ``_MODEL`` to a cheaper
   tier -- it added a distinct, separately promptfoo-gated class instead
   (see ``groq_claim_verifier.py``), so the asymmetry stays visible per
   provider rather than blurred into one model constant.
2. **Temperature 0.** Minimizes (but does not eliminate) run-to-run variance.
   Re-verifying the same claim against the same evidence may still legitimately
   diverge across calls -- an expected, documented limitation of resting
   correctness on model judgment, not a bug to chase to zero.
"""

from __future__ import annotations

import json

import anthropic

from career_agent.core.interfaces import ClaimVerdict
from career_agent.llm.prompts import (
    TRUTHFULNESS_GATE_PROMPT,
    TRUTHFULNESS_GATE_PROMPT_VERSION,
)

# Pinned to the most capable tier available. NEVER route this to a cheaper
# model as a cost optimization -- see ADR-0016's cost-cascade exemption.
_MODEL = "claude-opus-4-8"


class AnthropicClaimVerifier:
    """A :class:`~career_agent.core.interfaces.ClaimVerifier` backed by Claude."""

    prompt_version = TRUTHFULNESS_GATE_PROMPT_VERSION
    #: Keys the promptfoo results artifact (ADR-0043) -- distinct from
    #: ``GroqClaimVerifier``'s so a pass for one can never cover the other.
    provider_id = "anthropic"

    def __init__(self, *, api_key: str, model: str = _MODEL) -> None:
        """Configure the verifier with a bare API key.

        ``api_key`` is a plain string, not a
        :class:`~career_agent.core.config.Settings` object -- same config-flows-
        inward isolation as every other provider in this project.
        """
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def verify_claim(self, statement_text: str, evidence: str) -> ClaimVerdict:
        """Judge ``statement_text`` against ``evidence`` via a single Claude call.

        Raises on any failure (API error, malformed/non-JSON response) rather
        than returning a fabricated verdict -- the caller (the gate) is
        responsible for treating that as an explicit block.
        """
        prompt = TRUTHFULNESS_GATE_PROMPT.format(
            evidence=evidence, statement=statement_text
        )
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=300,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text for block in response.content if hasattr(block, "text")
        )
        payload = json.loads(text)  # raises on malformed response, by design
        return ClaimVerdict(
            verified=bool(payload["verified"]),
            confidence=float(payload["confidence"]),
            category=payload.get("category"),
            detail=str(payload.get("detail", "")),
        )
