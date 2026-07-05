"""Core interfaces (ADR-0001, ADR-0004).

The typed contracts every agent and plugin implements against. These are
:class:`typing.Protocol` definitions, not base classes with logic -- Phase 2
defines shape only. Concrete implementations land in the phases that need
them (see ROADMAP.md).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from career_agent.core.events import Event
from career_agent.domain.ats_scoring import AtsGapReport, SemanticKeywordClaim
from career_agent.domain.models import (
    Company,
    DraftedTailoring,
    HeldCandidate,
    HumanConfirmation,
    MasterProfile,
    Opportunity,
    SubmissionPreview,
    SubmittableApplication,
    TailoredResumeDraft,
    TruthfulnessResult,
)


class Task(BaseModel):
    """A unit of work the Planner dispatches to one capability agent."""

    task_type: str
    correlation_id: str
    payload: dict[str, object]


@runtime_checkable
class AgentBase(Protocol):
    """The shape every capability agent must expose to the Planner.

    Per ADR-0001's design principles: single responsibility, stateless where
    possible, and reachable only through this one method -- an agent never
    exposes anything else for another agent (or the Planner) to call.
    """

    name: str

    async def handle(self, task: Task) -> None:
        """Perform ``task``, then return -- results/failures surface as events."""
        ...


# The plugin registry itself is a concrete class, not a Protocol -- see
# :mod:`career_agent.core.registry` (Phase 3, ADR-0004). Plugins do not
# implement a common ``PluginBase`` interface; they implement their
# extension-point protocol below (``SearchProvider``, ``ATSAdapter``, ...) and
# are registered via the ``@register`` decorator + ``discover()``.


# ---------------------------------------------------------------------------
# Search provider abstraction (ADR-0002).
# ---------------------------------------------------------------------------


class ProviderCapabilities(BaseModel):
    """What a search provider supports.

    Lets the Planner match capability to query instead of assuming.
    """

    supports_site_search: bool
    supports_freshness: bool
    supports_news: bool
    supports_semantic_search: bool
    supports_images: bool


class ProviderHealth(BaseModel):
    """Rolling health stats feeding the Planner's dynamic provider ranking."""

    latency_ms_p50: float
    success_rate: float
    cost_per_query: float


class SearchQuery(BaseModel):
    """A search request, carrying the requirements a provider must satisfy."""

    text: str
    requires_semantic: bool = False
    requires_freshness: bool = False
    site: str | None = None


class SearchResult(BaseModel):
    """One normalized result returned by a :class:`SearchProvider`."""

    url: str
    title: str
    snippet: str


@runtime_checkable
class SearchProvider(Protocol):
    """A pluggable web-search backend (ADR-0002).

    Capabilities are declared on the interface itself so the Planner can
    filter and rank eligible providers without any provider-specific
    knowledge.
    """

    capabilities: ProviderCapabilities

    async def health(self) -> ProviderHealth:
        """Return this provider's current rolling health/latency/cost stats."""
        ...

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        """Run ``query`` against this provider and return normalized results."""
        ...


# ---------------------------------------------------------------------------
# Opportunity sources and ATS adapters.
# ---------------------------------------------------------------------------


@runtime_checkable
class OpportunitySource(Protocol):
    """A pluggable opportunity feed (YC, Hacker News, career pages, ...).

    ``fetch(since)`` is the whole contract: return opportunities discovered
    since ``since``, already normalized to :class:`Opportunity`. Any
    source-specific mechanics -- pagination, a lack of server-side ``since``
    filtering, HTML content fields -- are the source's private concern and
    must not leak into this signature. Adding a second source (Lever, Ashby)
    must not require changing this interface.
    """

    async def fetch(self, since: datetime) -> list[Opportunity]:
        """Return opportunities discovered since ``since``."""
        ...


