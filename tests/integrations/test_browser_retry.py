"""Phase 62 (ADR-0080): retry_async's bounded-retry contract.

Pure asyncio -- no Chromium required, unlike this project's other
integrations/browser tests, since retry_async has zero Playwright
dependency of its own (any awaitable + any exception type works).
"""

from __future__ import annotations

import pytest

from career_agent.integrations.browser.retry import retry_async


class _FlakyError(Exception):
    """A test-only exception standing in for a transient failure."""


class _OtherError(Exception):
    """A test-only exception standing in for a non-retryable failure."""


async def test_succeeds_on_the_first_attempt_no_retry_needed() -> None:
    calls = 0

    async def action() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    result = await retry_async(action, attempts=3, retry_on=(_FlakyError,))
    assert result == "ok"
    assert calls == 1


async def test_succeeds_after_failing_fewer_times_than_attempts() -> None:
    calls = 0

    async def action() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise _FlakyError("transient")
        return "ok"

    result = await retry_async(
        action, attempts=3, base_delay_seconds=0.001, retry_on=(_FlakyError,)
    )
    assert result == "ok"
    assert calls == 3


async def test_reraises_the_last_exception_once_attempts_are_exhausted() -> None:
    calls = 0

    async def action() -> str:
        nonlocal calls
        calls += 1
        raise _FlakyError(f"attempt {calls}")

    with pytest.raises(_FlakyError, match="attempt 3"):
        await retry_async(
            action, attempts=3, base_delay_seconds=0.001, retry_on=(_FlakyError,)
        )
    assert calls == 3


async def test_never_retries_an_exception_type_not_in_retry_on() -> None:
    calls = 0

    async def action() -> str:
        nonlocal calls
        calls += 1
        raise _OtherError("not transient")

    with pytest.raises(_OtherError):
        await retry_async(
            action, attempts=3, base_delay_seconds=0.001, retry_on=(_FlakyError,)
        )
    assert calls == 1


async def test_attempts_must_be_at_least_one() -> None:
    async def action() -> str:
        return "unreachable"

    with pytest.raises(ValueError, match="attempts must be >= 1"):
        await retry_async(action, attempts=0, retry_on=(_FlakyError,))
