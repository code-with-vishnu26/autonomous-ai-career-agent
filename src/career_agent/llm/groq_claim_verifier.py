r"""A free-tier, Groq-backed :class:`ClaimVerifier` (ADR-0043).

ADR-0016 pinned the truthfulness gate's verifier to the most capable paid
Anthropic tier and called that exemption permanent: a false-approve here
lets a fabricated claim reach a real submission, unrecoverable. ADR-0042
built on that by refusing to give this port any free-tier branch at all.

ADR-0043 explicitly overrides both, on direct user instruction to run the
whole project at zero ongoing cost, no exceptions. The asymmetry ADR-0016
described has not gone away -- it is compensated for structurally instead
of by model choice alone: ``promptfoo_gate.py`` now keys its results
artifact to *provider*, not just prompt version, so a pass recorded for
Anthropic can never silently authorize this class, and this class cannot
be wired into a real ``apply`` run until the promptfoo suite has actually
passed on live calls against ``openai/gpt-oss-120b`` specifically -- see
``promptfoo/promptfooconfig.groq.yaml``.

Model choice: ``openai/gpt-oss-120b`` (OpenAI's open-weight reasoning
model, hosted free on Groq) rather than ``llama-3.3-70b-versatile`` (used
for the lower-stakes drafting/matching ports) -- this is the single
highest-stakes judgment in the system, so it gets Groq's strongest
available free-tier reasoning model, not the same default as everything
else.

**Two live promptfoo runs, two distinct bugs found and fixed, neither a
model-quality failure**:

1. At ``max_tokens=300`` with no reasoning controls, hidden chain-of-thought
   consumed the whole token budget on every one of the 12-case matrix's
   live-run cases, truncating the response before the JSON ever appeared.
   Fixed by ``reasoning_effort="low"``, ``include_reasoning=False``, and a
   much larger ``max_tokens``.
2. With that fixed, a second live run still scored 0/10: ``gpt-oss-120b``
   prepends visible reasoning to its answer -- ``"Thinking: ...\\n{json}"``
   -- *regardless* of ``include_reasoning=False`` (a documented upstream
   Groq/gpt-oss quirk, not something this project's request body controls).
   The JSON itself was correct on every case; it was never the *entire*
   response text, which is what a bare ``json.loads(text)`` assumed. Fixed
   by :func:`~career_agent.llm.groq_client.extract_json_object`, which pulls
   the JSON substring out before parsing.

``promptfoo/promptfooconfig.groq.yaml`` must mirror both fixes exactly --
its ``defaultTest.transform`` re-implements the same first-``{``-to-last-
``}`` extraction, so the eval validates the same parsing path this class
actually uses. A config that tests a different call shape than this class
uses would validate nothing real.
"""

from __future__ import annotations

import json

from career_agent.core.interfaces import ClaimVerdict
from career_agent.llm.groq_client import extract_json_object, groq_chat_completion
from career_agent.llm.prompts import (
    TRUTHFULNESS_GATE_PROMPT,
    TRUTHFULNESS_GATE_PROMPT_VERSION,
)

_MODEL = "openai/gpt-oss-120b"
#: Reasoning tokens count against max_tokens for this model (Groq docs) --
#: sized generously above the ~170 reasoning tokens/case observed in a live
#: 12-case run, with headroom, not tuned to the bare minimum.
_MAX_TOKENS = 2000
_REASONING_EFFORT = "low"


class GroqClaimVerifier:
    """A :class:`~career_agent.core.interfaces.ClaimVerifier` backed by Groq."""

    prompt_version = TRUTHFULNESS_GATE_PROMPT_VERSION
    #: Keys the promptfoo results artifact (ADR-0043) -- distinct from
    #: ``AnthropicClaimVerifier``'s so a pass for one can never cover the
    #: other.
    provider_id = "groq"

    def __init__(self, *, api_key: str, model: str = _MODEL) -> None:
        """Configure the verifier with a bare API key (config-flows-inward)."""
        self._api_key = api_key
        self._model = model

    async def verify_claim(self, statement_text: str, evidence: str) -> ClaimVerdict:
        """Judge ``statement_text`` against ``evidence`` via a single Groq call.

        Raises on any failure (network error, malformed/non-JSON response)
        rather than returning a fabricated verdict -- identical fail-closed
        contract to ``AnthropicClaimVerifier``; the caller (the gate) treats
        that as an explicit block.
        """
        prompt = TRUTHFULNESS_GATE_PROMPT.format(
            evidence=evidence, statement=statement_text
        )
        text = await groq_chat_completion(
            api_key=self._api_key,
            model=self._model,
            prompt=prompt,
            max_tokens=_MAX_TOKENS,
            reasoning_effort=_REASONING_EFFORT,
            include_reasoning=False,
        )
        # raises ValueError (extraction) or JSONDecodeError (parsing) on any
        # malformed response, by design -- both are fail-closed, never a
        # fabricated verdict.
        payload = json.loads(extract_json_object(text))
        return ClaimVerdict(
            verified=bool(payload["verified"]),
            confidence=float(payload["confidence"]),
            category=payload.get("category"),
            detail=str(payload.get("detail", "")),
        )
