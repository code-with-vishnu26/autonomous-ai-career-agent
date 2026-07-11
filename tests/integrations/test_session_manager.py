"""Phase 47 (ADR-0065): SessionManager, driven against a real, local
Chromium instance -- same discipline as
``tests/agents/test_browser_applicator.py``. Every navigation uses a
``data:`` URL; nothing here ever makes a real network request.

The load-bearing test in this file is
``test_source_never_calls_a_fill_or_type_method`` -- a static guard that
this module can never gain a code path that types into a page, not merely
a runtime assertion about today's behavior.
"""

from __future__ import annotations

import ast
import glob
import inspect
from pathlib import Path

import pytest

from career_agent.integrations.browser import session_manager as session_manager_module
from career_agent.integrations.browser.browser_manager import BrowserManager
from career_agent.integrations.browser.session_manager import (
    LoginTimeoutError,
    SessionManager,
)
from career_agent.integrations.browser_session import EncryptedSessionStore
from tests._fakes import FakeKeyProvider

_LOGGED_IN_HTML = (
    "data:text/html,<html><body>"
    "<button id='account-menu'>Account</button>"
    "</body></html>"
)
_LOGGED_OUT_HTML = (
    "data:text/html,<html><body><a href='/login'>Log in</a></body></html>"
)


def _chromium_executable() -> str | None:
    matches = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    return matches[-1] if matches else None


pytestmark = pytest.mark.skipif(
    _chromium_executable() is None,
    reason="no local Chromium build found for real-browser tests",
)


def test_source_never_calls_a_fill_or_type_method() -> None:
    """Structural safety guard: this module must never gain a *call* to a
    method that types into a page -- login stays exclusively the human's
    action. An AST check, not a text search, so mentioning these method
    names in a docstring (as this very module's own docstring does, to
    explain the guarantee) can never produce a false failure -- only an
    actual ``x.fill(...)``-shaped call node does."""
    source = inspect.getsource(session_manager_module)
    tree = ast.parse(source)
    forbidden_methods = {"fill", "type", "press_sequentially", "press"}
    called_methods = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    offenders = called_methods & forbidden_methods
    assert not offenders, (
        f"session_manager.py must never call {offenders} -- login "
        f"automation is out of scope by design (ADR-0065)"
    )


async def test_is_logged_in_true_when_indicator_visible() -> None:
    manager = BrowserManager(chromium_executable_path=_chromium_executable())
    try:
        await manager.launch(headless=True)
        context = await manager.new_context()
        page = await context.new_page()
        await page.goto(_LOGGED_IN_HTML)
        session_manager = SessionManager(
            EncryptedSessionStore(Path("/tmp"), FakeKeyProvider())
        )
        assert await session_manager.is_logged_in(page, "#account-menu") is True
    finally:
        await manager.close()


async def test_is_logged_in_false_when_indicator_absent() -> None:
    manager = BrowserManager(chromium_executable_path=_chromium_executable())
    try:
        await manager.launch(headless=True)
        context = await manager.new_context()
        page = await context.new_page()
        await page.goto(_LOGGED_OUT_HTML)
        session_manager = SessionManager(
            EncryptedSessionStore(Path("/tmp"), FakeKeyProvider())
        )
        assert await session_manager.is_logged_in(page, "#account-menu") is False
    finally:
        await manager.close()


async def test_wait_for_login_returns_once_indicator_appears() -> None:
    """A real polling loop against a real page that is already logged in
    on the first poll -- proves the happy path returns, not just that the
    single-shot check does."""
    manager = BrowserManager(chromium_executable_path=_chromium_executable())
    try:
        await manager.launch(headless=True)
        context = await manager.new_context()
        page = await context.new_page()
        await page.goto(_LOGGED_IN_HTML)
        session_manager = SessionManager(
            EncryptedSessionStore(Path("/tmp"), FakeKeyProvider())
        )
        await session_manager.wait_for_login(
            page, "#account-menu", timeout_seconds=5, poll_interval_seconds=0.1
        )
    finally:
        await manager.close()


async def test_wait_for_login_times_out_when_never_logged_in() -> None:
    manager = BrowserManager(chromium_executable_path=_chromium_executable())
    try:
        await manager.launch(headless=True)
        context = await manager.new_context()
        page = await context.new_page()
        await page.goto(_LOGGED_OUT_HTML)
        session_manager = SessionManager(
            EncryptedSessionStore(Path("/tmp"), FakeKeyProvider())
        )
        with pytest.raises(LoginTimeoutError):
            await session_manager.wait_for_login(
                page,
                "#account-menu",
                timeout_seconds=0.3,
                poll_interval_seconds=0.1,
            )
    finally:
        await manager.close()


async def test_save_persists_the_real_context_storage_state(tmp_path: Path) -> None:
    manager = BrowserManager(chromium_executable_path=_chromium_executable())
    try:
        await manager.launch(headless=True)
        context = await manager.new_context()
        store = EncryptedSessionStore(tmp_path, FakeKeyProvider())
        session_manager = SessionManager(store)
        await session_manager.save("test-session", context)
        loaded = session_manager.load("test-session")
        assert loaded is not None
        assert "cookies" in loaded
    finally:
        await manager.close()


def test_load_returns_none_for_a_session_never_saved(tmp_path: Path) -> None:
    store = EncryptedSessionStore(tmp_path, FakeKeyProvider())
    session_manager = SessionManager(store)
    assert session_manager.load("never-saved") is None
