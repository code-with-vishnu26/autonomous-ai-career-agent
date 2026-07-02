"""Shared test doubles. Not collected as tests (no ``test_`` prefix).

``FakeHttpClient`` satisfies the :class:`~career_agent.core.interfaces.HttpClient`
port by replaying recorded JSON, so the suite makes no network call and stays
deterministic and offline (the live path is validated only when the project
runs on the user's own machine).
"""

from __future__ import annotations

import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(*parts: str) -> object:
    """Load and parse a JSON fixture under ``tests/fixtures``."""
    return json.loads(FIXTURES.joinpath(*parts).read_text())


class FakeHttpClient:
    """Replays recorded JSON by substring-matching the requested URL.

    Records every call on ``calls`` so tests can assert how a source queried
    the API (e.g. that it passed ``content=true``).
    """

    def __init__(
        self,
        responses: dict[str, object] | None = None,
        *,
        default: object | None = None,
    ) -> None:
        self._responses = responses or {}
        self._default = default
        self.calls: list[tuple[str, dict[str, str] | None]] = []
        self.post_calls: list[tuple[str, dict[str, object]]] = []

    async def get_json(
        self, url: str, *, params: dict[str, str] | None = None
    ) -> object:
        self.calls.append((url, params))
        return self._resolve(url)

    async def post_json(
        self,
        url: str,
        *,
        json: dict[str, object],
        headers: dict[str, str] | None = None,
    ) -> object:
        self.post_calls.append((url, json))
        return self._resolve(url)

    def _resolve(self, url: str) -> object:
        for key, payload in self._responses.items():
            if key in url:
                return payload
        if self._default is not None:
            return self._default
        raise KeyError(f"no fake response registered for {url!r}")
