"""Domain models for the Autonomous AI Career Agent.

Pure data and validation rules only. No I/O, no framework or SDK imports
beyond Pydantic and the standard library. See ADR-0006 (JSON Resume master
profile), ADR-0003 (truthfulness gate), and ADR-0011 (structured tailored
content) for the decisions these models encode.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Master profile (ADR-0006): JSON-Resume-shaped, immutable per version.
# ---------------------------------------------------------------------------


class BasicsSection(BaseModel):
    """The JSON Resume "basics" section: identity and contact facts."""

    name: str
    email: str
    phone: str | None = None
    summary: str | None = None
    location: str | None = None


class SkillEntry(BaseModel):
    """A single skill claim.

    ``id`` is assigned once when the entry is created and never reused, even
    if the entry is later deleted -- this is what keeps evidence pointers
    from silently reattaching to an unrelated entry.
    """

    id: str
    name: str
    level: str | None = None
    keywords: list[str] = Field(default_factory=list)


class WorkEntry(BaseModel):
    """A single employment claim. ``id`` is assigned once and never reused."""

    id: str
    name: str
    position: str
    start_date: date
    end_date: date | None = None
    highlights: list[str] = Field(default_factory=list)


class EducationEntry(BaseModel):
    """A single education claim. ``id`` is assigned once and never reused."""

    id: str
    institution: str
    area: str | None = None
    study_type: str | None = None
    start_date: date | None = None
    end_date: date | None = None


class ProjectEntry(BaseModel):
    """A single project claim. ``id`` is assigned once and never reused."""

    id: str
    name: str
    description: str | None = None
    highlights: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class LegalStatusSection(BaseModel):
    """User-confirmed facts needed to answer common eligibility questions.

    Each field is ``None`` **only** to mean "not yet captured" -- never as
    an implicit "no." Structurally distinct from a false answer on purpose:
    if ``bool = False`` were the default, an uncaptured fact would silently
    *answer* a real legal-status question the moment anything touched this
    field before a human had ever been asked -- a materially worse failure
    than any resume-tailoring fabrication, because this is a legal
    representation made to a real employer, not a resume claim. Any code
    that needs one of these facts and finds ``None`` must trigger an
    explicit capture flow (the same "cannot proceed without this, ask the
    human" shape as :class:`~career_agent.agents.resume.generator.
    MissingSummaryError`), never infer, never default.

    Deliberately narrow -- exactly the fields real, observed application
    questions have needed so far, not a general "arbitrary future facts"
    mechanism. The same discipline this project has applied everywhere a
    speculative generalization was tempting (``resolve_ats_kind`` over a
    ``CompanyRepository``, the flat ``Settings`` object, ``load_master_
    profile`` as a plain function): solve the concrete case, generalize
    later only if real additional cases actually appear.
    """

    work_authorized_us: bool | None = None
    requires_sponsorship: bool | None = None


class MasterProfile(BaseModel):
    """The single source of truth for every applicant-facing claim (ADR-0006).

    ``version`` is a content hash of the full document. Saving an edit never
    mutates an existing version in place; it produces a new one. This is what
    lets a stored :class:`EvidenceRef` name an exact, frozen snapshot that
    stays correct forever for that snapshot, independent of later edits --
    "was this true when submitted" and "is this still true now" become two
    separately answerable questions instead of one that silently rots.
    """

    version: str
    basics: BasicsSection
    work: list[WorkEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    skills: list[SkillEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    legal_status: LegalStatusSection = Field(default_factory=LegalStatusSection)


# ---------------------------------------------------------------------------
# Truthfulness gate (ADR-0003): per-statement evidence, confidence, explainability.
# ---------------------------------------------------------------------------


class EvidenceRef(BaseModel):
    """A pointer into one exact, immutable :class:`MasterProfile` snapshot.

    Binds to a stable ``entry_id`` (never an array position) within a named
    ``profile_version``, so edits to the profile can never silently shift
    what a stored evidence pointer means. ``field`` names the entry-scoped
    attribute (e.g. ``"highlights"``, ``"level"``, ``"position"``); ``index``
    is the list position within that field when it is list-valued. Both are
    stored as their own typed values rather than combined into one string, so
    resolving an EvidenceRef to display an excerpt never requires parsing a
    string in the explainability hot path.
    """

    profile_version: str
    section: Literal["basics", "work", "education", "skills", "projects"]
    entry_id: str | None = None  # None only for "basics" (a singleton section)
    field: str
    index: int | None = None
    excerpt: str


class Statement(BaseModel):
    """One atomic claim extracted from generated content, with its grounding."""

    text: str
    evidence: EvidenceRef | None
    confidence: float = Field(ge=0.0, le=1.0)
    verified: bool


class RejectionReason(BaseModel):
    """Why one statement failed the truthfulness gate (ADR-0003 explainability)."""

    statement_text: str
    category: Literal[
        "skill_not_found",
        "evidence_missing",
        "employer_mismatch",
        "date_inconsistency",
        "metric_unsupported",
        # Infrastructure failure (verifier timeout/error/malformed response),
        # NOT a content judgment -- kept as its own category (ADR-0016) rather
        # than overloading a content category, because "we couldn't check" is
        # not the same claim as "we checked and it's unsupported."
        "verification_failed",
    ]
    detail: str


class TruthfulnessResult(BaseModel):
    """The gate's verdict on a piece of generated content.

    ``profile_version`` must equal the ``profile_version`` of the
    :class:`TailoredResumeDraft` this result was computed for -- enforced by
    the gate implementation (Phase 5/7), not merely carried as data.
    Re-verifying an application later against a newer profile produces a new
    TruthfulnessResult; it never mutates a stored one.

    ``prompt_version`` is required (ADR-0016): the exact prompt that produced
    this verdict is part of the verdict's identity, not an afterthought -- a
    verdict must always be reproducible against the prompt that produced it,
    and re-verification with a changed prompt is expected to be able to
    diverge from the original (recorded, not a surprise).
    """

    profile_version: str
    approved: bool
    statements: list[Statement]
    rejections: list[RejectionReason] = Field(default_factory=list)
    prompt_version: str


# ---------------------------------------------------------------------------
# Opportunities.
# ---------------------------------------------------------------------------


class Company(BaseModel):
    """An employer a discovered :class:`Opportunity` belongs to."""

    id: str
    name: str
    domain: str | None = None
    career_page_url: str | None = None
    ats_kind: (
        Literal["greenhouse", "lever", "ashby", "workday", "unknown"] | None
    ) = None


class Provenance(BaseModel):
    """How an opportunity was derived, and how confidently (ADR-0012).

    Populated by *every* source, not just freeform ones. Structured sources
    (ATS APIs, the YC feed) set ``method="structured_api"``/``"structured_feed"``
    and ``extraction_confidence=1.0`` -- the source *is* the ground truth.
    Freeform sources that parse prose (Hacker News "Who's Hiring", later) set
    ``method="text_extraction"`` and a real confidence ``< 1.0``, giving the
    firehose an honest way to say "I'm not sure this is a real posting" instead
    of emitting a confident guess into the truthfulness-gated apply path.

    ``extraction_confidence`` lives here, not on :class:`Opportunity`, on
    purpose: confidence is a property of *how the opportunity was derived*, not
    of the opportunity itself, so keeping it beside ``method`` stops a reader
    from thresholding on the number without the extraction method right next to
    it (a 0.4 heuristic guess and a 1.0 API fact are not comparable numbers).
    """

    method: Literal["structured_api", "structured_feed", "text_extraction"]
    #: Stable pointer to the *raw* source item that was parsed -- distinct from
    #: ``Opportunity.source_url`` (the human apply/view page). For an ATS this is
    #: the API item; for a Hacker News post it is the comment permalink, which is
    #: not the apply link buried in the post's prose. It is the audit trail back
    #: to exactly what was read, which is what makes a low-confidence extraction
    #: reviewable later.
    reference: str
    extraction_confidence: float = Field(ge=0.0, le=1.0)


class Opportunity(BaseModel):
    """A discovered job posting, normalized across every discovery source."""

    id: str
    company_id: str
    #: A cross-source canonical employer identity (ADR-0014), computed by the
    #: source (a domain where available, else a normalized company name), so the
    #: repository can dedup the same job across sources by fingerprint. Required:
    #: a source cannot emit an opportunity without declaring one.
    canonical_company: str
    title: str
    source: Literal["ats_api", "yc", "hn", "career_page", "web_search"]
    source_url: str
    provenance: Provenance  # required (ADR-0012): every source must populate it
    ats_ref: str | None = None
    posted_at: datetime | None = None
    location: str | None = None
    remote: bool | None = None
    description_raw: str
    discovered_at: datetime


class HeldCandidate(BaseModel):
    """A candidate a freeform source looked at but did not emit (ADR-0013).

    It is its own type, not a low-confidence ``Opportunity``, on purpose: a
    reply, a "seeking work" post, or vague prose is not a job we are merely
    unsure about -- it is often not a job at all. Demoting it to a
    low-confidence ``Opportunity`` would corrupt the meaning of that type
    (which must always mean "a job we vouch is real") and hand the downstream
    truthfulness gate things that were never postings. Same discipline as
    ``TailoredResumeDraft`` vs ``TailoredResume``: model the uncertain thing as
    its own type rather than a nullable field on the certain one.

    Held candidates are recorded (never silently dropped) so the discard pile
    is visible and auditable -- a human or the Learning engine can later see
    "HN held N comments this run, and why", with ``reference`` pointing back to
    the exact raw item and ``extraction_confidence`` carrying its sub-threshold
    score (the ADR-0012 channel).
    """

    source: Literal["hn", "career_page", "web_search"]
    reason: Literal[
        "below_threshold",  # looked like a posting but a required field failed
        "not_a_posting",  # a reply, a question, or meta noise
        "seeking_work",  # a candidate advertising themselves, not a job
        "ambiguous_parse",  # job-adjacent prose with no parseable structure
    ]
    reference: str  # pointer to the raw item held (e.g. an HN comment permalink)
    raw_excerpt: str
    extraction_confidence: float = Field(ge=0.0, le=1.0)
    held_at: datetime


# ---------------------------------------------------------------------------
# Tailored content (ADR-0011): structured, not free text.
# ---------------------------------------------------------------------------


class TailoredWorkEntry(BaseModel):
    """One tailored employment entry, traceable back to its source claim."""

    source_entry_id: str  # MasterProfile.work[].id this entry was built from
    position: str
    highlights: list[str]  # each highlight is one Statement the gate verifies


class TailoredProjectEntry(BaseModel):
    """One tailored project entry, traceable back to its source claim."""

    source_entry_id: str  # MasterProfile.projects[].id this entry was built from
    name: str
    highlights: list[str]


class TailoredContent(BaseModel):
    """A tailored resume's content, JSON-Resume-shaped rather than free text.

    Structure (not prose) is what lets the truthfulness gate verify each
    highlight as one atomic :class:`Statement` without re-parsing text, and
    lets a future diff viewer compare against :class:`MasterProfile`
    section-by-section instead of diffing noisy prose. Rendering this to
    plain text, a PDF, or ATS form fields is a downstream renderer's job, not
    this model's (ADR-0011).
    """

    summary: str
    work: list[TailoredWorkEntry] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    projects: list[TailoredProjectEntry] = Field(default_factory=list)


class DraftedTailoring(BaseModel):
    """What an LLM-backed :class:`ContentDrafter` is allowed to produce (ADR-0022).

    Deliberately has **no** ``summary`` field -- the same "impossible to
    construct otherwise" move as ``TailoredWorkEntry`` having no date fields
    (ADR-0016's Case #6 correction). `summary` is sourced read-only from
    ``MasterProfile.basics.summary`` by the orchestrating
    ``LLMResumeGenerator``, never drafted by the LLM; this type structurally
    cannot carry one, so there is no path for a drafter implementation to
    slip invented summary prose into a draft even by mistake.
    """

    work: list[TailoredWorkEntry] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    projects: list[TailoredProjectEntry] = Field(default_factory=list)


class TailoredResumeDraft(BaseModel):
    """The Resume Agent's generator output, before verification.

    Deliberately has no :class:`TruthfulnessResult` attached -- a generator
    cannot approve its own output (ADR-0003). A draft only becomes a
    :class:`TailoredResume` after :class:`~career_agent.core.interfaces.
    TruthfulnessGate` has verified it.
    """

    opportunity_id: str
    profile_version: str
    content: TailoredContent


class ResumeArtifact(BaseModel):
    """A generated resume file on disk, traceable to the content it renders.

    The first non-text artifact in this project (Phase 9, ADR-0033): a
    binary file is opaque, so its link back to the gated content that
    produced it must be carried as data, not inferred. ``resume_id`` +
    ``profile_version`` name the exact :class:`TailoredResume` snapshot;
    ``content_hash`` (sha256 of the file bytes) is embedded in the
    filename, so a regenerated file after any content change gets a new
    name by construction -- an existing artifact is never silently
    overwritten, the same never-mutate-in-place discipline as
    ``MasterProfile.version``.
    """

    resume_id: str
    profile_version: str
    format: Literal["docx", "pdf"]
    path: str
    content_hash: str


class TailoredResume(BaseModel):
    """A tailored resume together with the gate's verdict on it.

    Always carries its :class:`TruthfulnessResult`, including when
    ``truthfulness.approved`` is ``False`` -- a rejected attempt is still kept
    for audit/explainability. Callers that submit applications (ADR-0010)
    must check ``truthfulness.approved`` themselves; this model does not
    enforce it.

    ``artifacts`` (Phase 9, ADR-0033) is a derived cache with the same
    status as ``rendered_text``: populated by ``ResumeTailoringPipeline``
    for approved drafts only, never the source of truth (the gated
    ``content`` is), and how a downstream applicator reaches a real file
    path without gaining any profile or renderer dependency of its own.
    """

    id: str
    opportunity_id: str
    profile_version: str
    content: TailoredContent
    rendered_text: str | None = None  # derived cache; never the source of truth
    artifacts: list[ResumeArtifact] = Field(default_factory=list)  # same status
    truthfulness: TruthfulnessResult


# ---------------------------------------------------------------------------
# Applications and outcomes.
# ---------------------------------------------------------------------------


class Application(BaseModel):
    """One submission attempt, tracked through the tiered applicator (ADR-0010).

    Constructible with a resume the gate rejected -- Phase 5's audit
    commitment keeps a blocked attempt visible, it does not forbid recording
    it. That is exactly why ``Application`` alone must never be the type
    ``Applicator``/``ATSAdapter`` submission methods accept: see
    :class:`SubmittableApplication`.

    ``status="paused_for_human"`` is not one uniform kind of "waiting"
    (ADR-0021). A browser-tier CAPTCHA/verification pause (ADR-0020) is
    *temporarily* blocked and genuinely resumable -- the live session is
    held open and ``BrowserApplicator.resume()`` can advance it once the
    human clears the challenge. An email-tier pause (ADR-0021) is
    *permanently* outside this system's reach: a draft was created and
    nothing further can be automated -- there is no ``resume()`` for the
    email tier at all, because sending is a capability this project
    deliberately never gives itself (``EmailDraftSink`` has no ``send``
    method). A future dashboard or notification surfacing
    ``paused_for_human`` applications as one list must not imply a uniform
    "resume" action is available for all of them.

    ``status="rejected"`` (ADR-0023) is deliberately distinct from
    ``"failed"``. ``"failed"`` means a submission attempt was made through a
    tier and did not succeed -- a real-world event, potentially worth
    retrying via a different tier. ``"rejected"`` means the truthfulness
    gate blocked the resume before any submission was ever attempted -- a
    content problem, where retrying via a different tier accomplishes
    nothing until the resume itself is fixed. Collapsing these into one
    status would force every future consumer (a dashboard, a retry policy,
    the Learning engine) to re-derive the distinction by also inspecting
    ``resume.truthfulness.approved`` -- exactly the kind of
    should-be-structural distinction this project has refused to leave to
    inference everywhere else.

    ``applicant`` (Phase 8f, ADR-0027) is a **frozen snapshot** of
    ``MasterProfile.basics`` at the moment this ``Application`` was built --
    not a live pointer resolved again at submission time. This is the same
    "was this true when submitted" discipline ``TailoredResume.profile_version``
    already applies to resume content, now extended to identity: a
    live lookup at ``Applicator.submit()`` time would let a profile edit
    between ``prepare()`` and ``submit()`` silently submit a name/email that
    disagrees with the content that was actually gated and rendered --
    submitted identity and submitted content coming from two different
    moments in time, with nothing to flag the mismatch. Freezing both
    together here closes that gap. Required, not optional-with-a-default,
    for the same "impossible to construct otherwise" reason
    ``canonical_company``/``provenance`` are required elsewhere in this
    codebase: nothing should be able to build a real ``Application`` with no
    identity and have that go unnoticed until a real external form tries to
    fill blank fields.

    ``legal_status`` (Phase 8k, ADR-0032) is the same kind of frozen
    snapshot as ``applicant`` -- ``MasterProfile.legal_status`` captured
    once at pipeline-construction time, one field wider on the same
    precedent, not a new decision. It exists so
    :class:`~career_agent.agents.apply.browser_applicator.BrowserApplicator`
    can auto-fill a Category 2 (:mod:`~career_agent.agents.apply.
    question_answerer`) factual question it already has a captured fact
    for, without ever gaining a dependency on ``MasterProfile`` storage
    itself -- it only ever receives this pre-frozen section as data, the
    same way it has always received ``applicant``. The section itself is
    required (always present, even before any fact within it has been
    captured); its own fields may individually be ``None`` per
    :class:`LegalStatusSection`'s own "not yet captured" discipline.
    """

    id: str
    opportunity_id: str
    resume: TailoredResume
    applicant: BasicsSection
    legal_status: LegalStatusSection
    tier_used: Literal["ats_api", "browser", "email"] | None = None
    status: Literal["pending", "paused_for_human", "submitted", "failed", "rejected"]
    submitted_at: datetime | None = None


# ---------------------------------------------------------------------------
# Submission safety (ADR-0018): structural approval + confirmation binding.
# ---------------------------------------------------------------------------


class SubmittableApplication(BaseModel):
    """An :class:`Application` whose resume has passed the truthfulness gate.

    The only shape ``Applicator``/``ATSAdapter`` submission methods accept
    (``core/interfaces.py``). Enforced by a model validator, not by a
    designated factory function -- ``SubmittableApplication(application=...)``
    raises on an unapproved resume exactly as ``to_submittable()`` does,
    because it *is* the same call underneath. There is no construction path
    that skips the check. This is the same "impossible to construct
    otherwise" discipline as ``TailoredResumeDraft`` vs ``TailoredResume``,
    applied one step further downstream, to submission rather than tailoring.
    """

    application: Application

    @model_validator(mode="after")
    def _require_approved_resume(self) -> SubmittableApplication:
        truthfulness = self.application.resume.truthfulness
        if not truthfulness.approved:
            raise ValueError(
                "SubmittableApplication requires an Application whose "
                "resume.truthfulness.approved is True; got "
                f"{len(truthfulness.rejections)} unresolved rejection(s) for "
                f"application {self.application.id!r}."
            )
        return self


def to_submittable(application: Application) -> SubmittableApplication:
    """Named entry point for readability at call sites.

    Not the *only* thing enforcing the approval check -- the model validator
    on :class:`SubmittableApplication` does that regardless of how the type
    is constructed. This function exists so callers read "make this
    submittable" rather than a bare, unexplained model construction.
    """
    return SubmittableApplication(application=application)


class SubmissionPreview(BaseModel):
    """Exactly what one submission attempt would send, no network I/O yet.

    Produced by ``Applicator.prepare()``. ``preview_token`` is generated
    fresh per call and must be echoed back,
    unmodified, inside the :class:`HumanConfirmation` that authorizes sending
    it -- binding a confirmation to *this exact* preview, not "a submission"
    in general. ``Applicator.submit()`` rejects any mismatch (ADR-0018).
    """

    application_id: str
    tier: Literal["ats_api", "browser", "email"]
    target: str
    rendered_content: str
    preview_token: str


class HumanConfirmation(BaseModel):
    """A human's explicit, specific authorization to send one preview.

    Names the exact :class:`SubmissionPreview` it authorizes.
    ``preview_token`` must equal the preview being submitted exactly; a
    confirmation is not a boolean flag an orchestration step can default to
    "yes" -- it names which preview, who confirmed it, and when (ADR-0018).
    """

    preview_token: str
    confirmed_by: str
    confirmed_at: datetime


class PauseAcknowledgment(BaseModel):
    """A human's acknowledgment that a mid-submission challenge is cleared.

    Covers CAPTCHA, verification, or a login wall for one specific paused
    browser session (ADR-0020). Mirrors :class:`HumanConfirmation`'s shape
    deliberately -- ``pause_token`` names the exact pause being cleared, not
    a boolean a caller could satisfy for the wrong session.
    ``BrowserApplicator.resume()`` rejects any mismatch, and re-checks the
    challenge is actually gone rather than trusting the acknowledgment alone.
    """

    pause_token: str
    confirmed_by: str
    confirmed_at: datetime


#: Funnel ordering for outcome stages (ADR-0009). Not an exclusivity rule: an
#: application can accumulate several :class:`Outcome` rows over its lifetime
#: (e.g. viewed, then interview, then rejection). ``"rejection"`` is
#: deliberately out-of-band (``-1``) since it can terminate the funnel from
#: any earlier stage, not only the end. The Learning Agent (Phase 8) must read
#: an application's *full* Outcome history to know which stage a rejection
#: terminated -- rejected after an interview is a very different signal from
#: rejected at screening, and that distinction is lost if only the latest row
#: is read.
FUNNEL_ORDER: dict[str, int] = {
    "viewed": 0,
    "response": 1,
    "interview": 2,
    "offer": 3,
    "rejection": -1,
}


class Outcome(BaseModel):
    """One recorded event in an application's lifecycle (ADR-0009).

    Outcomes are additive: multiple rows may exist for the same
    ``application_id``, representing progression through (or exit from) the
    funnel in :data:`FUNNEL_ORDER`. Never treat the latest row as the whole
    history.
    """

    application_id: str
    kind: Literal["viewed", "response", "rejection", "interview", "offer"]
    occurred_at: datetime
    detail: str | None = None
