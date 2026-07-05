"""Shared test doubles. Not collected as tests (no ``test_`` prefix).

``FakeHttpClient`` satisfies the :class:`~career_agent.core.interfaces.HttpClient`
port by replaying recorded JSON, so the suite makes no network call and stays
deterministic and offline (the live path is validated only when the project
runs on the user's own machine).
"""

from __future__ import annotations

import json
from pathlib import Path

from career_agent.core.events import ApplicationSubmitted, Event
from career_agent.core.interfaces import ClaimVerdict
from career_agent.domain.models import DraftedTailoring, SubmittableApplication

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(*parts: str) -> object:
    """Load and parse a JSON fixture under ``tests/fixtures``."""
    return json.loads(FIXTURES.joinpath(*parts).read_text())


class FakeHttpClient:
    """Replays recorded JSON by substring-matching the requested URL.

    Records every call on ``calls`` so tests can assert how a source queried
    the API (e.g. that it passed ``content=true``).
    """

    def __init__(
        self,
        responses: dict[str, object] | None = None,
        *,
        default: object | None = None,
    ) -> None:
        self._responses = responses or {}
        self._default = default
        self.calls: list[tuple[str, dict[str, str] | None]] = []
        self.post_calls: list[tuple[str, dict[str, object]]] = []

    async def get_json(
        self, url: str, *, params: dict[str, str] | None = None
    ) -> object:
        self.calls.append((url, params))
        return self._resolve(url)

    async def post_json(
        self,
        url: str,
        *,
        json: dict[str, object],
        headers: dict[str, str] | None = None,
    ) -> object:
        self.post_calls.append((url, json))
        return self._resolve(url)

    def _resolve(self, url: str) -> object:
        for key, payload in self._responses.items():
            if key in url:
                return payload
        if self._default is not None:
            return self._default
        raise KeyError(f"no fake response registered for {url!r}")


class FakeClaimVerifier:
    """Satisfies :class:`~career_agent.core.interfaces.ClaimVerifier`.

    Deterministic, fixture-driven, exactly ``FakeHttpClient``'s pattern applied
    to the truthfulness gate: ``verdicts`` maps exact statement text to a
    canned :class:`~career_agent.core.interfaces.ClaimVerdict` (or an
    :class:`Exception` instance/class to simulate verifier failure). A missing
    key raises loudly rather than returning a silent default -- a test that
    doesn't specify a verdict for a statement it exercises is a broken test,
    not a pass.

    Proves the gate's *orchestration* is correct (evidence assembly, category
    mapping, fail-closed aggregation) -- it proves nothing about whether a real
    model judges these claims correctly. That is what the promptfoo suite is
    for (ADR-0016); this fake is not a substitute for it.
    """

    def __init__(
        self,
        verdicts: dict[str, ClaimVerdict | Exception | type[Exception]],
        *,
        prompt_version: str = "fake-v1",
    ) -> None:
        self._verdicts = verdicts
        self.prompt_version = prompt_version
        self.calls: list[tuple[str, str]] = []

    async def verify_claim(self, statement_text: str, evidence: str) -> ClaimVerdict:
        self.calls.append((statement_text, evidence))
        if statement_text not in self._verdicts:
            raise KeyError(
                f"no fake verdict registered for statement {statement_text!r}"
            )
        outcome = self._verdicts[statement_text]
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, type) and issubclass(outcome, Exception):
            raise outcome("simulated verifier failure")
        return outcome


