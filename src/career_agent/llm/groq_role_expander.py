"""A free-tier, Groq-backed :class:`RoleExpander` (Phase 72, ADR-0090).

Wired only where ``RoleExpander`` was already documented as advisory-only
(``core/interfaces.py``): its output can only ever widen a search's
``related`` tier, never gate, filter, or promote anything to an exact
match, so a cheaper model's occasional bad suggestion costs nothing more
than one extra (still harmless) related-role search term. Same offline-
testing discipline as ``GroqContentDrafter``: never imported on the test
path in production wiring; exercised via a fake port in
``domain.role_expansion`` tests instead.
"""

from __future__ import annotations

import json

from career_agent.llm.groq_client import groq_chat_completion
from career_agent.llm.prompts import ROLE_EXPANDER_PROMPT, ROLE_EXPANDER_PROMPT_VERSION

_MODEL = "llama-3.3-70b-versatile"


class GroqRoleExpander:
    """A :class:`~career_agent.core.interfaces.RoleExpander` backed by Groq."""

    prompt_version = ROLE_EXPANDER_PROMPT_VERSION

    def __init__(self, *, api_key: str, model: str = _MODEL) -> None:
        """Configure the expander with a bare API key (config-flows-inward)."""
        self._api_key = api_key
        self._model = model

    async def suggest_related_roles(self, role_query: str) -> list[str]:
        """Related job titles for ``role_query`` via a single Groq call.

        Raises on a network error; a malformed/non-JSON/non-list response
        is treated as "no suggestions" (returns ``[]``) rather than an
        error -- this port is advisory-only, so a parse hiccup should
        degrade the *quality* of the related-roles bucket, not fail the
        caller's search. Compare ``GroqContentDrafter.draft``, which
        raises on the same malformed-response case: that draft feeds a
        gate that must see a real failure to reject correctly, while this
        output only ever adds optional, harmless search terms.
        """
        prompt = ROLE_EXPANDER_PROMPT.format(role_query=role_query)
        text = await groq_chat_completion(
            api_key=self._api_key, model=self._model, prompt=prompt, max_tokens=300
        )
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, str)]
