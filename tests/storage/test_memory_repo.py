"""Tests for the in-memory OpportunityRepository."""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.core.interfaces import OpportunityRepository
from career_agent.domain.models import Opportunity, Provenance
from career_agent.storage.memory import InMemoryOpportunityRepository


def _opp(
    opportunity_id: str = "id-1",
    *,
    canonical_company: str = "acme",
    title: str = "Engineer",
    location: str | None = None,
    ats_ref: str | None = None,
) -> Opportunity:
    return Opportunity(
        id=opportunity_id,
        company_id="acme",
        canonical_company=canonical_company,
        title=title,
        source="ats_api",
        source_url="https://example.invalid/1",
        provenance=Provenance(
            method="structured_api",
            reference="https://example.invalid/api/1",
            extraction_confidence=1.0,
        ),
        ats_ref=ats_ref,
        location=location,
        description_raw="",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_in_memory_repo_satisfies_the_contract() -> None:
    assert isinstance(InMemoryOpportunityRepository(), OpportunityRepository)


def test_in_memory_repo_exposes_only_the_contract_methods() -> None:
    """Fidelity guard: the in-memory impl must not add public convenience
    methods the SQLite impl won't also have, or the later swap isn't a drop-in.
    Only `add` and `get` are public."""
    public = {
        name
        for name in vars(InMemoryOpportunityRepository).keys()
        if not name.startswith("_")
    }
    assert public == {"add", "get"}


async def test_add_is_idempotent_by_id() -> None:
    repo = InMemoryOpportunityRepository()
    assert await repo.add(_opp("id-1")) is True
    assert await repo.add(_opp("id-1")) is False  # duplicate id


async def test_get_returns_stored_or_none() -> None:
    repo = InMemoryOpportunityRepository()
    stored = _opp("id-1")
    await repo.add(stored)
    assert (await repo.get("id-1")) == stored
    assert (await repo.get("missing")) is None


async def test_cross_source_duplicate_is_deduped_by_fingerprint() -> None:
    """ADR-0014 two-key: a non-authoritative opportunity (e.g. an HN or web
    hit, no native id) whose canonical company + title + location match a known
    ATS job is a duplicate -- even though its primary id differs."""
    repo = InMemoryOpportunityRepository()
    ats_job = _opp(
        "greenhouse:acme:1",
        canonical_company="acme.com",
        title="Senior Rust Engineer",
        location="Remote",
        ats_ref="1",  # authoritative
    )
    # same job, discovered via a non-authoritative source: different primary id,
    # no native ref, but the same canonical company/title/location.
    hn_hit = _opp(
        "fingerprint-hash-xyz",
        canonical_company="acme.com",
        title="Senior Rust Engineer",
        location="Remote",
        ats_ref=None,  # non-authoritative
    )
    assert await repo.add(ats_job) is True
    assert await repo.add(hn_hit) is False  # deduped by fingerprint match


async def test_two_authoritative_reqs_sharing_a_fingerprint_stay_separate() -> None:
    """The negative guarantee two-key exists to protect: two distinct ATS reqs
    at one company with identical title+location (different native ids) must NOT
    merge. A dedup that only proves things merge is half a test."""
    repo = InMemoryOpportunityRepository()
    req_a = _opp(
        "greenhouse:acme:1",
        canonical_company="acme",
        title="Software Engineer",
        location="Remote",
        ats_ref="1",
    )
    req_b = _opp(
        "greenhouse:acme:2",  # distinct native id
        canonical_company="acme",
        title="Software Engineer",
        location="Remote",
        ats_ref="2",
    )
    assert await repo.add(req_a) is True
    assert await repo.add(req_b) is True  # same fingerprint, but both authoritative
    assert (await repo.get("greenhouse:acme:1")) is not None
    assert (await repo.get("greenhouse:acme:2")) is not None
