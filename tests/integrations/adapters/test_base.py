"""Phase 48 (ADR-0066): shared base-package behavior -- capability
defaults, the universal fail-closed ``prepare_application()`` stub, and
generic page-metadata extraction driven against a real, local Chromium
instance (same discipline as ``tests/agents/test_browser_applicator.py``
and Phase 47's browser tests). Every navigation uses a ``data:`` URL;
nothing here ever makes a real network request.
"""

from __future__ import annotations

import glob

import pytest

from career_agent.integrations.adapters.base import (
    AdapterCapabilities,
    FeatureUnavailableError,
    extract_generic_job_metadata,
)
from career_agent.integrations.adapters.greenhouse import GreenhouseAdapter
from career_agent.integrations.browser.browser_manager import BrowserManager
from career_agent.integrations.browser.session_manager import SessionManager
from career_agent.integrations.browser.tab_manager import TabManager
from career_agent.integrations.browser_session import EncryptedSessionStore
from tests._fakes import FakeHttpClient, FakeKeyProvider


def test_adapter_capabilities_default_to_all_false() -> None:
    """No preference means 'unverified,' never an implicit True."""
    capabilities = AdapterCapabilities()
    assert capabilities.supports_resume_upload is False
    assert capabilities.supports_cover_letter_upload is False
    assert capabilities.supports_easy_apply is False


async def test_prepare_application_always_raises_this_phase() -> None:
    """Load-bearing non-goal guard: every adapter's prepare_application()
    must fail closed, never silently no-op, this phase."""
    adapter = GreenhouseAdapter(["acme"], client=FakeHttpClient())
    with pytest.raises(FeatureUnavailableError):
        await adapter.prepare_application()


def _chromium_executable() -> str | None:
    matches = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    return matches[-1] if matches else None


pytestmark = pytest.mark.skipif(
    _chromium_executable() is None,
    reason="no local Chromium build found for real-browser tests",
)


async def test_extract_generic_job_metadata_prefers_open_graph_tags() -> None:
    manager = BrowserManager(chromium_executable_path=_chromium_executable())
    try:
        await manager.launch(headless=True)
        context = await manager.new_context()
        page = await context.new_page()
        await page.goto(
            "data:text/html,<html><head>"
            "<title>Fallback Title</title>"
            "<meta property='og:title' content='Backend Engineer'>"
            "<meta property='og:description' content='Build things.'>"
            "</head><body></body></html>"
        )
        metadata = await extract_generic_job_metadata(page)
        assert metadata["title"] == "Backend Engineer"
        assert metadata["description"] == "Build things."
    finally:
        await manager.close()


async def test_extract_generic_job_metadata_falls_back_to_title_tag() -> None:
    manager = BrowserManager(chromium_executable_path=_chromium_executable())
    try:
        await manager.launch(headless=True)
        context = await manager.new_context()
        page = await context.new_page()
        await page.goto(
            "data:text/html,<html><head><title>Plain Title</title></head>"
            "<body></body></html>"
        )
        metadata = await extract_generic_job_metadata(page)
        assert metadata["title"] == "Plain Title"
        assert metadata["description"] is None
    finally:
        await manager.close()


async def test_greenhouse_adapter_open_job_uses_tab_manager() -> None:
    """The browser-facing hooks (open_job/extract_job/detect_login) are
    inherited from BrowserAdapterMixin, exercised here through one real
    adapter -- proving the mixin actually wires into a real TabManager."""
    manager = BrowserManager(chromium_executable_path=_chromium_executable())
    try:
        await manager.launch(headless=True)
        context = await manager.new_context()
        tabs = TabManager(context)
        adapter = GreenhouseAdapter(["acme"], client=FakeHttpClient())
        page = await adapter.open_job(
            tabs, "job-1", "data:text/html,<h1>A Real Job</h1>"
        )
        assert tabs.get_tab("job-1") is page
        assert await page.text_content("h1") == "A Real Job"
    finally:
        await manager.close()


async def test_greenhouse_adapter_extract_job_uses_generic_metadata() -> None:
    manager = BrowserManager(chromium_executable_path=_chromium_executable())
    try:
        await manager.launch(headless=True)
        context = await manager.new_context()
        tabs = TabManager(context)
        adapter = GreenhouseAdapter(["acme"], client=FakeHttpClient())
        page = await adapter.open_job(
            tabs,
            "job-1",
            "data:text/html,<html><head><title>A Real Job</title></head>"
            "<body></body></html>",
        )
        metadata = await adapter.extract_job(page)
        assert metadata["title"] == "A Real Job"
    finally:
        await manager.close()


async def test_greenhouse_adapter_detect_login_delegates_to_session_manager(
    tmp_path,
) -> None:
    manager = BrowserManager(chromium_executable_path=_chromium_executable())
    try:
        await manager.launch(headless=True)
        context = await manager.new_context()
        tabs = TabManager(context)
        adapter = GreenhouseAdapter(["acme"], client=FakeHttpClient())
        page = await adapter.open_job(
            tabs,
            "job-1",
            "data:text/html,<button id='account-menu'>Account</button>",
        )
        sessions = SessionManager(
            EncryptedSessionStore(tmp_path, FakeKeyProvider())
        )
        assert await adapter.detect_login(sessions, page, "#account-menu") is True
        assert await adapter.detect_login(sessions, page, "#no-such-id") is False
    finally:
        await manager.close()
