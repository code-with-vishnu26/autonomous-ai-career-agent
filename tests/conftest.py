"""Suite-wide safety net: no test may reach a real LLM provider.

This is a safety net, not a substitute for correct control flow -- the
actual bug this project hit (a test asserting "promptfoo gate blocks"
silently depended on ambient repository state, and on a machine with a
real, valid results artifact the gate passed and execution reached a
real Groq HTTP call using a fake key) was fixed at its real cause
(``run_auto_cli_command`` gained the same injectable ``promptfoo_results_dir``
``run_apply_command`` already had, and the affected test now uses it).
This fixture exists so that *any* future test with the same class of bug
fails loudly and immediately with a clear message, instead of either
silently attempting a real network call or producing a confusing
provider-side error (a 401, a timeout) that looks unrelated to its actual
cause.

Both ``GroqContentDrafter``/``GroqClaimVerifier`` (via ``groq_client.py``'s
``httpx.AsyncClient``) and ``AnthropicClaimVerifier``/Anthropic's own SDK
(``anthropic.AsyncAnthropic``, which is itself built on ``httpx.AsyncClient``
internally) are covered by patching at the one shared point both paths
funnel through.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest

_BLOCKED_HOSTS = {"api.groq.com", "api.anthropic.com"}


@pytest.fixture(autouse=True)
def _block_real_llm_network_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise instead of dispatching any real request to a blocked host.

    Test doubles (``FakeHttpClient``, ``httpx.MockTransport``) never
    target these hostnames in the first place, so this never fires for a
    correctly-isolated test -- it only fires for exactly the bug class
    this file's docstring describes.
    """
    original_send: Callable[..., Awaitable[httpx.Response]] = httpx.AsyncClient.send

    async def guarded_send(
        self: httpx.AsyncClient, request: httpx.Request, *args: Any, **kwargs: Any
    ) -> httpx.Response:
        # A client explicitly wired to httpx.MockTransport (this project's
        # own established pattern -- see tests/llm/test_groq_providers.py)
        # never reaches a real socket regardless of which URL its request
        # targets, so it is not the failure mode this guard exists for.
        if isinstance(self._transport, httpx.MockTransport):
            return await original_send(self, request, *args, **kwargs)
        if request.url.host in _BLOCKED_HOSTS:
            raise RuntimeError(
                f"Test attempted a real network call to {request.url.host!r} "
                f"({request.method} {request.url}). Tests must never reach a "
                f"real LLM provider -- if this fired, a test is missing proper "
                f"isolation (e.g. an unvalidated-promptfoo test not pointing "
                f"at an isolated results directory), not a case for mocking "
                f"this specific call away."
            )
        return await original_send(self, request, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "send", guarded_send)
