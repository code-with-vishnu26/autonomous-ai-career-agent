"""Deterministic provider detection + adapter lookup (Phase 48, ADR-0066).

The CLI (and any future caller) never switches on provider names -- it
asks the registry to find the adapter for a URL. Detection is pure,
deterministic pattern matching, the same discipline
:func:`~career_agent.domain.ats_urls.resolve_ats_kind` already uses for
Greenhouse/Lever/Ashby (reused here, not reimplemented) -- **no AI, no
heuristic scoring, no network fetch** to decide which adapter applies.
"""

from __future__ import annotations

from career_agent.domain.ats_urls import resolve_ats_kind
from career_agent.integrations.adapters.base import (
    UnsupportedProviderError,
    WebsiteAdapter,
)

#: Hostname fragments for providers with no ATS-style
#: ``ATS_URL_PATTERNS`` entry (job-board aggregators, plus Workday's real,
#: publicly documented multi-tenant hosting domain -- not a guess, the
#: same category of "this platform's own known public URL shape" as
#: ``ats_urls.py``'s existing patterns, just host-based rather than
#: path-based since these platforms don't share one path convention).
_HOSTNAME_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("myworkdayjobs.com", "workday"),
    ("remoteok.com", "remoteok"),
    ("remoteok.io", "remoteok"),
    ("remotive.com", "remotive"),
    ("arbeitnow.com", "arbeitnow"),
    ("themuse.com", "themuse"),
)


def detect_provider(url: str) -> str | None:
    """The provider name for ``url``, or ``None`` if nothing matches.

    Tries the existing ATS URL patterns first (Greenhouse/Lever/Ashby),
    then this package's own hostname table for job boards + Workday.
    """
    ats_kind = resolve_ats_kind(url)
    if ats_kind is not None:
        return ats_kind
    lowered = url.lower()
    for fragment, provider in _HOSTNAME_PROVIDERS:
        if fragment in lowered:
            return provider
    return None


class AdapterRegistry:
    """Looks up the right :class:`WebsiteAdapter` for a URL."""

    def __init__(self, adapters: list[WebsiteAdapter]) -> None:
        """Register every known adapter, in priority order.

        Order matters only in the pathological case of two adapters both
        claiming the same URL (``supports()`` disagreement) -- the first
        registered wins. No two adapters in this package's own
        :func:`default_registry` do.
        """
        self._adapters = adapters

    def find(self, url: str) -> WebsiteAdapter:
        """The adapter that claims ``url``.

        Raises :class:`UnsupportedProviderError` if none does -- never
        returns a best-guess adapter for an unrecognized URL.
        """
        for adapter in self._adapters:
            if adapter.supports(url):
                return adapter
        raise UnsupportedProviderError(
            f"no registered adapter recognizes {url!r} -- see "
            f"integrations/adapters/README or ADR-0066 for the list of "
            f"supported providers"
        )

    def providers(self) -> list[str]:
        """Every registered adapter's provider name, in registration order."""
        return [adapter.provider for adapter in self._adapters]
