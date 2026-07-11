"""Multi-tab support over one ``BrowserContext`` (Phase 47, ADR-0065).

A named registry of Playwright ``Page`` objects -- open a tab under a
caller-chosen name, fetch it back by that name later, close it, list
what's open. Structurally cannot navigate to or fill any job-application
form; it only creates/tracks/closes/navigates ``Page`` objects to
caller-supplied URLs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page


class UnknownTabError(Exception):
    """No tab is registered under this name."""


class DuplicateTabError(Exception):
    """A tab is already registered under this name.

    Raised rather than silently replacing the existing tab -- a caller
    that meant to reuse an already-open tab should call :meth:`TabManager.
    get_tab`, not accidentally leak the original ``Page`` by overwriting
    its registry entry.
    """


class TabManager:
    """Tracks Playwright ``Page``s by caller-chosen name, within one context."""

    def __init__(self, context: BrowserContext) -> None:
        """Track tabs opened within the given ``BrowserContext``."""
        self._context = context
        self._tabs: dict[str, Page] = {}

    async def open_tab(self, name: str, *, url: str | None = None) -> Page:
        """Open a new tab under ``name``, optionally navigating it to ``url``.

        Raises :class:`DuplicateTabError` if ``name`` is already open --
        use :meth:`get_tab` to reuse an existing one instead.
        """
        if name in self._tabs:
            raise DuplicateTabError(f"a tab named {name!r} is already open")
        page = await self._context.new_page()
        if url is not None:
            await page.goto(url)
        self._tabs[name] = page
        return page

    def get_tab(self, name: str) -> Page:
        """The ``Page`` registered under ``name``.

        Raises :class:`UnknownTabError` if no tab is open under that name.
        """
        try:
            return self._tabs[name]
        except KeyError:
            raise UnknownTabError(f"no tab named {name!r} is open") from None

    async def close_tab(self, name: str) -> None:
        """Close and deregister the tab named ``name``."""
        page = self.get_tab(name)
        await page.close()
        del self._tabs[name]

    def list_tabs(self) -> list[str]:
        """Every currently-open tab name, sorted for deterministic output."""
        return sorted(self._tabs)

    async def close_all(self) -> None:
        """Close and deregister every open tab."""
        for name in list(self._tabs):
            await self.close_tab(name)

    async def bring_to_front(self, name: str) -> None:
        """Focus the tab named ``name`` (Playwright's own tab-switch call)."""
        await self.get_tab(name).bring_to_front()
