"""Phase 47 (ADR-0065): TabManager, driven against a real, local Chromium
instance -- same discipline as ``tests/agents/test_browser_applicator.py``.
Every navigation uses a ``data:`` URL; nothing here ever makes a real
network request.
"""

from __future__ import annotations

import glob

import pytest

from career_agent.integrations.browser.browser_manager import BrowserManager
from career_agent.integrations.browser.tab_manager import (
    DuplicateTabError,
    TabManager,
    UnknownTabError,
)


def _chromium_executable() -> str | None:
    matches = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    return matches[-1] if matches else None


pytestmark = pytest.mark.skipif(
    _chromium_executable() is None,
    reason="no local Chromium build found for real-browser tests",
)


async def _manager_and_tabs() -> tuple[BrowserManager, TabManager]:
    manager = BrowserManager(chromium_executable_path=_chromium_executable())
    await manager.launch(headless=True)
    context = await manager.new_context()
    return manager, TabManager(context)


async def test_open_tab_navigates_and_registers_it_by_name() -> None:
    manager, tabs = await _manager_and_tabs()
    try:
        page = await tabs.open_tab(
            "job-1", url="data:text/html,<h1>Job One</h1>"
        )
        assert await page.text_content("h1") == "Job One"
        assert tabs.get_tab("job-1") is page
    finally:
        await manager.close()


async def test_open_tab_without_url_stays_on_a_blank_page() -> None:
    manager, tabs = await _manager_and_tabs()
    try:
        page = await tabs.open_tab("blank")
        assert page.url in ("about:blank", "")
    finally:
        await manager.close()


async def test_open_tab_with_a_duplicate_name_raises() -> None:
    manager, tabs = await _manager_and_tabs()
    try:
        await tabs.open_tab("job-1", url="data:text/html,<h1>One</h1>")
        with pytest.raises(DuplicateTabError):
            await tabs.open_tab("job-1", url="data:text/html,<h1>Two</h1>")
    finally:
        await manager.close()


async def test_get_tab_for_an_unknown_name_raises() -> None:
    manager, tabs = await _manager_and_tabs()
    try:
        with pytest.raises(UnknownTabError):
            tabs.get_tab("nonexistent")
    finally:
        await manager.close()


async def test_multiple_tabs_are_independently_addressable() -> None:
    """The core multi-tab guarantee: two open tabs must not interfere."""
    manager, tabs = await _manager_and_tabs()
    try:
        await tabs.open_tab("job-1", url="data:text/html,<h1>Job One</h1>")
        await tabs.open_tab("job-2", url="data:text/html,<h1>Job Two</h1>")
        assert await tabs.get_tab("job-1").text_content("h1") == "Job One"
        assert await tabs.get_tab("job-2").text_content("h1") == "Job Two"
        assert tabs.list_tabs() == ["job-1", "job-2"]
    finally:
        await manager.close()


async def test_close_tab_deregisters_and_closes_the_page() -> None:
    manager, tabs = await _manager_and_tabs()
    try:
        page = await tabs.open_tab("job-1", url="data:text/html,<h1>One</h1>")
        await tabs.close_tab("job-1")
        assert tabs.list_tabs() == []
        assert page.is_closed()
        with pytest.raises(UnknownTabError):
            tabs.get_tab("job-1")
    finally:
        await manager.close()


async def test_close_tab_for_an_unknown_name_raises() -> None:
    manager, tabs = await _manager_and_tabs()
    try:
        with pytest.raises(UnknownTabError):
            await tabs.close_tab("nonexistent")
    finally:
        await manager.close()


async def test_close_all_closes_and_deregisters_every_tab() -> None:
    manager, tabs = await _manager_and_tabs()
    try:
        await tabs.open_tab("job-1", url="data:text/html,<h1>One</h1>")
        await tabs.open_tab("job-2", url="data:text/html,<h1>Two</h1>")
        await tabs.close_all()
        assert tabs.list_tabs() == []
    finally:
        await manager.close()


async def test_bring_to_front_does_not_raise_for_a_known_tab() -> None:
    manager, tabs = await _manager_and_tabs()
    try:
        await tabs.open_tab("job-1", url="data:text/html,<h1>One</h1>")
        await tabs.bring_to_front("job-1")  # must not raise
    finally:
        await manager.close()


async def test_bring_to_front_for_an_unknown_name_raises() -> None:
    manager, tabs = await _manager_and_tabs()
    try:
        with pytest.raises(UnknownTabError):
            await tabs.bring_to_front("nonexistent")
    finally:
        await manager.close()
