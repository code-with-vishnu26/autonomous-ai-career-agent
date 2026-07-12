"""Failure-diagnostics capture for browser actions (Phase 62, ADR-0080).

On any browser-action failure, this module takes a screenshot, dumps the
page's HTML, and writes out any console log lines collected up to that
point -- so a human reviewing a ``FAILED``/``UNKNOWN`` submission has
something to look at beyond an exception message. Never writes on the
happy path -- only called from an ``except`` block.

Best-effort by construction: a failure while capturing diagnostics about
a failure must never mask or replace the real exception. Every capture
call swallows its own errors and returns what it managed to get, down to
``None`` if nothing could be captured at all.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import ConsoleMessage, Page

logger = logging.getLogger(__name__)

#: Bounded so a long-lived page (a slow ATS form, a stuck challenge) can
#: never grow this without limit -- oldest entries drop first, matching
#: the "most recent activity is what matters for debugging a failure"
#: intent, not a completeness guarantee.
_MAX_CONSOLE_LINES = 500


class ConsoleLogCollector:
    """Subscribes to a page's console output and keeps the last N lines.

    Attach once per page, right after creation, via :meth:`attach` -- the
    collector itself never opens or closes anything.
    """

    def __init__(self) -> None:
        """Start with an empty, bounded buffer."""
        self._lines: deque[str] = deque(maxlen=_MAX_CONSOLE_LINES)

    def attach(self, page: Page) -> None:
        """Start recording ``page``'s console messages."""
        page.on("console", self._on_console_message)

    def _on_console_message(self, message: ConsoleMessage) -> None:
        timestamp = datetime.now(UTC).isoformat()
        self._lines.append(f"[{timestamp}] {message.type}: {message.text}")

    @property
    def lines(self) -> list[str]:
        """A snapshot of the collected lines, oldest first."""
        return list(self._lines)


@dataclass(frozen=True)
class FailureDiagnostics:
    """Where each captured artifact landed -- any field may be ``None``."""

    directory: Path
    screenshot_path: Path | None
    html_path: Path | None
    console_log_path: Path | None


async def capture_failure_diagnostics(
    page: Page,
    *,
    artifacts_dir: Path,
    correlation_id: str,
    console_log: ConsoleLogCollector | None = None,
) -> FailureDiagnostics | None:
    """Best-effort screenshot + HTML + console-log dump for a failed action.

    Returns ``None`` (never raises) if the directory can't even be
    created -- every individual artifact within it is independently
    best-effort too, so a screenshot failing (e.g. the page already
    closed) still leaves the HTML/console dump attempts to run.
    """
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    directory = artifacts_dir / f"{correlation_id}_{timestamp}"
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.warning(
            "Could not create browser-failure diagnostics directory %s",
            directory,
            exc_info=True,
        )
        return None

    screenshot_path = await _try_screenshot(page, directory)
    html_path = await _try_html_dump(page, directory)
    console_log_path = _try_console_dump(console_log, directory)

    return FailureDiagnostics(
        directory=directory,
        screenshot_path=screenshot_path,
        html_path=html_path,
        console_log_path=console_log_path,
    )


async def _try_screenshot(page: Page, directory: Path) -> Path | None:
    path = directory / "screenshot.png"
    try:
        await page.screenshot(path=str(path), full_page=True)
    except Exception:  # noqa: BLE001 -- diagnostics capture must never raise
        logger.warning("Could not capture failure screenshot", exc_info=True)
        return None
    return path


async def _try_html_dump(page: Page, directory: Path) -> Path | None:
    path = directory / "page.html"
    try:
        html = await page.content()
        path.write_text(html, encoding="utf-8")
    except Exception:  # noqa: BLE001 -- diagnostics capture must never raise
        logger.warning("Could not capture failure page HTML", exc_info=True)
        return None
    return path


def _try_console_dump(
    console_log: ConsoleLogCollector | None, directory: Path
) -> Path | None:
    if console_log is None:
        return None
    path = directory / "console.log"
    try:
        path.write_text("\n".join(console_log.lines), encoding="utf-8")
    except OSError:
        logger.warning("Could not write failure console log", exc_info=True)
        return None
    return path
