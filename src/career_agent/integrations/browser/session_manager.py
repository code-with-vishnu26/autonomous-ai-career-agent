"""Session persistence + login detection (Phase 47, ADR-0065).

Wraps :class:`~career_agent.integrations.browser_session.EncryptedSessionStore`
(ADR-0020) for encrypted-at-rest save/load, and adds the one primitive that
store never had: waiting for a human to complete a login this process will
never attempt itself.

**This module never fills in a username, password, or any credential
field, anywhere, under any code path.** It only ever *reads* the page (the
current URL, whether a CSS selector is present/visible) -- there is no
method here that accepts a credential or calls Playwright's
``.fill()``/``.type()``/``.press_sequentially()``. That is a structural
guarantee, checkable by reading this file (and pinned by
``tests/integrations/test_session_manager.py``'s source-scan guard), not
merely a docstring claim.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from career_agent.integrations.browser_session import EncryptedSessionStore

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page


class LoginTimeoutError(Exception):
    """The human did not complete login within the allotted wait.

    Never raised for "the site has no such selector" vs. "the human hasn't
    logged in yet" as distinct cases -- both look identical from here (the
    indicator is simply absent), and this module has no way to tell them
    apart without knowing the specific site, which is deliberately out of
    scope this phase (that is Phase 48's adapter framework).
    """


class SessionManager:
    """Save/load a browser session, and wait -- never automate -- for login."""

    def __init__(self, store: EncryptedSessionStore) -> None:
        """Wrap an already-configured :class:`EncryptedSessionStore`."""
        self._store = store

    def load(self, session_id: str) -> dict[str, object] | None:
        """The previously saved ``storage_state``, or ``None``.

        The caller decides what to do next (e.g. prompt for login) when
        nothing was saved yet.
        """
        return self._store.load(session_id)

    async def save(self, session_id: str, context: BrowserContext) -> None:
        """Persist the context's current ``storage_state``, encrypted at rest."""
        state = await context.storage_state()
        self._store.save(session_id, state)

    async def is_logged_in(self, page: Page, indicator_selector: str) -> bool:
        """Whether ``indicator_selector`` is visible on the current page.

        ``indicator_selector`` names a CSS selector present only when
        logged in (e.g. an account-menu button) -- the caller supplies it;
        this method has no built-in knowledge of any specific site. Never
        inspects, reads, or fills any credential field.
        """
        try:
            element = await page.query_selector(indicator_selector)
        except Exception:  # noqa: BLE001 -- a closed/navigating page: not logged in
            return False
        if element is None:
            return False
        return await element.is_visible()

    async def wait_for_login(
        self,
        page: Page,
        indicator_selector: str,
        *,
        timeout_seconds: float = 300.0,
        poll_interval_seconds: float = 2.0,
    ) -> None:
        """Poll until ``indicator_selector`` appears, or raise a timeout error.

        Raises :class:`LoginTimeoutError` on timeout. The human logs in
        directly on the visible page (see
        :class:`~career_agent.integrations.browser.browser_manager.
        BrowserManager`'s ``headless=False`` default); this method only
        ever observes the page, never types or clicks anything on it.
        """
        elapsed = 0.0
        while elapsed < timeout_seconds:
            if await self.is_logged_in(page, indicator_selector):
                return
            await asyncio.sleep(poll_interval_seconds)
            elapsed += poll_interval_seconds
        raise LoginTimeoutError(
            f"login not detected (selector {indicator_selector!r}) within "
            f"{timeout_seconds}s"
        )
