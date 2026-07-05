"""Per-``ats_kind`` form-filling strategies for ``BrowserApplicator`` (ADR-0028/0029).

A :class:`FormFiller` knows how to fill *identity and resume* fields for
exactly one ATS platform's public apply form, and declares
``known_field_selectors`` -- the exact set of fields it fills and nothing
else -- plus, since ADR-0029, ``challenge_selector`` and ``submit_selector``:
the platform's own real markup for a verification challenge and the
clickable submit action. ``BrowserApplicator`` used to hardcode
``#verification-challenge``/``#submit_app`` (Greenhouse's own fixture
markers) directly; those are now declared per platform, because a real,
live Lever posting confirmed real hCaptcha markup (``div#h-captcha``, a
hidden submit button) that the old hardcoded values would never have
matched at all.

``known_field_selectors`` entries are arbitrary CSS selectors, not assumed
to be ``#id`` shapes -- the same real Lever posting confirmed its identity
fields have no ``id`` attribute at all, only ``name`` (e.g. ``name="email"``,
selectable as ``[name='email']``). ``BrowserApplicator``'s
``_unhandled_required_fields`` derives a field's real selector from
whichever attribute it actually has (``id`` first, then ``name``), so this
declaration style works for both shapes.

Only Greenhouse has a real, working implementation. **Lever's and Ashby's
field-level DOM selectors could not be verified before this slice was
built** -- two independent verification attempts (this codebase's own
sandbox, whose Playwright cannot reach arbitrary internet hosts at all; and
a separate attempt against live postings, which could reach documentation
but not rendered page DOM) both hit a real wall, not a shortcut taken.
Lever's own documentation confirms the form is genuinely
organization-configurable ("Full Name" and "Email" are the only two fields
guaranteed present on every posting), which argues against a plausible-but-
unverified static selector map more strongly than mere uncertainty would.
``LeverFormFiller``/``AshbyFormFiller`` are therefore explicit stubs that
raise :class:`FormFillerNotImplementedError` rather than fill anything --
a real human needs to inspect a handful of real live postings on each
platform and report back the actual field selectors before these can be
built for real. Lever's resume field in particular is confirmed to need
more than a selector: it's a collapsed ``<li class="application-question
resume">`` with a ``resumeStorageId`` hidden field, strongly suggesting a
JS-driven file-upload widget rather than Greenhouse's plain textarea --
this project has no resume *file* artifact anywhere in its domain model
(``SubmittableApplication`` only ever carries ``rendered_text``), so
``LeverFormFiller`` stays a stub until that's confirmed one way or the
other, not just until selectors are known.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from career_agent.domain.models import SubmittableApplication

if TYPE_CHECKING:
    from playwright.async_api import Page


class FormFillerNotImplementedError(Exception):
    """This platform's real form selectors have not been verified yet.

    Raised instead of guessing at selectors that were never confirmed
    against a real, live posting -- the same "don't build on an unverified
    assumption" discipline that killed the Tier 1 direct-API premise
    (ADR-0027), now applied to browser-tier selectors.
    """


@runtime_checkable
class FormFiller(Protocol):
    """Fills exactly the identity/resume fields it knows, and declares them.

    ``known_field_selectors`` is what lets ``BrowserApplicator`` detect any
    *other* required field a real posting's form has and refuse rather than
    silently ignore or guess at it -- the declaration is the safety
    mechanism, not just documentation. Entries are arbitrary CSS selectors
    (``#id`` or ``[name='...']``), matching whichever attribute a given
    platform's real form actually uses.

    ``challenge_selector``/``submit_selector`` (ADR-0029) are this
    platform's own real markup for a verification challenge and the
    clickable submit action -- previously hardcoded directly in
    ``BrowserApplicator`` to Greenhouse's own fixture markers, which would
    never have matched a real platform's different markup (confirmed by a
    real Lever posting's hCaptcha widget).
    """

    ats_kind: str
    known_field_selectors: frozenset[str]
    challenge_selector: str
    submit_selector: str

    async def fill_identity_and_resume(
        self, page: Page, application: SubmittableApplication
    ) -> None:
        """Fill this platform's identity and resume fields on the live page."""
        ...


class GreenhouseFormFiller:
    """The one real, working :class:`FormFiller` (ADR-0020, ADR-0028).

    Moved here from ``BrowserApplicator`` without behavior change -- same
    selectors, same ``_split_name`` heuristic, same known-imprecise-stopgap
    documentation.
    """

    ats_kind = "greenhouse"
    known_field_selectors = frozenset(
        {"#first_name", "#last_name", "#email", "#resume_text"}
    )
    challenge_selector = "#verification-challenge"
    submit_selector = "#submit_app"

    async def fill_identity_and_resume(
        self, page: Page, application: SubmittableApplication
    ) -> None:
        """Fill Greenhouse's identity/resume fields from ``application``."""
        applicant = application.application.applicant
        first_name, last_name = _split_name(applicant.name)
        summary = application.application.resume.content.summary
        await page.fill("#first_name", first_name)
        await page.fill("#last_name", last_name)
        await page.fill("#email", applicant.email)
        await page.fill("#resume_text", summary)


class MissingResumeArtifactError(Exception):
    """Lever's resume field is a required file upload, and there is no file.

    Raised before anything is filled (Phase 11, ADR-0035): Lever has no
    manual-text path at all, so an application whose ``TailoredResume``
    carries no DOCX :class:`~career_agent.domain.models.ResumeArtifact`
    (or whose recorded artifact file no longer exists on disk) cannot be
    submitted honestly through this platform. Typed and named -- the fix
    is "generate the resume files (Phase 9's ``artifacts_dir``)", which
    this message says plainly, never a silent skip of a required upload.
    """


class LeverFormFiller:
    """The real Lever filler (Phase 11, ADR-0035), built on ADR-0029's evidence.

    Every selector here comes from the recorded human dev-tools inspection
    of a live jobs.lever.co posting (ADR-0029): identity fields have no
    ``id``, only ``name``; the name field is a **single** full-name input
    (never split -- the opposite of Greenhouse's first/last pair, and one
    less place for the ``_split_name`` heuristic's known imprecision to
    leak); the resume is a **required file upload** with no manual-text
    alternative, satisfied by attaching Phase 9's canonical DOCX artifact
    via Playwright ``set_input_files``; the challenge is real hCaptcha
    markup (``#h-captcha``), handled by the existing pause/resume
    machinery -- a human solves it, never this project (no solving
    services, ever). Live validation against a real posting on the user's
    machine remains the final check before a real submission, per the
    standing offline-fixture-first discipline.
    """

    ats_kind = "lever"
    known_field_selectors = frozenset(
        {"[name='name']", "[name='email']", "[name='resume']"}
    )
    challenge_selector = "#h-captcha"
    submit_selector = "#btn-submit"

    async def fill_identity_and_resume(
        self, page: Page, application: SubmittableApplication
    ) -> None:
        """Fill Lever's identity fields and attach the real resume file.

        Raises :class:`MissingResumeArtifactError` before touching the page
        if the application carries no DOCX artifact or the file is gone
        from disk -- a required upload with nothing to upload is a
        precondition failure the human must fix, not something to submit
        around.
        """
        app = application.application
        docx = next(
            (
                artifact
                for artifact in app.resume.artifacts
                if artifact.format == "docx"
            ),
            None,
        )
        if docx is None:
            raise MissingResumeArtifactError(
                f"application {app.id!r} carries no DOCX resume artifact -- "
                f"Lever's resume field is a required file upload with no "
                f"manual-text path. Run the pipeline with artifacts_dir set "
                f"(Phase 9, ADR-0033) so a real file exists to attach."
            )
        docx_path = Path(docx.path)
        if not docx_path.exists():
            raise MissingResumeArtifactError(
                f"resume artifact {docx.path!r} (recorded for application "
                f"{app.id!r}) no longer exists on disk -- regenerate the "
                f"resume files before submitting through Lever."
            )
        await page.fill("[name='name']", app.applicant.name)
        await page.fill("[name='email']", app.applicant.email)
        await page.set_input_files("[name='resume']", str(docx_path))


class AshbyFormFiller:
    """Stub -- Ashby's real form selectors are not yet verified (ADR-0028).

    Ashby's application forms are per-company-configurable, with fields
    identified by an internal ``path`` rather than a stable public DOM
    contract, plus optional separate EEOC survey forms. Same "verify before
    building" refusal as :class:`LeverFormFiller`.
    """

    ats_kind = "ashby"
    known_field_selectors = frozenset()
    # Left empty rather than guessed -- see LeverFormFiller's comment.
    challenge_selector = ""
    submit_selector = ""

    async def fill_identity_and_resume(
        self, page: Page, application: SubmittableApplication
    ) -> None:
        """Always raises -- Ashby's real selectors are not yet verified."""
        raise FormFillerNotImplementedError(
            "Ashby's real form field selectors have not been verified "
            "against a live posting -- see ADR-0028. Inspect a handful of "
            "real jobs.ashbyhq.com postings and update this class before "
            "using it for a real submission."
        )


def default_form_fillers() -> dict[str, FormFiller]:
    """The real registry a composition root wires up: one entry per ATS kind.

    Lever/Ashby are included -- so ``BrowserApplicator`` can raise a clear
    :class:`FormFillerNotImplementedError` naming the actual gap for those
    platforms -- rather than omitted, which would instead raise the less
    informative "no adapter registered at all" error a genuinely unknown
    ATS kind gets.
    """
    return {
        "greenhouse": GreenhouseFormFiller(),
        "lever": LeverFormFiller(),
        "ashby": AshbyFormFiller(),
    }


def _split_name(name: str) -> tuple[str, str]:
    """Split one JSON-Resume ``basics.name`` into Greenhouse's first/last fields.

    A **known-imprecise stopgap, not an assumed-correct split** (ADR-0027):
    the last whitespace-separated token becomes ``last_name``, everything
    before it becomes ``first_name``; a single-token name puts that token in
    ``first_name`` with an empty ``last_name``. It gets multi-part surnames
    ("van der Berg"), suffixes ("Jr.", "III"), and non-Western name orders
    wrong. Solving this properly needs per-field human confirmation before a
    real submission, not a smarter heuristic -- that is named, deferred
    future work (ADR-0027), not something silently left for later.
    """
    parts = name.rsplit(" ", 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]
