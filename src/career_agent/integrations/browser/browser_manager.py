"""Browser lifecycle management: launch/close a real Chromium instance.

Phase 47 (ADR-0065): the low-level "have a running browser" primitive
other future browser-driven agents build on. Structurally cannot open a
job application, fill a form, or submit anything -- it has no knowledge of
jobs, ATS forms, or the domain model at all, only Playwright's own
``Browser``/``BrowserContext`` types (checkable by reading this file's
imports, not merely by docstring claim).

Reuses this project's existing ``chromium_executable_path`` override
pattern (:mod:`career_agent.agents.apply.browser_applicator`, ADR-0020):
production passes ``None`` and lets Playwright find its own matched
browser; this sandbox has a version-mismatched pre-installed Chromium, so
tests point at it explicitly (see that module's test file for the
``glob``-based lookup this mirrors).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Playwright


class BrowserLaunchError(Exception):
    """Playwright could not launch/attach to a Chromium instance."""


class BrowserManager:
    """Launches and closes a single Chromium ``Browser`` for this process.

    Two context modes, matching the Phase 47 brief's "persistent profile"
    and "reuse browser sessions" as two distinct capabilities:

    - :meth:`launch_persistent_context` -- a Chrome-native persistent
      profile (``user_data_dir``): cookies/localStorage/login state
      persist on disk across process restarts automatically, no explicit
      save/load step. The simplest way to "stay logged in."
    - :meth:`launch` + :meth:`new_context` -- an ephemeral browser with an
      explicit, injectable ``storage_state`` (what
      :class:`~career_agent.integrations.browser_session.EncryptedSessionStore`
      already saves/loads, encrypted at rest, ADR-0020) -- the same
      pattern ``BrowserApplicator`` already uses. Use this when session
      state must be encrypted at rest rather than left as a plaintext
      profile directory.

    Not headless by default (``headless=False``) -- a human must be able
    to see and interact with the window for :class:`~career_agent.
    integrations.browser.session_manager.SessionManager`'s login-wait flow
    to mean anything; ``headless=True`` is for tests/CI that never need a
    human to look at the screen.
    """

    def __init__(self, *, chromium_executable_path: str | None = None) -> None:
        """Configure the Chromium executable override (``None`` in production)."""
        self._chromium_executable_path = chromium_executable_path
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._persistent_context: BrowserContext | None = None

    async def launch(self, *, headless: bool = False) -> Browser:
        """Start Playwright and launch Chromium.

        Idempotent: a second call while already launched returns the
        existing ``Browser`` rather than launching a duplicate.
        """
        if self._browser is not None:
            return self._browser
        from playwright.async_api import async_playwright

        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                executable_path=self._chromium_executable_path,
                headless=headless,
            )
        except Exception as exc:  # noqa: BLE001 -- wrap into our own error type
            raise BrowserLaunchError(f"could not launch Chromium: {exc}") from exc
        return self._browser

    async def new_context(
        self, *, storage_state: dict[str, object] | None = None
    ) -> BrowserContext:
        """A fresh context on the already-launched browser.

        Optionally seeded with a previously saved ``storage_state``
        (:meth:`~career_agent.integrations.browser.session_manager.
        SessionManager.load`). Raises :class:`BrowserLaunchError` if
        :meth:`launch` has not been called yet.
        """
        if self._browser is None:
            raise BrowserLaunchError("launch() must be called before new_context()")
        return await self._browser.new_context(
            storage_state=storage_state if storage_state else None
        )

    async def launch_persistent_context(
        self, user_data_dir: Path, *, headless: bool = False
    ) -> BrowserContext:
        """A persistent Chrome profile at ``user_data_dir``.

        Cookies/localStorage/login state survive across process restarts
        automatically, on disk -- no explicit save/load call needed.
        Distinct from :meth:`launch` + :meth:`new_context` (this call
        launches the browser *and* returns its one context together,
        matching Playwright's own persistent-context API shape).
        """
        from playwright.async_api import async_playwright

        try:
            self._playwright = await async_playwright().start()
            context = await self._playwright.chromium.launch_persistent_context(
                str(user_data_dir),
                executable_path=self._chromium_executable_path,
                headless=headless,
            )
        except Exception as exc:  # noqa: BLE001
            raise BrowserLaunchError(
                f"could not launch a persistent Chromium profile at "
                f"{user_data_dir}: {exc}"
            ) from exc
        self._browser = context.browser
        self._persistent_context = context
        return context

    async def close(self) -> None:
        """Tear down whatever was launched.

        Safe to call even if nothing was launched, or twice -- every step
        is guarded and best-effort so a failure tearing one thing down
        never skips tearing down the rest.
        """
        if self._persistent_context is not None:
            try:
                await self._persistent_context.close()
            except Exception:  # noqa: BLE001 -- best-effort teardown
                pass
            self._persistent_context = None
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:  # noqa: BLE001 -- best-effort teardown
                pass
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
