"""Company research result (Phase 69, ADR-0087).

What the agent could find *from real, public web sources* about an
employer -- a short factual summary, a public careers/application page,
and the source links it drew from. Deliberately carries no information
about named individuals (no HR names, no employee contacts): the owner's
choice was public company channels only, and scraping people's profiles
would violate the very platforms' ToS this project already refuses to
scrape (ADR-0036).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResearchSource(BaseModel):
    """One real web result the research drew from -- a title and its URL."""

    title: str
    url: str


class CompanyResearch(BaseModel):
    """Public, source-backed facts about a company.

    ``available`` is ``False`` when no search provider was configured (no
    Exa/Google CSE key) -- the honest "we didn't look" signal, distinct
    from ``available=True`` with an empty ``sources`` ("we looked, found
    nothing"). Everything here is public and source-linked; no guessed or
    LLM-fabricated facts, and no personal data about individuals.
    """

    available: bool
    summary: str = ""
    careers_url: str | None = None
    sources: list[ResearchSource] = Field(default_factory=list)

    @classmethod
    def unavailable(cls) -> CompanyResearch:
        """No search provider configured -- add an Exa or Google CSE key."""
        return cls(
            available=False,
            summary=(
                "No web-search key configured -- add an Exa or Google Custom "
                "Search API key in Settings to enable company research."
            ),
        )