@runtime_checkable
class HttpClient(Protocol):
    """A minimal async HTTP port so sources depend on an interface, not httpx.

    Kept deliberately tiny: sources need to GET or POST JSON. A real
    httpx-backed implementation lives in :mod:`career_agent.integrations.http`;
    tests inject a fake that replays recorded fixtures, so the suite never
    makes a network call.

    ``post_json`` was added in 4c slice-2 (additively -- existing ``get_json``
    callers are unaffected) because Exa's real search API is POST with a JSON
    body, not GET with query params; a GET-only port could not honestly reach
    it once the user runs this against the real service.
    """

    async def get_json(
        self, url: str, *, params: dict[str, str] | None = None
    ) -> object:
        """GET ``url`` and return the parsed JSON body."""
        ...

    async def post_json(
        self,
        url: str,
        *,
        json: dict[str, object],
        headers: dict[str, str] | None = None,
    ) -> object:
        """POST ``json`` to ``url`` and return the parsed JSON response body."""
        ...


@runtime_checkable
class OpportunityRepository(Protocol):
    """Idempotent store of discovered opportunities (dedup boundary).

    This is *the contract*; the Phase 4a in-memory implementation and the
    later SQLite implementation both satisfy exactly these two methods and no
    more, so the swap is a drop-in. ``add`` is the dedup primitive: it returns
    ``True`` when the opportunity was newly stored and ``False`` when its
    :attr:`Opportunity.id` was already present, so a caller emits a discovery
    event only for genuinely new opportunities.
    """

    async def add(self, opportunity: Opportunity) -> bool:
        """Store ``opportunity``; return whether it was newly added.

        Returns ``False`` (and does not overwrite) if the id was already
        present.
        """
        ...

    async def get(self, opportunity_id: str) -> Opportunity | None:
        """Return the stored opportunity with this id, or ``None``."""
        ...


@runtime_checkable
class HeldCandidateSink(Protocol):
    """Where a freeform source records candidates it held, not emitted (ADR-0013).

    An *additive, optional* collaborator: only extraction-type sources (Hacker
    News, later) need it. It imposes nothing on the structured sources and does
    not change ``OpportunitySource.fetch`` or the :class:`Opportunity` type --
    held candidates leave through this sink, never through ``fetch()``'s return
    value. Implementations may keep them in memory (tests) or publish a
    ``CandidateHeld`` event onto the bus (production visibility).
    """

    async def record(self, held: HeldCandidate) -> None:
        """Record a held candidate so the discard pile stays visible."""
        ...


@runtime_checkable
class ATSAdapter(Protocol):
    """A pluggable ATS integration (Greenhouse, Lever, Ashby, ...).

    ``submit`` takes :class:`~career_agent.domain.models.SubmittableApplication`,
    not a bare ``Application`` -- structurally, this method cannot be called
    with a resume the truthfulness gate has not approved (ADR-0018). Only the
    tiered ``Applicator`` implementation is expected to call this; it is not
    meant to be invoked directly by orchestration code, which is why it has
    no confirmation parameter of its own -- confirmation is obtained and
    checked one layer up, in ``Applicator.submit``, before an adapter is ever
    reached.
    """

    ats_kind: str

    async def fetch_postings(self, company: Company) -> list[Opportunity]:
        """Return ``company``'s current postings from this ATS."""
        ...

    async def submit(self, application: SubmittableApplication) -> Event:
        """Submit ``application`` directly through this ATS's API."""
        ...


@runtime_checkable
class EmailDraftSink(Protocol):
    """Creates a draft email -- and only a draft (ADR-0021).

    Deliberately has **no** ``send`` method. That is a scope restraint this
    project holds itself to, not a fact about the underlying email API --
    the real Gmail API can send mail; this Protocol simply never exposes
    that capability, so nothing in this codebase can call it without first
    widening the interface, a visible, reviewable change. Tier 3
    (``EmailApplicator``) can therefore never claim
    ``ApplicationSubmitted`` -- only a human, acting outside this system in
    their own email client, can actually send.
    """

    async def create_draft(self, *, to: str, subject: str, body: str) -> str:
        """Create a draft email; return an opaque id identifying it."""
        ...


