"""Website Adapter Framework: shared building blocks (Phase 48, ADR-0066).

The Protocol, capabilities model, exceptions, and one generic
(non-vendor-specific) page-extraction helper every adapter may use.

**Discovery is not reimplemented here.** Six of the seven providers this
phase covers already have a real, working, tested, API-based
:class:`~career_agent.core.interfaces.OpportunitySource`
(``plugins/sources/{greenhouse,lever,ashby,job_boards}.py``) -- faster and
more reliable than browser scraping, and already wired into
``career-agent discover``. Every concrete adapter's ``search()`` delegates
to its existing source rather than re-fetching the same data through a
browser. What is genuinely new is the browser-facing half: opening a job
URL in a real tab (Phase 47's ``TabManager``), a generic page-metadata
extraction fallback, login detection (Phase 47's ``SessionManager``), and
declared per-platform capabilities.

**No vendor-specific DOM selectors are guessed anywhere in this package.**
This project already has one hard-won lesson about that
(:mod:`career_agent.agents.apply.form_fillers`'s docstring: Lever's and
Ashby's *application-form* selectors were left as explicit stubs until a
real, live posting could be inspected, rather than guessed). The
*job-posting content* DOM (title, description) is a different surface
this project has never inspected on any live posting either, so
:func:`extract_generic_job_metadata` deliberately uses only two universal,
standards-based signals every well-formed web page can be expected to
carry -- the ``<title>`` element and Open Graph meta tags
(``og:title``/``og:description``) -- never a guessed vendor-specific CSS
class or ``id``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pydantic import BaseModel

if TYPE_CHECKING:
    from playwright.async_api import Page

    from career_agent.domain.models import Opportunity
    from career_agent.integrations.browser.session_manager import SessionManager
    from career_agent.integrations.browser.tab_manager import TabManager


class UnsupportedProviderError(Exception):
    """No registered adapter's ``supports()`` matched this URL."""


class PageNotLoadedError(Exception):
    """A browser-facing method was called before :meth:`WebsiteAdapter.open_job`."""


class FeatureUnavailableError(Exception):
    """This adapter does not (yet) support the requested capability.

    Raised instead of guessing or silently no-op'ing -- the same
    fail-closed, name-the-real-gap discipline as
    :class:`~career_agent.agents.apply.form_fillers.FormFillerNotImplementedError`.
    Every ``prepare_application()`` call raises this in Phase 48 by
    design: form-filling and submission are explicitly out of scope this
    phase (Phase 51+), not silently unimplemented.
    """


class AdapterCapabilities(BaseModel):
    """What a website adapter's platform supports, declared -- not guessed.

    Mirrors :class:`~career_agent.core.interfaces.ProviderCapabilities`'s
    existing "declared on the interface so a future Planner can filter
    without provider-specific knowledge" pattern (ADR-0002), applied to
    application platforms instead of search providers. Every value here is
    grounded in real evidence already in this codebase (mainly
    :mod:`career_agent.agents.apply.form_fillers`'s verified/stubbed
    selectors), not assumption -- see each adapter module's docstring for
    its specific evidence. ``False``/unset never means "confirmed absent,"
    only "not yet verified present" -- the same discipline
    ``LegalStatusSection`` and ``JobPreferences`` already apply to their
    own optional fields.
    """

    supports_resume_upload: bool = False
    supports_cover_letter_upload: bool = False
    supports_easy_apply: bool = False


