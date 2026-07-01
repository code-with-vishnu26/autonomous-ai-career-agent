"""Structural (Protocol) tests for career_agent.core.interfaces.

These are duck-typed structural checks, not integration tests: each fake
implementation exists only to prove the Protocol's shape is satisfiable and
that runtime_checkable isinstance() checks work as the plugin registry
(Phase 3) will rely on them.
"""

from __future__ import annotations

from datetime import datetime

from career_agent.core.events import ApplicationSubmitted, Event
from career_agent.core.interfaces import (
    AgentBase,
    Applicator,
    ATSAdapter,
    NotificationSink,
    OpportunitySource,
    ProviderCapabilities,
    ResumeGenerator,
    SearchProvider,
    SearchQuery,
    SearchResult,
    Task,
    TruthfulnessGate,
)
from career_agent.domain.models import (
    Application,
    BasicsSection,
    Company,
    MasterProfile,
    Opportunity,
    Provenance,
    TailoredContent,
    TailoredResumeDraft,
    TruthfulnessResult,
)


class _FakeAgent:
    name = "fake-agent"

    async def handle(self, task: Task) -> None:
        return None


class _FakeSearchProvider:
    capabilities = ProviderCapabilities(
        supports_site_search=True,
        supports_freshness=False,
        supports_news=False,
        supports_semantic_search=True,
        supports_images=False,
    )

    async def health(self):
        from career_agent.core.interfaces import ProviderHealth

        return ProviderHealth(
            latency_ms_p50=100.0, success_rate=0.99, cost_per_query=0.001
        )

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        return [SearchResult(url="https://example.com", title="x", snippet="y")]


class _FakeOpportunitySource:
    async def fetch(self, since: datetime) -> list[Opportunity]:
        return []


class _FakeATSAdapter:
    ats_kind = "greenhouse"

    async def fetch_postings(self, company: Company) -> list[Opportunity]:
        return []

    async def submit(self, application: Application) -> Event:
        return ApplicationSubmitted(
            correlation_id="c1", application_id=application.id, tier_used="ats_api"
        )


class _FakeApplicator:
    async def apply(self, application: Application) -> Event:
        return ApplicationSubmitted(
            correlation_id="c1", application_id=application.id, tier_used="browser"
        )


class _FakeResumeGenerator:
    async def tailor(
        self, opportunity: Opportunity, profile: MasterProfile
    ) -> TailoredResumeDraft:
        return TailoredResumeDraft(
            opportunity_id=opportunity.id,
            profile_version=profile.version,
            content=TailoredContent(summary="Engineer"),
        )


class _FakeTruthfulnessGate:
    async def verify(
        self, draft: TailoredResumeDraft, profile: MasterProfile
    ) -> TruthfulnessResult:
        return TruthfulnessResult(
            profile_version=draft.profile_version, approved=True, statements=[]
        )


class _FakeNotificationSink:
    async def notify(self, event: Event) -> None:
        return None


def test_agent_base_is_structurally_satisfiable() -> None:
    assert isinstance(_FakeAgent(), AgentBase)


def test_search_provider_is_structurally_satisfiable() -> None:
    assert isinstance(_FakeSearchProvider(), SearchProvider)


def test_opportunity_source_is_structurally_satisfiable() -> None:
    assert isinstance(_FakeOpportunitySource(), OpportunitySource)


def test_ats_adapter_is_structurally_satisfiable() -> None:
    assert isinstance(_FakeATSAdapter(), ATSAdapter)


def test_applicator_is_one_interface_not_three() -> None:
    """A single Applicator Protocol covers all tiers; there is no separate
    ApiApplicator/BrowserApplicator/EmailApplicator interface to satisfy."""
    assert isinstance(_FakeApplicator(), Applicator)


def test_resume_generator_and_truthfulness_gate_are_separate_protocols() -> None:
    """A ResumeGenerator has no method that can mark its own output verified
    -- verification lives on a distinct interface (ADR-0003)."""
    generator_methods = {
        name for name in dir(ResumeGenerator) if not name.startswith("_")
    }
    gate_methods = {name for name in dir(TruthfulnessGate) if not name.startswith("_")}
    assert "verify" not in generator_methods
    assert "tailor" not in gate_methods
    assert isinstance(_FakeResumeGenerator(), ResumeGenerator)
    assert isinstance(_FakeTruthfulnessGate(), TruthfulnessGate)


def test_notification_sink_is_structurally_satisfiable() -> None:
    assert isinstance(_FakeNotificationSink(), NotificationSink)


async def test_generator_then_gate_orchestration_never_self_approves() -> None:
    """End-to-end of the two-step flow the Resume Agent (Phase 7) will run:
    tailor() produces an unverified draft; only verify() can approve it."""
    generator = _FakeResumeGenerator()
    gate = _FakeTruthfulnessGate()
    profile = MasterProfile(
        version="v1", basics=BasicsSection(name="Ada", email="ada@example.com")
    )
    opportunity = Opportunity(
        id="opp-1",
        company_id="co-1",
        title="Engineer",
        source="ats_api",
        source_url="https://example.com/job",
        provenance=Provenance(
            method="structured_api",
            reference="https://example.com/api/job",
            extraction_confidence=1.0,
        ),
        description_raw="...",
        discovered_at=datetime.now(),
    )
    draft = await generator.tailor(opportunity, profile)
    assert not hasattr(draft, "truthfulness")  # drafts cannot carry a verdict
    result = await gate.verify(draft, profile)
    assert result.profile_version == draft.profile_version