# ---------------------------------------------------------------------------
# Applying (ADR-0010, ADR-0018) and truthfulness (ADR-0003).
# ---------------------------------------------------------------------------


@runtime_checkable
class Applicator(Protocol):
    """The single interface orchestration code uses to submit an application.

    Tier selection (direct ATS API / driven browser / email-to-apply) is an
    internal strategy this implementation chooses between -- callers never
    see three separate interfaces for the three tiers (ADR-0010).

    Split into ``prepare``/``submit`` rather than one ``apply`` call
    (ADR-0018): ``prepare`` performs no network I/O and cannot itself send
    anything; ``submit`` is the only method that can, and it requires a
    :class:`~career_agent.domain.models.HumanConfirmation` naming the exact
    :class:`~career_agent.domain.models.SubmissionPreview` being authorized,
    not a boolean flag that could default to "yes". There is no ``apply()``
    that bypasses this by calling both steps internally -- that would put the
    confirmation requirement back behind something callers could no longer
    see or skip.
    """

    async def prepare(self, application: SubmittableApplication) -> SubmissionPreview:
        """Assemble exactly what would be sent, performing no network I/O."""
        ...

    async def submit(
        self, preview: SubmissionPreview, confirmation: HumanConfirmation
    ) -> Event:
        """Send ``preview``, only if ``confirmation`` names that exact preview."""
        ...


@runtime_checkable
class ResumeGenerator(Protocol):
    """Tailors content into an unverified draft.

    Returns a :class:`~career_agent.domain.models.TailoredResumeDraft`, which
    deliberately has no :class:`TruthfulnessResult` attached -- a generator
    cannot approve its own output. See :class:`TruthfulnessGate`, a
    deliberately separate interface (ADR-0003).
    """

    async def tailor(
        self,
        opportunity: Opportunity,
        profile: MasterProfile,
        *,
        gap_report: AtsGapReport | None = None,
    ) -> TailoredResumeDraft:
        """Produce an unverified, structured draft for ``opportunity``.

        ``gap_report`` (Phase 10, ADR-0034) carries the ATS retailor loop's
        SURFACEABLE keywords only -- the type structurally cannot carry a
        keyword the profile has no evidence for, so a retailor request can
        never name a fabrication target (matrix case B1).
        """
        ...


@runtime_checkable
class ContentDrafter(Protocol):
    """The narrow LLM port behind the real :class:`ResumeGenerator` (ADR-0022).

    Scoped exactly like :class:`ClaimVerifier` was for the gate: a single,
    narrow capability (draft work/skill/project selections) rather than the
    general Haiku->Sonnet->Opus cascade client the architecture still
    describes as future work. Unlike ``ClaimVerifier``, this port is *not*
    permanently exempted from future cost-cascade routing -- a false-approve
    on tailoring is recoverable (the gate catches it downstream); a
    false-approve on verification is not, which is the actual reason
    ``ClaimVerifier`` earned its exemption, not something that transfers
    here by default.
    """

    prompt_version: str

    async def draft(
        self,
        opportunity: Opportunity,
        profile: MasterProfile,
        *,
        gap_report: AtsGapReport | None = None,
    ) -> DraftedTailoring:
        """Draft work/skill/project selections. Never asked for ``summary``.

        ``gap_report`` (ADR-0034): SURFACEABLE-only retailor targets; see
        :class:`ResumeGenerator.tailor`.
        """
        ...


