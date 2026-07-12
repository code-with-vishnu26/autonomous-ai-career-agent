"""A free-tier, Groq-backed :class:`CareerCoachAdvisor` (Phase 57, ADR-0075).

Same offline-testing discipline as the other Groq ports: never imported on
the test path in production wiring; exercised via a mocked HTTP transport.
"""

from __future__ import annotations

from career_agent.llm.groq_client import groq_chat_completion
from career_agent.llm.prompts import COACH_ADVISOR_PROMPT_VERSION

_MODEL = "llama-3.3-70b-versatile"


class GroqCareerCoachAdvisor:
    """A :class:`~career_agent.core.interfaces.CareerCoachAdvisor` backed by Groq."""

    prompt_version = COACH_ADVISOR_PROMPT_VERSION

    def __init__(self, *, api_key: str, model: str = _MODEL) -> None:
        """Configure the advisor with a bare API key."""
        self._api_key = api_key
        self._model = model

    async def draft_text(self, prompt: str, *, max_tokens: int = 1500) -> str:
        """Return Groq's raw completion text. Raises on any call failure."""
        return await groq_chat_completion(
            api_key=self._api_key,
            model=self._model,
            prompt=prompt,
            max_tokens=max_tokens,
        )
