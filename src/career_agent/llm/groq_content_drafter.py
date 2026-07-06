"""A free-tier, Groq-backed :class:`ContentDrafter` (ADR-0042).

Wired only where ``ContentDrafter`` was already documented as *not*
cost-cascade-exempt (ADR-0022): a false-approve here is recoverable because
every draft this produces still passes through the same, unchanged,
Anthropic-backed truthfulness gate (``AnthropicClaimVerifier``) before
anything is approved. Swapping the drafting model changes tailoring
*quality*, never the safety of what gets approved.

Same offline-testing discipline as ``AnthropicContentDrafter``: never
imported on the test path in production wiring; its logic is exercised via
a mocked HTTP transport instead of a live call.
"""

from __future__ import annotations

import json

from career_agent.core.interfaces import DraftedTailoring
from career_agent.domain.ats_scoring import AtsGapReport
from career_agent.domain.models import MasterProfile, Opportunity
from career_agent.llm.groq_client import groq_chat_completion
from career_agent.llm.prompts import (
    RESUME_DRAFT_GAP_SECTION,
    RESUME_DRAFT_PROMPT,
    RESUME_DRAFT_PROMPT_VERSION,
)

_MODEL = "llama-3.3-70b-versatile"


class GroqContentDrafter:
    """A :class:`~career_agent.core.interfaces.ContentDrafter` backed by Groq."""

    prompt_version = RESUME_DRAFT_PROMPT_VERSION

    def __init__(self, *, api_key: str, model: str = _MODEL) -> None:
        """Configure the drafter with a bare API key (config-flows-inward)."""
        self._api_key = api_key
        self._model = model

    async def draft(
        self,
        opportunity: Opportunity,
        profile: MasterProfile,
        *,
        gap_report: AtsGapReport | None = None,
    ) -> DraftedTailoring:
        """Draft work/skill/project selections via a single Groq call.

        Raises on any failure (network error, malformed/non-JSON response,
        or a response that doesn't validate) rather than returning a
        fabricated draft -- identical contract to ``AnthropicContentDrafter``.
        """
        gap_section = ""
        if gap_report is not None and gap_report.surfaceable:
            surfaceable_lines = "\n".join(
                f"- {item.keyword}: supported by profile text "
                f"{item.profile_evidence!r}"
                for item in gap_report.surfaceable
            )
            gap_section = RESUME_DRAFT_GAP_SECTION.format(
                surfaceable_lines=surfaceable_lines
            )
        prompt = RESUME_DRAFT_PROMPT.format(
            opportunity_description=opportunity.description_raw,
            profile_json=profile.model_dump_json(),
            gap_section=gap_section,
        )
        text = await groq_chat_completion(
            api_key=self._api_key, model=self._model, prompt=prompt, max_tokens=2000
        )
        payload = json.loads(text)  # raises on malformed response, by design
        return DraftedTailoring(
            work=payload.get("work", []),
            skills=payload.get("skills", []),
            projects=payload.get("projects", []),
        )
