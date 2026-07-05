"""Shared HTTP plumbing for Groq-backed ports (ADR-0042).

Groq exposes an OpenAI-compatible ``/chat/completions`` endpoint, so this is
a thin ``httpx`` call rather than a new SDK dependency -- the project
already depends on ``httpx`` for every other real-network integration.
Deliberately not built on the ``anthropic`` package's call shape: Groq is a
genuinely different provider, not a drop-in model-name swap.
"""

from __future__ import annotations

import httpx

_GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqCallError(Exception):
    """A Groq call failed (network, non-2xx, or an unexpected response shape).

    Callers decide what "failed" means for their port -- ``ContentDrafter``
    raises outward (a fabricated draft is worse than no draft), the
    advisory ``SemanticKeywordMatcher`` catches this and fails to ``[]``.
    """


async def groq_chat_completion(
    *, api_key: str, model: str, prompt: str, max_tokens: int, temperature: float = 0
) -> str:
    """POST a single-message chat completion to Groq; return the raw text.

    No ``response_format`` constraint is requested: both prompts that call
    this (resume drafting, semantic keyword matching) ask for JSON in plain
    prompt text and are parsed leniently by the caller, the same contract
    the existing Anthropic-backed ports use -- one of them expects a JSON
    *array* at the top level, which Groq's ``json_object`` response format
    would reject outright.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                _GROQ_CHAT_COMPLETIONS_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            payload = response.json()
        return str(payload["choices"][0]["message"]["content"])
    except httpx.HTTPError as exc:
        raise GroqCallError(f"Groq call failed: {type(exc).__name__}: {exc}") from exc
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise GroqCallError(
            f"Groq returned an unexpected response shape: {type(exc).__name__}: {exc}"
        ) from exc
