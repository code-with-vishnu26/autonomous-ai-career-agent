"""Web résumé upload -> AI-analyzed review -> Master Profile (Phase 71, ADR-0089).

The web analogue of `career-agent import-cv` + `promote-cv` (Phase 26,
ADR-0052), reusing their exact fail-closed promotion boundary
(`domain/ingestion.py::promote`, `storage/cv_ingest.py::
apply_confirmed_promotions`) unmodified. Uploading a résumé never writes
the profile by itself: it only produces `UNVERIFIED` fact proposals for
the caller to review; only proposals the caller explicitly confirms here
are promoted, and only into fields with no existing different trusted
value.

Two-step flow, mirroring `prepare_actions`/`submission_actions`'s
background-task pattern in shape (though this work is synchronous --
parsing a résumé is fast, no LLM call, nothing to poll):

1. `POST /user/master-profile/import` (multipart) reads the uploaded file,
   extracts UNVERIFIED proposals, and caches the draft + the document's
   normalized text server-side under a token -- never trusting a client
   to hold or replay the source document's content on confirm.
2. `POST /user/master-profile/import/{token}/confirm` takes the caller's
   per-proposal confirm/reject decisions, re-validates each confirmed
   proposal's evidence against the *cached* document text (the same
   source-drift-adjacent check `promote-cv` does against a re-read file),
   and promotes only what passes into the caller's stored Master Profile.

Pending drafts live only in this process's memory (module-level dict, the
same reasoning `submission_actions`/`prepare_actions` already rely on:
each is tied to one upload, never needed after its confirm/expiry).
"""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel

from career_agent.api.dependencies import get_master_profile_store
from career_agent.api.security import get_current_user
from career_agent.domain.ingestion import TrustState
from career_agent.domain.models import MasterProfile
from career_agent.domain.user import User
from career_agent.storage.cv_ingest import (
    DocumentParseError,
    UnsupportedDocumentError,
    apply_confirmed_promotions,
    ingest_document_bytes,
    read_document_bytes,
)
from career_agent.storage.profile import ProfileValidationError

router = APIRouter(prefix="/user/master-profile/import", tags=["cv-import"])

_STALE_ENTRY_SECONDS = 3600.0
#: Basics fields BasicsSection requires -- if a resume produced neither
#: (no email regex match, no first-line-looks-like-a-name match), the
#: promoted profile still cannot be saved; named explicitly so the
#: response can say exactly what is missing rather than a generic error.
_REQUIRED_BASICS = ("name", "email")


class _PendingImport:
    def __init__(self, user_id: str, draft, document_text: str) -> None:  # noqa: ANN001
        self.user_id = user_id
        self.draft = draft
        self.document_text = document_text
        self.created_at = time.monotonic()


_pending: dict[str, _PendingImport] = {}


def _prune_stale_entries() -> None:
    cutoff = time.monotonic() - _STALE_ENTRY_SECONDS
    for token in [t for t, e in _pending.items() if e.created_at < cutoff]:
        del _pending[token]


class ProposalView(BaseModel):
    """One fact proposal, with a readable evidence snippet for the review UI."""

    proposal_id: str
    field_path: str
    proposed_value: str
    evidence_text: str
    conflict_ids: list[str]


class UploadResponse(BaseModel):
    """Body for ``POST /user/master-profile/import``."""

    token: str
    source_type: str
    proposals: list[ProposalView]


def _evidence_snippet(document_text: str, proposal) -> str:  # noqa: ANN001
    """The document text a proposal's first evidence span points at.

    Display-only -- promotion re-validates the real span against the
    cached document text independently (:func:`apply_confirmed_promotions`),
    so a snippet that failed to slice cleanly is not a security concern,
    only a slightly less helpful review UI.
    """
    if not proposal.evidence_spans:
        return proposal.proposed_value
    span = proposal.evidence_spans[0]
    return document_text[span.start_offset : span.end_offset]


