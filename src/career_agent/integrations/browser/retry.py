"""Bounded retry for transient browser-action failures (Phase 62, ADR-0080).

No new dependency (no ``tenacity``) for what a small function already
does -- the same "one small helper beats a library" precedent
``core/logging_config.py``'s ``JsonFormatter`` already established.

Deliberately narrow: retries a single Playwright *action* (fill a field,
navigate to a URL), never the submit click itself. Retrying the click
would risk a second real-world submission if the first attempt actually
succeeded but the response was slow to arrive -- the "never submit
twice" guarantee (``domain/execution.py``, ADR-0048/ADR-0050) depends on
the click happening at most once per confirmed preview, which this
module has no way to verify was safe to relax. Callers choose what to
wrap; this function has no opinion about which actions are safe to
retry.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def retry_async(
    action: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay_seconds: float = 0.5,
    retry_on: tuple[type[BaseException], ...],
) -> T:
    """Call ``action()`` up to ``attempts`` times, retrying only ``retry_on``.

    Exponential backoff (``base_delay_seconds * 2**attempt_index``) between
    attempts. Re-raises the last exception once attempts are exhausted --
    never swallows a persistent failure. Any exception not in ``retry_on``
    propagates immediately on the first occurrence, unretried.
    """
    if attempts < 1:
        raise ValueError(f"attempts must be >= 1, got {attempts}")
    for attempt_index in range(attempts):
        try:
            return await action()
        except retry_on as exc:
            if attempt_index == attempts - 1:
                raise
            last_exc = exc
            await asyncio.sleep(base_delay_seconds * (2**attempt_index))
    raise AssertionError(f"unreachable: retry_on={last_exc!r}")
