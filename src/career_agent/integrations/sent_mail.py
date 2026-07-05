"""Email send-confirmation: SENT-folder polling port (Phase 17, ADR-0041).

The email tier (ADR-0021) only ever creates drafts -- sending is a human
act this project never performs. That leaves its ``paused_for_human``
applications permanently unadvanceable by automation *unless* the system
can honestly observe that the human really sent the draft. This module is
that observation, as a port:

- :class:`SentMailChecker` -- "does a message to ``to`` with ``subject``
  exist in the SENT folder?" Nothing more. No send capability exists
  anywhere on this port either (the same interface-level restraint as
  ``EmailDraftSink`` having no ``send``).
- :func:`confirm_email_sent` -- the advance decision: a draft counts as
  sent only on a positive SENT-folder observation. "We couldn't check"
  (checker failure) is NOT "it wasn't sent" and NOT "it was sent" -- it
  raises, typed, because advancing or regressing an application on an
  unobserved fact would be exactly the unverified-signal trust this
  project refuses everywhere.

The real, OAuth-backed Gmail implementation of :class:`SentMailChecker`
remains deliberately unbuilt in this sandbox -- a Google OAuth token needs
the same dedicated, user-present review ADR-0020 gave session encryption,
and it is untestable here. The port + decision logic close ADR-0021's
recorded pre-scheduling gap *structurally*; the user validates the real
Gmail checker live (standing brief: sandbox-untestable, user validates).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class SentCheckUnavailableError(Exception):
    """The SENT folder could not be checked -- an unknown, not a no.

    Raised instead of returning ``False``: "we couldn't look" must never
    advance an application (false yes) or convince a caller the human
    didn't send it (false no). The caller retries later; the application
    stays exactly where it was.
    """


@runtime_checkable
class SentMailChecker(Protocol):
    """Read-only observation of the user's SENT folder. No send exists here."""

    async def was_sent(self, *, to: str, subject: str) -> bool:
        """Whether a message to ``to`` with ``subject`` exists in SENT."""
        ...


async def confirm_email_sent(
    checker: SentMailChecker, *, to: str, subject: str
) -> bool:
    """The advance decision: positive observation only.

    Returns ``True`` only when the checker positively finds the sent
    message. A checker failure propagates as
    :class:`SentCheckUnavailableError` -- never coerced into a boolean in
    either direction.
    """
    try:
        return await checker.was_sent(to=to, subject=subject)
    except SentCheckUnavailableError:
        raise
    except Exception as exc:
        raise SentCheckUnavailableError(
            f"could not check the SENT folder for {to!r} / {subject!r}: "
            f"{type(exc).__name__}"
        ) from exc
