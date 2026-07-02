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
from career_agent.domain.models import SubmittableApplication

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
