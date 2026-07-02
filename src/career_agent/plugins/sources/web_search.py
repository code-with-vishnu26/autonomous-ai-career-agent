"""Web-search opportunity source (4c slice-2).

The consumer half of the search split: :class:`~career_agent.plugins.search.
exa.ExaSearchProvider` returns raw :class:`SearchResult`s (the ADR-0002 search
port); this class turns them into :class:`Opportunity` objects -- or holds
them, never defaulting an unverified hit to a confident posting. It reuses the
:class:`~career_agent.core.interfaces.HeldCandidateSink` mechanism built for
Hacker News (ADR-0013): a search result is exactly the same kind of unverified
signal a freeform comment is, just wearing a different hat.

**A URL that matches a known ATS pattern is a strong signal, not a confirmed
posting.** The search index can be stale, the listing can be expired, the URL
can 404. Confidence 1.0 is earned by actually parsing the job, never by URL
shape alone -- so a matched URL is handed to the real ATS source
(``GreenhouseSource`` / ``LeverSource`` / ``AshbySource``, reused as-is, not
reimplemented) to confirm. If the ATS confirms it, the returned
``Opportunity`` *is* the ATS source's own record (same id, same
``method="structured_api"``, ``confidence=1.0``) -- it naturally dedups against
an already-known ATS-sourced record via the ADR-0014 two-key identity, exactly
as if the ATS source had found it directly. If the ATS parse fails (404, id not
present, fetch error), the hit is held, never emitted.

A URL with no recognized ATS pattern (a career page, a blog post, a generic
company site) is held directly -- classifying arbitrary web content into a
confident job posting is out of scope for this slice; see ADR-0015.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from career_agent.core.interfaces import (
    HeldCandidateSink,
    HttpClient,
    SearchProvider,
    SearchQuery,
    SearchResult,
)
from career_agent.domain.models import HeldCandidate, Opportunity
from career_agent.plugins.sources.ashby import AshbySource
from career_agent.plugins.sources.greenhouse import GreenhouseSource
from career_agent.plugins.sources.lever import LeverSource

# (ats_kind, pattern) -- pattern captures (board_or_company, job_id)
_ATS_URL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("greenhouse", re.compile(r"boards\.greenhouse\.io/([^/]+)/jobs/([^/?#]+)")),
    ("lever", re.compile(r"jobs\.lever\.co/([^/]+)/([^/?#]+)")),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([^/]+)/([^/?#]+)")),
]

_GENERIC_HELD_CONFIDENCE = 0.15  # a career page / blog post: weak, unstructured
_UNCONFIRMED_HELD_CONFIDENCE = 0.4  # matched an ATS pattern, but didn't parse


class SearchOpportunitySource:
    """Classifies web-search hits into confirmed opportunities or held candidates."""

    def __init__(
        self,
        provider: SearchProvider,
        queries: list[SearchQuery],
        *,
        client: HttpClient,
        held_sink: HeldCandidateSink,
    ) -> None:
        """Configure the source with a search provider and its queries.

        ``client`` is used to *confirm* ATS-pattern hits by re-parsing the real
        ATS source, not to call the search provider itself (that's ``provider``).
        """
        self._provider = provider
        self._queries = queries
        self._client = client
        self._sink = held_sink

    async def fetch(self, since: datetime) -> list[Opportunity]:
        """Run the configured queries.

        Returns confirmed opportunities; holds everything else via the sink.
        """
        opportunities: list[Opportunity] = []
        for query in self._queries:
            for result in await self._provider.search(query):
                verdict = await self._classify(result)
                if isinstance(verdict, Opportunity):
                    if verdict.posted_at is None or verdict.posted_at >= since:
                        opportunities.append(verdict)
                else:
                    await self._sink.record(verdict)
        return opportunities

    async def _classify(self, result: SearchResult) -> Opportunity | HeldCandidate:
        match = _match_ats_pattern(result.url)
        if match is None:
            return self._hold(
                "ambiguous_parse", result, _GENERIC_HELD_CONFIDENCE
            )
        ats_kind, board, job_id = match
        confirmed = await self._confirm_via_ats_parse(ats_kind, board, job_id)
        if confirmed is not None:
            return confirmed
        return self._hold("below_threshold", result, _UNCONFIRMED_HELD_CONFIDENCE)

    async def _confirm_via_ats_parse(
        self, ats_kind: str, board: str, job_id: str
    ) -> Opportunity | None:
        """Hand an ATS-pattern URL to the *real* ATS source to confirm it.

        Deliberately reuses the already-built, already-tested source classes
        rather than re-implementing per-ATS parsing here -- "confirmed" means
        "the ATS's own source found this exact job," nothing weaker.
        """
        source: GreenhouseSource | LeverSource | AshbySource
        if ats_kind == "greenhouse":
            source = GreenhouseSource([board], client=self._client)
        elif ats_kind == "lever":
            source = LeverSource([board], client=self._client)
        elif ats_kind == "ashby":
            source = AshbySource([board], client=self._client)
        else:  # pragma: no cover - unreachable, _match_ats_pattern is exhaustive
            return None
        try:
            opportunities = await source.fetch(_EPOCH)
        except Exception:
            return None
        return next((o for o in opportunities if o.ats_ref == job_id), None)

    def _hold(
        self, reason: str, result: SearchResult, confidence: float
    ) -> HeldCandidate:
        return HeldCandidate(
            source="web_search",
            reason=reason,  # type: ignore[arg-type]
            reference=result.url,
            raw_excerpt=(result.title + " -- " + result.snippet)[:280],
            extraction_confidence=confidence,
            held_at=datetime.now(UTC),
        )


_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _match_ats_pattern(url: str) -> tuple[str, str, str] | None:
    for ats_kind, pattern in _ATS_URL_PATTERNS:
        match = pattern.search(url)
        if match:
            return ats_kind, match.group(1), match.group(2)
    return None