@runtime_checkable
class WebsiteAdapter(Protocol):
    """The one interface every job-website adapter implements.

    ``provider`` is a stable, lowercase identifier (``"greenhouse"``,
    ``"workday"``, ...) matching :func:`~career_agent.domain.ats_urls.
    resolve_ats_kind`'s vocabulary where the platform is one of the three
    ATS kinds that function already recognizes, so a caller never has to
    reconcile two different naming schemes for the same platform.
    """

    provider: str
    capabilities: AdapterCapabilities

    def supports(self, url: str) -> bool:
        """Whether this adapter recognizes ``url`` as its own platform."""
        ...

    async def search(self, **kwargs: object) -> list[Opportunity]:
        """Discover postings on this platform.

        Delegates to this platform's existing, real
        :class:`~career_agent.core.interfaces.OpportunitySource` where one
        exists (six of seven providers this phase covers); raises
        :class:`FeatureUnavailableError` where none does (Workday).
        """
        ...

    async def open_job(self, tabs: TabManager, name: str, url: str) -> Page:
        """Open ``url`` in a new named tab (Phase 47's ``TabManager``)."""
        ...

    async def extract_job(self, page: Page) -> dict[str, str | None]:
        """Best-effort, generic metadata from an already-open job page.

        Returns ``{"title": ..., "description": ...}`` (either value may be
        ``None`` if absent) via :func:`extract_generic_job_metadata` --
        never a vendor-specific guessed selector. This is a fallback for
        when only a URL is known (no structured API data available), not
        the primary path ``search()`` uses.
        """
        ...

    async def detect_login(
        self, sessions: SessionManager, page: Page, indicator_selector: str
    ) -> bool:
        """Whether the current page shows this platform's logged-in state.

        ``indicator_selector`` is supplied by the caller -- this project
        has no verified "logged in" selector for any of these platforms
        (the same "don't guess a selector" discipline as everywhere else
        in this package). Delegates to Phase 47's
        ``SessionManager.is_logged_in`` -- never types or clicks anything.
        """
        ...

    async def prepare_application(self, *args: object, **kwargs: object) -> object:
        """Not implemented this phase.

        Always raises :class:`FeatureUnavailableError` -- form-filling and
        submission preparation are explicitly out of scope for Phase 48
        (see that phase's non-goals); this method exists on the interface
        now so a future phase extends it rather than bolting it on.
        """
        ...


async def extract_generic_job_metadata(page: Page) -> dict[str, str | None]:
    """Universal, standards-based job metadata -- never a guessed selector.

    Tries Open Graph meta tags first (``og:title``/``og:description`` --
    a documented cross-site convention many job boards populate, not a
    vendor-specific internal DOM detail), then falls back to the page's
    plain ``<title>`` element (present on essentially every well-formed
    HTML page) for the title only -- there is no universal fallback for a
    description, so it stays ``None`` if no Open Graph tag is present.
    """
    title: str | None = None
    description: str | None = None

    og_title = await page.query_selector("meta[property='og:title']")
    if og_title is not None:
        title = await og_title.get_attribute("content")

    og_description = await page.query_selector("meta[property='og:description']")
    if og_description is not None:
        description = await og_description.get_attribute("content")

    if not title:
        page_title = await page.title()
        title = page_title if page_title else None

    return {"title": title, "description": description}


class BrowserAdapterMixin:
    """Shared implementation of :class:`WebsiteAdapter`'s browser-facing half.

    Every concrete adapter's ``open_job``/``extract_job``/``detect_login``/
    ``prepare_application`` behavior is the same (only ``supports()``,
    ``search()``, ``provider``, and ``capabilities`` genuinely differ per
    platform) -- inheriting this mixin is what keeps each provider module
    small and focused on what actually differs, rather than seven
    near-identical copies of the same four methods.
    """

    async def open_job(self, tabs: TabManager, name: str, url: str) -> Page:
        """Open ``url`` in a new named tab."""
        return await tabs.open_tab(name, url=url)

    async def extract_job(self, page: Page) -> dict[str, str | None]:
        """Generic Open-Graph/title extraction -- see module docstring."""
        return await extract_generic_job_metadata(page)

    async def detect_login(
        self, sessions: SessionManager, page: Page, indicator_selector: str
    ) -> bool:
        """Delegates to Phase 47's ``SessionManager.is_logged_in``."""
        return await sessions.is_logged_in(page, indicator_selector)

    async def prepare_application(self, *args: object, **kwargs: object) -> object:
        """Always raises -- see :class:`FeatureUnavailableError`."""
        provider = getattr(self, "provider", "this adapter")
        raise FeatureUnavailableError(
            f"{provider}: prepare_application() is not implemented in "
            f"Phase 48 -- form-filling and submission preparation are a "
            f"future phase's scope, by design (ADR-0066)"
        )
