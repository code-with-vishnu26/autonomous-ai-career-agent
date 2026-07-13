"""Research a company from real, public web sources (Phase 69, ADR-0087).

Takes the :class:`~career_agent.core.interfaces.SearchProvider` *protocol*
(never a concrete plugin -- the composition root injects Exa or Google
CSE), so this stays a downward-only import and is trivially testable with
a fake provider. Returns only what real search results say, with their
source links; it never asks an LLM to invent company facts (the owner's
choice was source-backed accuracy over a convenient-but-approximate AI
brief) and never touches personal data about individuals.
"""

from __future__ import annotations

from career_agent.core.interfaces import SearchProvider, SearchQuery
from career_agent.domain.company_research import CompanyResearch, ResearchSource

#: Cap on sources kept, so an export row stays readable and one company's
#: research is a bounded number of API calls.
_MAX_SOURCES = 5


def _looks_like_careers(url: str) -> bool:
    lowered = url.lower()
    return any(token in lowered for token in ("career", "job", "/join", "hiring"))


async def research_company(
    company: str,
    provider: SearchProvider | None,
    *,
    domain: str | None = None,
) -> CompanyResearch:
    """Find public, source-backed facts about ``company``.

    ``provider is None`` (no search key configured) returns
    :meth:`CompanyResearch.unavailable` -- the honest "we didn't look"
    result, never a fabricated summary. Otherwise it runs one company
    overview search (scoped to the company's own ``domain`` when known,
    for a first-party result) and keeps the top results as sources; the
    first result whose URL looks like a careers/jobs page becomes
    ``careers_url``. A provider error degrades to an empty-but-available
    result, never an exception into the export path.
    """
    if provider is None:
        return CompanyResearch.unavailable()

    query = SearchQuery(text=f"{company} company overview careers", site=domain)
    try:
        results = await provider.search(query)
    except Exception:  # noqa: BLE001 -- research is best-effort; never break export
        return CompanyResearch(available=True, summary="", sources=[])

    kept = results[:_MAX_SOURCES]
    careers_url = next(
        (result.url for result in kept if _looks_like_careers(result.url)), None
    )
    summary = kept[0].snippet.strip() if kept else ""
    return CompanyResearch(
        available=True,
        summary=summary,
        careers_url=careers_url,
        sources=[ResearchSource(title=r.title or r.url, url=r.url) for r in kept],
    )