@runtime_checkable
class SemanticKeywordMatcher(Protocol):
    """Advisory LLM port for the ATS gate's semantic layer (Phase 10, ADR-0034).

    Asked one question: "is this missing keyword genuinely present in the
    resume under different wording -- and if so, quote the exact supporting
    phrase?" Its claims are worthless until
    :func:`~career_agent.domain.ats_scoring.verified_semantic_keywords`
    confirms each quoted phrase exists verbatim in the resume text,
    deterministically (matrix case A3) -- and even a verified claim only
    prunes the retailor gap report; nothing this port produces can reach
    the gate's pass/fail decision (matrix case A1).

    Deliberately NOT cost-cascade-exempt, unlike ``ClaimVerifier``
    (ADR-0016): that exemption exists to protect judgments that *gate*
    something, where a cheaper model's false approval is unrecoverable.
    This port gates nothing -- its output is deterministically re-verified,
    and a wrong answer costs at most one wasted retailor suggestion --
    so the exemption's purpose does not apply (ADR-0034).
    """

    async def propose_matches(
        self, missing_keywords: list[str], resume_text: str
    ) -> list[SemanticKeywordClaim]:
        """Propose (keyword, quoted supporting phrase) pairs. May return []."""
        ...


@runtime_checkable
class TruthfulnessGate(Protocol):
    """Verifies a draft against the master profile and renders a verdict (ADR-0003).

    Kept separate from :class:`ResumeGenerator` on purpose: a generator has
    no method that can mark its own output verified. Orchestration code (the
    Resume Agent) calls generator, then gate, as two distinct steps, and only
    assembles a :class:`~career_agent.domain.models.TailoredResume` after the
    gate has run.
    """

    async def verify(
        self, draft: TailoredResumeDraft, profile: MasterProfile
    ) -> TruthfulnessResult:
        """Verify every statement in ``draft`` against ``profile``."""
        ...


class ClaimVerdict(BaseModel):
    """One :class:`ClaimVerifier` judgment on a single claim (ADR-0016).

    ``confidence`` is required, not optional -- a verdict of ``verified=True``
    said with low confidence must not be trusted the same as one said with
    high confidence (same discipline as ``Provenance.extraction_confidence``
    and ``HeldCandidate``, not invented a third way). The gate treats
    sub-threshold confidence as unverified regardless of ``verified``.
    """

    verified: bool
    confidence: float = Field(ge=0.0, le=1.0)
    category: (
        Literal[
            "skill_not_found",
            "evidence_missing",
            "employer_mismatch",
            "date_inconsistency",
            "metric_unsupported",
            "verification_failed",
        ]
        | None
    ) = None
    detail: str = ""
    matched_index: int | None = None


@runtime_checkable
class ClaimVerifier(Protocol):
    """Judges whether one claim is entailed by evidence text (ADR-0016).

    A narrow, purpose-built port -- not the general Claude cost-cascade client
    named in the project stack. The real implementation
    (:mod:`career_agent.llm.claim_verifier`) is free to eventually delegate to
    that cascade client once it exists, without this phase needing to build it
    first.

    This is the first place in the architecture where correctness rests on a
    model's judgment rather than a structural guarantee (a required field, an
    AST-checked import, an import-linter contract). ``verify_claim`` is
    permanently exempt from cost-down routing (ADR-0016): implementations must
    use the most capable model tier, never the cheap end of a cascade, because
    a false-approve here is catastrophic and a heuristic cannot safely
    distinguish honest rephrasing from fabrication in both directions at once.
    """

    #: Identifies the exact prompt/model configuration that produced verdicts
    #: from this instance, so every :class:`TruthfulnessResult` it contributes
    #: to is reproducible against the prompt that produced it.
    prompt_version: str

    async def verify_claim(self, statement_text: str, evidence: str) -> ClaimVerdict:
        """Judge whether ``statement_text`` is entailed by ``evidence``.

        Must raise on failure (timeout, API error, malformed response) rather
        than return a fabricated verdict -- the gate treats any exception as
        an explicit block, never a silent pass.
        """
        ...


@runtime_checkable
class NotificationSink(Protocol):
    """A pluggable notification channel.

    Notifications are a cross-cutting concern, not a first-class agent
    (ADR-0001) -- this interface is how a plugin hooks into that concern.
    """

    async def notify(self, event: Event) -> None:
        """Deliver ``event`` to this sink's channel."""
        ...
