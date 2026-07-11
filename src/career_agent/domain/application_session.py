"""``ApplicationSession``: a reviewable snapshot of prepared-but-unsubmitted work.

Phase 51's own goal states it exactly: prepare an application inside a
browser, then **stop before Submit**. This model is what "stop" produces --
the artifact handed to Phase 52's Human Review Center, mirroring how
``TailoredResume``/``Application`` (ADR-0011/ADR-0023) are what résumé
tailoring produces for a human to review before anything downstream acts on
it. Pure data, no I/O, no ``Page``/browser object anywhere on it -- fully
serializable, so it can be persisted (``storage/sqlite.py``) and later
re-displayed without a live browser session (Phase 52, future work).

``status`` never includes anything resembling "submitted" -- there is no
value here this model can hold that means an external submission happened.
That is a structural fact about this type, not merely a convention any
caller has to remember: :class:`ApplicationSession` has no field for a
submission confirmation/ID, and never will until a future phase's
Submission Engine (Phase 53) explicitly earns one, "only after explicit
approval" per this project's own standing roadmap commitment.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

#: - ``READY_FOR_REVIEW``: fields were filled/mapped as far as this engine
#:   safely can go; a human reviews before anything further happens.
#: - ``BLOCKED``: at least one required field has no describable text at
#:   all (mirrors ``UnsupportedFormFieldsError``'s hard-refuse case) --
#:   preparation could not honestly proceed past it.
#: - ``LOGIN_REQUIRED_TIMEOUT``: the human did not complete login within
#:   the allotted wait; preparation never reached the form at all.
#: - ``UNSUPPORTED_PROVIDER``: no ``FormFiller`` exists for this
#:   opportunity's platform yet (mirrors ``FeatureUnavailableError``).
ApplicationSessionStatus = Literal[
    "READY_FOR_REVIEW",
    "BLOCKED",
    "LOGIN_REQUIRED_TIMEOUT",
    "UNSUPPORTED_PROVIDER",
]


class ApplicationSession(BaseModel):
    """One preparation attempt's full, reviewable state. Never a submission."""

    id: str
    provider: str
    company: str
    job_title: str
    url: str
    opportunity_id: str
    status: ApplicationSessionStatus
    resume_variant_id: str | None = None
    cover_letter_body: str | None = None
    #: Selectors this run recognized and filled -- known identity/resume
    #: fields (``FormFiller.known_field_selectors``) plus any Category 2
    #: factual field auto-answered from an already-captured profile fact.
    filled_fields: list[str] = Field(default_factory=list)
    #: Every required selector on the live form this run found and had to
    #: reason about at all (``filled_fields`` + ``missing_fields``).
    detected_fields: list[str] = Field(default_factory=list)
    #: Real files actually attached via Playwright ``set_input_files``
    #: (e.g. Lever's DOCX résumé upload) -- never a guessed/blind upload.
    uploaded_files: list[str] = Field(default_factory=list)
    #: Required fields this run could not safely answer -- a human must
    #: fill these directly, the same "never guess" discipline
    #: ``BrowserApplicator``'s Phase A manifest already applies.
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime
