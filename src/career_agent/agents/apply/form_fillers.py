"""Per-``ats_kind`` form-filling strategies for ``BrowserApplicator`` (ADR-0028).

A :class:`FormFiller` knows how to fill *identity and resume* fields for
exactly one ATS platform's public apply form, and declares
``known_field_selectors`` -- the exact set of fields it fills and nothing
else. ``BrowserApplicator`` uses that declaration to detect any *other*
required field a real posting's form has (a custom question, an EEOC/
demographic question, anything else) and refuse rather than guess at it
(:class:`~career_agent.agents.apply.browser_applicator.UnsupportedFormFieldsError`).

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
built for real.
"""

from __future__ import annotations

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
    mechanism, not just documentation.
    """

    ats_kind: str
    known_field_selectors: frozenset[str]

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


class LeverFormFiller:
    """Stub -- Lever's real form selectors are not yet verified (ADR-0028).

    Lever's own documentation confirms "Full Name" and "Email" are the only
    two fields guaranteed present; everything else (phone, location,
    pronouns, resume, custom questions, EEO questions) is independently
    configurable per company. Filling this in with guessed selectors would
    be exactly the unverified assumption this project has repeatedly
    refused to build on.
    """

    ats_kind = "lever"
    known_field_selectors = frozenset()

    async def fill_identity_and_resume(
        self, page: Page, application: SubmittableApplication
    ) -> None:
        """Always raises -- Lever's real selectors are not yet verified."""
        raise FormFillerNotImplementedError(
            "Lever's real form field selectors have not been verified "
            "against a live posting -- see ADR-0028. Inspect a handful of "
            "real jobs.lever.co postings and update this class before "
            "using it for a real submission."
        )


class AshbyFormFiller:
    """Stub -- Ashby's real form selectors are not yet verified (ADR-0028).

    Ashby's application forms are per-company-configurable, with fields
    identified by an internal ``path`` rather than a stable public DOM
    contract, plus optional separate EEOC survey forms. Same "verify before
    building" refusal as :class:`LeverFormFiller`.
    """

    ats_kind = "ashby"
    known_field_selectors = frozenset()

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
