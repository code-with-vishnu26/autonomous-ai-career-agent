"""The real, Claude-backed :class:`ContentDrafter` (ADR-0022).

Never imported on the test path -- tests inject ``FakeContentDrafter``
(``tests/_fakes.py``) instead, the same offline-testing discipline every
other real-network component in this project follows.

Unlike ``AnthropicClaimVerifier``, ``_MODEL`` here is **not** permanently
pinned against future cost-cascade routing -- a false-approve on tailoring
is recoverable (the truthfulness gate catches it downstream); that asymmetry
is what earned ``ClaimVerifier`` its permanent exemption, and it does not
transfer here by default. A single capable model is used for this phase;
cascade tiering is named future work (ADR-0022), not decided now.
"""

from __future__ import annotations

import json

import anthropic

from career_agent.core.interfaces import DraftedTailoring
from career_agent.domain.models import MasterProfile, Opportunity
from career_agent.llm.prompts import RESUME_DRAFT_PROMPT, RESUME_DRAFT_PROMPT_VERSION

_MODEL = "claude-opus-4-8"


class AnthropicContentDrafter:
    """A :class:`~career_agent.core.interfaces.ContentDrafter` backed by Claude."""

    prompt_version = RESUME_DRAFT_PROMPT_VERSION

    def __init__(self, *, api_key: str, model: str = _MODEL) -> None:
        """Configure the drafter with a bare API key.

        ``api_key`` is a plain string, not a
        :class:`~career_agent.core.config.Settings` object -- same config-flows-
        inward isolation as every other provider in this project.
        """
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def draft(
        self, opportunity: Opportunity, profile: MasterProfile
    ) -> DraftedTailoring:
        """Draft work/skill/project selections via a single Claude call.

        Raises on any failure (API error, malformed/non-JSON response, or a
        response that doesn't validate against :class:`DraftedTailoring` --
        including one that tries to include a ``summary`` key, which the
        model is never asked for) rather than returning a fabricated draft.
        """
        prompt = RESUME_DRAFT_PROMPT.format(
            opportunity_description=opportunity.description_raw,
            profile_json=profile.model_dump_json(),
        )
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=2000,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text for block in response.content if hasattr(block, "text")
        )
        payload = json.loads(text)  # raises on malformed response, by design
        return DraftedTailoring(
            work=payload.get("work", []),
            skills=payload.get("skills", []),
            projects=payload.get("projects", []),
        )
