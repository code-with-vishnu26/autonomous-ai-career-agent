"""A concrete httpx-backed :class:`HttpClient`.

The only place in the project that imports httpx for opportunity discovery.
Sources depend on the :class:`~career_agent.core.interfaces.HttpClient` port,
not on this class, so this implementation is swappable and is never imported on
the test path (tests inject a fixture-replaying fake instead).

Note: in the Claude Code Remote sandbox, outbound HTTPS to ATS hosts is blocked
by the egress policy, so this client's live path is validated when the project
is run on the user's own machine, not in-sandbox.
"""

from __future__ import annotations

import httpx


class HttpxClient:
    """An async HTTP client that GETs/POSTs JSON, with a sane timeout and UA."""

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        user_agent: str = "autonomous-ai-career-agent/0.1 (+self-hosted)",
    ) -> None:
        """Create a client with a default timeout and identifying user agent."""
        self._timeout = timeout
        self._headers = {"User-Agent": user_agent, "Accept": "application/json"}

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> object:
        """GET ``url`` (optionally with query ``params``) and return parsed JSON.

        Raises :class:`httpx.HTTPStatusError` on a non-2xx response so the
        caller can decide how to handle a failed source without silently
        treating an error page as data.
        """
        async with httpx.AsyncClient(
            timeout=self._timeout, headers={**self._headers, **(headers or {})}
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    async def post_json(
        self,
        url: str,
        *,
        json: dict[str, object],
        headers: dict[str, str] | None = None,
    ) -> object:
        """POST ``json`` to ``url`` and return the parsed JSON response body."""
        async with httpx.AsyncClient(
            timeout=self._timeout, headers={**self._headers, **(headers or {})}
        ) as client:
            response = await client.post(url, json=json)
            response.raise_for_status()
            return response.json()
