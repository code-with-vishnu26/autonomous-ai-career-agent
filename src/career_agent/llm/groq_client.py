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


def extract_json_object(text: str) -> str:
    r"""Return the substring from the first ``{`` to the last ``}`` in ``text``.

    A second live promptfoo run (ADR-0043, after fixing the token-budget
    truncation) showed ``openai/gpt-oss-120b`` still prepending visible
    chain-of-thought reasoning to its answer -- ``"Thinking: ...\n{json}"``
    -- even with ``include_reasoning=False`` set. This is a documented
    upstream Groq/gpt-oss quirk (reasoning leaking into the visible
    ``content`` field regardless of that flag), not something this
    project's request body controls. The JSON itself was always correct;
    it was never the *entire* response text, which is what a bare
    ``json.loads(text)`` assumed.

    Used only by ``GroqClaimVerifier`` -- ``llama-3.3-70b-versatile`` (the
    other two Groq-backed ports) is not a reasoning model and has shown no
    evidence of this behavior, so it is not applied speculatively there.

    Raises ``ValueError`` if no ``{``/``}`` pair exists at all, so a
    response that is pure reasoning with no JSON anywhere still fails
    closed exactly as a bare ``json.loads`` would have.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON object found in Groq response: {text!r}")
    return text[start : end + 1]


async def groq_chat_completion(
    *,
    api_key: str,
    model: str,
    prompt: str,
    max_tokens: int,
    temperature: float = 0,
    reasoning_effort: str | None = None,
    include_reasoning: bool | None = None,
) -> str:
    """POST a single-message chat completion to Groq; return the raw text.

    No ``response_format`` constraint is requested: both prompts that call
    this (resume drafting, semantic keyword matching) ask for JSON in plain
    prompt text and are parsed leniently by the caller, the same contract
    the existing Anthropic-backed ports use -- one of them expects a JSON
    *array* at the top level, which Groq's ``json_object`` response format
    would reject outright.

    ``reasoning_effort``/``include_reasoning`` exist only for reasoning
    models (``openai/gpt-oss-120b``, ADR-0043's ``GroqClaimVerifier``) --
    Groq's own docs state these models spend part of ``max_tokens`` on
    hidden chain-of-thought before ever emitting the requested JSON, so
    leaving both unset on a reasoning model risks the visible answer being
    truncated away entirely. ``llama-3.3-70b-versatile`` (the other two
    ports' model) is not a reasoning model and never passes these.
    """
    body: dict[str, object] = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if reasoning_effort is not None:
        body["reasoning_effort"] = reasoning_effort
    if include_reasoning is not None:
        body["include_reasoning"] = include_reasoning
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                _GROQ_CHAT_COMPLETIONS_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=body,
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