@router.post("", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_resume(
    file: UploadFile, current_user: User = Depends(get_current_user)
) -> UploadResponse:
    """Parse an uploaded résumé into UNVERIFIED fact proposals for review.

    Never touches the Master Profile. Supported formats: PDF, DOCX, TXT,
    MD (the exact set :func:`~career_agent.storage.cv_ingest.
    read_document_bytes` supports); an unsupported extension or malformed
    document is refused with a clear 400, never a bare 500.
    """
    raw_bytes = await file.read()
    try:
        draft = ingest_document_bytes(file.filename or "resume", raw_bytes)
    except (UnsupportedDocumentError, DocumentParseError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    # The normalized document text isn't on the draft itself (only digests
    # and offsets are) -- re-derive it once here for evidence snippets and
    # for the confirm step's re-validation cache.
    _raw, document_text, _source_type = read_document_bytes(
        file.filename or "resume", raw_bytes
    )

    _prune_stale_entries()
    token = str(uuid.uuid4())
    _pending[token] = _PendingImport(current_user.id, draft, document_text)

    return UploadResponse(
        token=token,
        source_type=draft.source_type,
        proposals=[
            ProposalView(
                proposal_id=p.proposal_id,
                field_path=p.field_path,
                proposed_value=p.proposed_value,
                evidence_text=_evidence_snippet(document_text, p),
                conflict_ids=p.conflict_ids,
            )
            for p in draft.proposals
        ],
    )


class ProposalDecision(BaseModel):
    """One caller decision on one proposal."""

    proposal_id: str
    confirmed: bool


class ConfirmRequest(BaseModel):
    """Body for ``POST /user/master-profile/import/{token}/confirm``.

    A proposal not listed here is left ``UNVERIFIED`` -- ``promote()``'s
    ``NOT_CONFIRMED`` path, never silently trusted. There is no
    "confirm everything" default; every promoted fact was explicitly
    opted into by the caller.
    """

    decisions: list[ProposalDecision]


class ProposalOutcome(BaseModel):
    """One proposal's fail-closed promotion outcome (mirrors ProposalResult)."""

    proposal_id: str
    field_path: str
    proposed_value: str
    outcome: str
    reason: str


class ConfirmResponse(BaseModel):
    """Body for ``POST /user/master-profile/import/{token}/confirm``."""

    results: list[ProposalOutcome]
    profile_saved: bool
    missing_required_fields: list[str]
    profile: MasterProfile | None


@router.post("/{token}/confirm", response_model=ConfirmResponse)
def confirm_resume_import(
    token: str,
    body: ConfirmRequest,
    current_user: User = Depends(get_current_user),
    master_profile_store=Depends(get_master_profile_store),
) -> ConfirmResponse:
    """Promote the caller's confirmed proposals into their Master Profile.

    Reuses :func:`apply_confirmed_promotions` unmodified: a confirmed
    proposal is promoted only if its (server-recomputed) binding digest
    matches, its evidence re-validates against the cached document text,
    it has no unresolved conflict, and the target field currently holds no
    different trusted value -- exactly `promote-cv`'s fail-closed boundary,
    just reached over HTTP instead of a hand-edited draft file.
    """
    entry = _pending.get(token)
    if entry is None or entry.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import token not found (expired or never existed).",
        )

    decisions = {d.proposal_id: d.confirmed for d in body.decisions}
    decided_proposals = []
    for proposal in entry.draft.proposals:
        confirmed = decisions.get(proposal.proposal_id)
        if confirmed is True:
            decided_proposals.append(
                proposal.model_copy(update={"trust_state": TrustState.CONFIRMED})
            )
        elif confirmed is False:
            decided_proposals.append(
                proposal.model_copy(update={"trust_state": TrustState.REJECTED})
            )
        else:
            decided_proposals.append(proposal)  # left UNVERIFIED
    draft = entry.draft.model_copy(update={"proposals": decided_proposals})

    existing = master_profile_store.get(current_user.id)
    profile_raw = (
        existing.model_dump(mode="json", exclude={"version"})
        if existing is not None
        else {
            "basics": {},
            "work": [],
            "education": [],
            "skills": [],
            "projects": [],
            "legal_status": {},
        }
    )

    updated, results = apply_confirmed_promotions(
        draft, entry.document_text, profile_raw
    )
    # apply_confirmed_promotions builds its own PromotionConfirmation
    # internally, labelled confirmed_by="draft-file" (the CLI's label for a
    # hand-edited draft) -- reused as-is rather than forked, since the
    # fail-closed decision it produces is identical either way; only the
    # human-readable label would differ, and nothing here surfaces it.

    missing = [f for f in _REQUIRED_BASICS if not updated.get("basics", {}).get(f)]
    saved_profile: MasterProfile | None = None
    profile_saved = False
    if not missing:
        try:
            candidate = MasterProfile(version="pending", **updated)
            saved_profile = master_profile_store.save(current_user.id, candidate)
            profile_saved = True
        except ProfileValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Could not save the updated profile: {exc}",
            ) from exc

    return ConfirmResponse(
        results=[
            ProposalOutcome(
                proposal_id=r.proposal_id,
                field_path=r.field_path,
                proposed_value=r.proposed_value,
                outcome=r.outcome,
                reason=r.reason,
            )
            for r in results
        ],
        profile_saved=profile_saved,
        missing_required_fields=missing,
        profile=saved_profile,
    )