class FakeATSAdapter:
    """Satisfies :class:`~career_agent.core.interfaces.ATSAdapter`.

    ``submit_outcomes`` maps an ``Application.id`` to either ``None`` (record
    the call, return a canned ``ApplicationSubmitted``) or a
    :class:`~career_agent.agents.apply.applicator.SubmissionError` instance
    to simulate a real ATS-side failure (duplicate submission, rate limit,
    malformed payload) -- so submission-time failure handling is exercised
    against something other than the happy path, same discipline as
    ``FakeClaimVerifier``'s exception-simulation. Every call is recorded on
    ``calls`` so a test can assert whether the adapter was ever reached at
    all -- the load-bearing assertion for confirmation-token rejection.
    """

    def __init__(
        self,
        *,
        ats_kind: str = "greenhouse",
        submit_outcomes: dict[str, Exception] | None = None,
    ) -> None:
        self.ats_kind = ats_kind
        self._submit_outcomes = submit_outcomes or {}
        self.calls: list[SubmittableApplication] = []

    async def fetch_postings(self, company: object) -> list[object]:
        raise NotImplementedError("FakeATSAdapter is submit-only in this suite")

    async def submit(self, application: SubmittableApplication) -> Event:
        self.calls.append(application)
        app_id = application.application.id
        if app_id in self._submit_outcomes:
            raise self._submit_outcomes[app_id]
        return ApplicationSubmitted(
            correlation_id=application.application.opportunity_id,
            application_id=app_id,
            tier_used="ats_api",
        )


class FakeEmailDraftSink:
    """Satisfies :class:`~career_agent.core.interfaces.EmailDraftSink`.

    Has no ``send`` method either -- the fake mirrors the real port's
    deliberate scope restraint exactly, not a looser test-only shape.
    Records every call so a test can assert a draft was (or was never)
    created.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    async def create_draft(self, *, to: str, subject: str, body: str) -> str:
        self.calls.append({"to": to, "subject": subject, "body": body})
        return f"draft-{len(self.calls)}"


class FakeContentDrafter:
    """Satisfies :class:`~career_agent.core.interfaces.ContentDrafter`.

    Deterministic, fixture-driven, the same pattern as ``FakeClaimVerifier``:
    ``result`` is the canned :class:`DraftedTailoring` returned on every
    call (or an ``Exception`` to simulate drafter failure). Records every
    call -- including the ``gap_report`` it was shown (Phase 10, ADR-0034),
    which is how tests prove structurally what the drafter was and was NOT
    ever told (matrix case B1: no GENUINE gap in any recorded gap_report,
    across every retry).

    ``results`` (optional) supplies a per-call sequence for retailor-loop
    tests: call N returns ``results[N]``, and calls past the end repeat the
    final entry.
    """

    def __init__(
        self,
        result: DraftedTailoring | Exception | None = None,
        *,
        results: list[DraftedTailoring | Exception] | None = None,
        prompt_version: str = "fake-draft-v1",
    ) -> None:
        if (result is None) == (results is None):
            raise ValueError("pass exactly one of result= or results=")
        self._results = results if results is not None else [result]
        self.prompt_version = prompt_version
        self.calls: list[tuple[str, str, object]] = []

    async def draft(
        self, opportunity: object, profile: object, *, gap_report: object = None
    ) -> DraftedTailoring:
        index = min(len(self.calls), len(self._results) - 1)
        self.calls.append(
            (opportunity.id, profile.version, gap_report)  # type: ignore[attr-defined]
        )
        outcome = self._results[index]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeKeyProvider:
    """Satisfies :class:`~career_agent.integrations.browser_session.KeyProvider`.

    In-memory only -- no real OS keychain touched. ``unavailable=True``
    simulates a keychain the process cannot reach (headless/CI, no backend
    configured), so callers can be tested against the fail-closed path
    without needing a real backend to fail.
    """

    def __init__(self, *, unavailable: bool = False) -> None:
        self._unavailable = unavailable
        self._key: bytes | None = None

    def get_or_create_key(self) -> bytes:
        if self._unavailable:
            from career_agent.integrations.browser_session import (
                SessionEncryptionUnavailableError,
            )

            raise SessionEncryptionUnavailableError("simulated keychain unavailable")
        if self._key is None:
            from cryptography.fernet import Fernet

            self._key = Fernet.generate_key()
        return self._key
