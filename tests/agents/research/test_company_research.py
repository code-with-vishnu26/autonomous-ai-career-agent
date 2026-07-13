"""Phase 69 (ADR-0087): company research over a pluggable SearchProvider."""

from __future__ import annotations

from career_agent.agents.research.company_research import research_company
from career_agent.core.interfaces import SearchResult


class _FakeProvider:
    def __init__(self, results: list[SearchResult]) -> None:
        self._results = results
        self.queries: list[str] = []

    async def search(self, query) -> list[SearchResult]:  # noqa: ANN001
        self.queries.append(query.text)
        return self._results


class _FailingProvider:
    async def search(self, query) -> list[SearchResult]:  # noqa: ANN001
        raise RuntimeError("search backend down")


async def test_no_provider_is_honestly_unavailable() -> None:
    research = await research_company("Acme", None)
    assert research.available is False
    assert "no web-search key" in research.summary.lower()
    assert research.sources == []


async def test_returns_source_backed_summary_and_careers_link() -> None:
    provider = _FakeProvider(
        [
            SearchResult(
                url="https://acme.com/careers",
                title="Acme Careers",
                snippet="Acme builds rockets.",
            ),
            SearchResult(
                url="https://acme.com/about",
                title="About Acme",
                snippet="Founded 2020.",
            ),
        ]
    )
    research = await research_company("Acme", provider)
    assert research.available is True
    assert research.summary == "Acme builds rockets."
    assert research.careers_url == "https://acme.com/careers"
    assert [s.url for s in research.sources] == [
        "https://acme.com/careers",
        "https://acme.com/about",
    ]


async def test_no_careers_result_leaves_careers_url_none() -> None:
    provider = _FakeProvider(
        [SearchResult(url="https://acme.com/news", title="News", snippet="Update.")]
    )
    research = await research_company("Acme", provider)
    assert research.careers_url is None
    assert research.available is True


async def test_provider_error_degrades_to_empty_but_available() -> None:
    research = await research_company("Acme", _FailingProvider())
    assert research.available is True  # we looked; the backend just failed
    assert research.summary == ""
    assert research.sources == []


async def test_caps_sources_to_a_readable_number() -> None:
    provider = _FakeProvider(
        [
            SearchResult(url=f"https://acme.com/{i}", title=str(i), snippet="x")
            for i in range(20)
        ]
    )
    research = await research_company("Acme", provider)
    assert len(research.sources) <= 5
