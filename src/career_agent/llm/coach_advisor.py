"""The real, Claude-backed :class:`CareerCoachAdvisor` (Phase 57, ADR-0075).

Never imported on the test path -- tests inject a fake advisor instead, the
same offline-testing discipline every other real-network component in this
project follows.
"""

from __future__ import annotations

import anthropic

from career_agent.llm.prompts import COACH_ADVISOR_PROMPT_VERSION

_MODEL = "claude-opus-4-8"


class AnthropicCareerCoachAdvisor:
    """A :class:`~career_agent.core.interfaces.CareerCoachAdvisor` backed by Claude."""

    prompt_version = COACH_ADVISOR_PROMPT_VERSION

    def __init__(self, *, api_key: str, model: str = _MODEL) -> None:
        """Configure the advisor with a bare API key."""
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def draft_text(self, prompt: str, *, max_tokens: int = 1500) -> str:
        """Return Claude's raw completion text. Raises on any call failure."""
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            block.text for block in response.content if hasattr(block, "text")
        )
