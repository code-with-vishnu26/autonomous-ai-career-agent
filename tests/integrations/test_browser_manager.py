"""Phase 47 (ADR-0065): BrowserManager, driven against a real, local
Chromium instance -- not a Python-level fake standing in for a browser,
the same discipline as ``tests/agents/test_browser_applicator.py``. Every
navigation uses ``about:blank`` or a ``data:`` URL; nothing here ever
makes a real network request.
"""

from __future__ import annotations

import glob
from pathlib import Path

import pytest

from career_agent.integrations.browser.browser_manager import (
    BrowserLaunchError,
    BrowserManager,
)


def _chromium_executable() -> str | None:
    """Same lookup as ``tests/agents/test_browser_applicator.py`` -- this
    sandbox has a version-mismatched pre-installed Chromium, so tests
    point at it explicitly rather than letting Playwright guess."""
    matches = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    return matches[-1] if matches else None


pytestmark = pytest.mark.skipif(
    _chromium_executable() is None,
    reason="no local Chromium build found for real-browser tests",
)


async def test_launch_and_close_a_real_chromium_instance() -> None:
    manager = BrowserManager(chromium_executable_path=_chromium_executable())
    browser = await manager.launch(headless=True)
    assert browser.is_connected()
    await manager.close()
    assert not browser.is_connected()


async def test_launch_is_idempotent_returns_the_same_browser() -> None:
    manager = BrowserManager(chromium_executable_path=_chromium_executable())
    try:
        first = await manager.launch(headless=True)
        second = await manager.launch(headless=True)
        assert first is second
    finally:
        await manager.close()


async def test_new_context_before_launch_raises() -> None:
    manager = BrowserManager(chromium_executable_path=_chromium_executable())
    with pytest.raises(BrowserLaunchError):
        await manager.new_context()


async def test_new_context_produces_a_working_page() -> None:
    manager = BrowserManager(chromium_executable_path=_chromium_executable())
    try:
        await manager.launch(headless=True)
        context = await manager.new_context()
        page = await context.new_page()
        await page.goto("data:text/html,<h1>hello</h1>")
        assert await page.text_content("h1") == "hello"
    finally:
        await manager.close()


async def test_new_context_seeded_with_storage_state_carries_cookies() -> None:
    """The bridge to EncryptedSessionStore: a saved storage_state, handed
    back in, must actually restore into the new context."""
    manager = BrowserManager(chromium_executable_path=_chromium_executable())
    try:
        await manager.launch(headless=True)
        seeded_state = {
            "cookies": [
                {
                    "name": "session",
                    "value": "abc123",
                    "domain": "example.com",
                    "path": "/",
                    "expires": -1,
                    "httpOnly": False,
                    "secure": False,
                    "sameSite": "Lax",
                }
            ],
            "origins": [],
        }
        context = await manager.new_context(storage_state=seeded_state)
        state = await context.storage_state()
        assert state["cookies"][0]["name"] == "session"
        assert state["cookies"][0]["value"] == "abc123"
    finally:
        await manager.close()


async def test_launch_persistent_context_creates_a_working_page(
    tmp_path: Path,
) -> None:
    manager = BrowserManager(chromium_executable_path=_chromium_executable())
    try:
        context = await manager.launch_persistent_context(
            tmp_path / "profile", headless=True
        )
        page = await context.new_page()
        await page.goto("data:text/html,<h1>persistent</h1>")
        assert await page.text_content("h1") == "persistent"
    finally:
        await manager.close()


async def test_launch_persistent_context_profile_dir_persists_on_disk(
    tmp_path: Path,
) -> None:
    """The whole point of a persistent profile: the directory has real
    Chrome profile content after the browser closes, reusable next launch."""
    profile_dir = tmp_path / "profile"
    manager = BrowserManager(chromium_executable_path=_chromium_executable())
    context = await manager.launch_persistent_context(profile_dir, headless=True)
    page = await context.new_page()
    await page.goto("about:blank")
    await manager.close()
    assert profile_dir.is_dir()
    assert any(profile_dir.iterdir())


async def test_close_is_safe_when_nothing_was_launched() -> None:
    manager = BrowserManager(chromium_executable_path=_chromium_executable())
    await manager.close()  # must not raise


async def test_close_is_safe_to_call_twice() -> None:
    manager = BrowserManager(chromium_executable_path=_chromium_executable())
    await manager.launch(headless=True)
    await manager.close()
    await manager.close()  # must not raise
