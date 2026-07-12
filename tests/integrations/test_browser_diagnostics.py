"""Phase 62 (ADR-0080): failure-diagnostics capture, driven against a real,
local Chromium instance -- the same discipline as this project's other
integrations/browser tests. Every navigation uses a ``data:`` URL; nothing
here ever makes a real network request.
"""

from __future__ import annotations

import glob
from pathlib import Path

import pytest

from career_agent.integrations.browser.diagnostics import (
    ConsoleLogCollector,
    capture_failure_diagnostics,
)


def _chromium_executable() -> str | None:
    """Same lookup as ``tests/agents/test_browser_applicator.py``."""
    matches = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    return matches[-1] if matches else None


pytestmark = pytest.mark.skipif(
    _chromium_executable() is None,
    reason="no local Chromium build found for real-browser tests",
)

_PAGE_WITH_CONSOLE_LOG = (
    "data:text/html,"
    "<html><body><h1>hi</h1>"
    "<script>console.log('hello from the page');</script>"
    "</body></html>"
)


async def _launch_page():
    from playwright.async_api import async_playwright

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        executable_path=_chromium_executable(), headless=True
    )
    page = await browser.new_page()
    return browser, page


async def test_capture_writes_screenshot_html_and_console_log(
    tmp_path: Path,
) -> None:
    browser, page = await _launch_page()
    try:
        console_log = ConsoleLogCollector()
        console_log.attach(page)
        await page.goto(_PAGE_WITH_CONSOLE_LOG)
        await page.wait_for_timeout(50)  # let the console event actually fire

        diagnostics = await capture_failure_diagnostics(
            page,
            artifacts_dir=tmp_path,
            correlation_id="opp-1",
            console_log=console_log,
        )

        assert diagnostics is not None
        assert diagnostics.screenshot_path is not None
        assert diagnostics.screenshot_path.exists()
        assert diagnostics.screenshot_path.stat().st_size > 0

        assert diagnostics.html_path is not None
        assert diagnostics.html_path.exists()
        assert "<h1>hi</h1>" in diagnostics.html_path.read_text(encoding="utf-8")

        assert diagnostics.console_log_path is not None
        assert diagnostics.console_log_path.exists()
        assert "hello from the page" in diagnostics.console_log_path.read_text(
            encoding="utf-8"
        )
    finally:
        await browser.close()


async def test_capture_without_a_console_collector_skips_that_file(
    tmp_path: Path,
) -> None:
    browser, page = await _launch_page()
    try:
        await page.goto(_PAGE_WITH_CONSOLE_LOG)
        diagnostics = await capture_failure_diagnostics(
            page, artifacts_dir=tmp_path, correlation_id="opp-2"
        )
        assert diagnostics is not None
        assert diagnostics.console_log_path is None
        assert diagnostics.screenshot_path is not None
        assert diagnostics.html_path is not None
    finally:
        await browser.close()


async def test_capture_after_the_page_closed_never_raises(tmp_path: Path) -> None:
    """Best-effort by construction -- a page that's already gone (the exact
    situation a crashed/closed browser leaves behind) must not turn
    diagnostics capture itself into a second exception."""
    browser, page = await _launch_page()
    await page.goto(_PAGE_WITH_CONSOLE_LOG)
    await page.close()
    try:
        diagnostics = await capture_failure_diagnostics(
            page, artifacts_dir=tmp_path, correlation_id="opp-3"
        )
        assert diagnostics is not None
        assert diagnostics.screenshot_path is None
        assert diagnostics.html_path is None
    finally:
        await browser.close()


async def test_console_log_collector_is_bounded() -> None:
    browser, page = await _launch_page()
    try:
        collector = ConsoleLogCollector()
        collector.attach(page)
        await page.goto(
            "data:text/html,<script>"
            "for (let i = 0; i < 600; i++) { console.log('line ' + i); }"
            "</script>"
        )
        await page.wait_for_timeout(200)
        assert len(collector.lines) <= 500
    finally:
        await browser.close()
