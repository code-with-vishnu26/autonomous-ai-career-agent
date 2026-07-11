"""Phase 53 (ADR-0071): SubmissionEngine -- the fail-closed gate in front of
the real Tier-2 executor.

Precondition/refusal tests never touch a browser at all (proven by running
without a Chromium skip guard -- they must pass identically with or
without a local Chromium build). Only the genuine happy-path / real-click
tests are gated on a local Chromium build, reusing the exact offline
fixture-route pattern already established in
``test_browser_applicator.py``/``test_application_engine.py``.
"""

from __future__ import annotations

import glob
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from career_agent.agents.submission.submission_engine import SubmissionEngine
from career_agent.domain.application_session import ApplicationSession
from career_agent.domain.execution import SubmissionOutcome
from career_agent.domain.models import (
    Application,
    BasicsSection,
    LegalStatusSection,
    Opportunity,
    Provenance,
    Statement,
    SubmittableApplication,
    TailoredContent,
    TailoredResume,
    TruthfulnessResult,
)
from career_agent.domain.review import ReviewSession
from career_agent.integrations.adapters.base import FeatureUnavailableError
from career_agent.integrations.browser_session import EncryptedSessionStore
from tests._fakes import FakeKeyProvider

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "greenhouse" / "apply_form.html"
_GREENHOUSE_URL = "https://boards.greenhouse.io/acme/jobs/12345"
_ASHBY_URL = "https://jobs.ashbyhq.com/acme/12345"
_ROUTE_PATTERNS = [
    "https://boards.greenhouse.io/**",
    "https://jobs.ashbyhq.com/**",
]


def _chromium_executable() -> str | None:
    matches = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    return matches[-1] if matches else None


def _route_to(fixture_path: Path):
    async def install(context: BrowserContext) -> None:
        async def handler(route):
            await route.fulfill(path=str(fixture_path))

        for pattern in _ROUTE_PATTERNS:
            await context.route(pattern, handler)

    return install


def _opportunity(
    opportunity_id: str = "opp-1",
    *,
    source_url: str = _GREENHOUSE_URL,
    source: str = "ats_api",
) -> Opportunity:
    return Opportunity(
        id=opportunity_id,
        company_id="acme",
        canonical_company="Acme Corp",
        title="Software Engineer",
        source=source,
        source_url=source_url,
        provenance=Provenance(
            method="structured_api", reference=source_url, extraction_confidence=1.0
        ),
        description_raw="",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _content() -> TailoredContent:
    return TailoredContent(summary="Experienced engineer.")


def _approved_application(
    content: TailoredContent | None = None,
) -> SubmittableApplication:
    resume = TailoredResume(
        id="resume-1",
        opportunity_id="opp-1",
        profile_version="profile-v1",
        content=content or _content(),
        truthfulness=TruthfulnessResult(
            profile_version="profile-v1",
            approved=True,
            statements=[
                Statement(text="x", evidence=None, confidence=0.9, verified=True)
            ],
            prompt_version="test-v1",
        ),
    )
    app = Application(
        id="app-1",
        opportunity_id="opp-1",
        resume=resume,
        applicant=BasicsSection(name="Ada Lovelace", email="ada@example.com"),
        legal_status=LegalStatusSection(),
        status="pending",
    )
    return SubmittableApplication(application=app)


def _application_session(**overrides: object) -> ApplicationSession:
    fields = {
        "id": "sess-1",
        "provider": "greenhouse",
        "company": "Acme Corp",
        "job_title": "Software Engineer",
        "url": _GREENHOUSE_URL,
        "opportunity_id": "opp-1",
        "status": "READY_FOR_REVIEW",
        "resume_variant_id": "variant-1",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return ApplicationSession(**fields)


def _review_session(**overrides: object) -> ReviewSession:
    fields = {
        "id": "review-1",
        "application_session_id": "sess-1",
        "company": "Acme Corp",
        "job_title": "Software Engineer",
        "provider": "greenhouse",
        "approval_status": "APPROVED",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return ReviewSession(**fields)


def _engine(tmp_path: Path, *, fixture_path: Path = _FIXTURE) -> SubmissionEngine:
    session_store = EncryptedSessionStore(tmp_path, FakeKeyProvider())
    return SubmissionEngine(
        session_store,
        chromium_executable_path=_chromium_executable(),
        on_context_ready=_route_to(fixture_path),
    )


def _never_confirm() -> bool:
    raise AssertionError("confirm_fn must never be called for this precondition")


# ---------------------------------------------------------------------------
# Fail-closed preconditions -- never touch a browser, run unconditionally.
# ---------------------------------------------------------------------------


async def test_review_not_approved_refuses_before_any_confirmation(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path)
    result = await engine.submit(
        _opportunity(),
        _approved_application(),
        _review_session(approval_status="REJECTED"),
        _application_session(),
        _content(),
        confirm_fn=_never_confirm,
    )
    assert result.status == "REFUSED"
    assert result.refusal_reason == "review_not_approved"
    assert result.submitted is False


async def test_application_not_ready_refuses(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    result = await engine.submit(
        _opportunity(),
        _approved_application(),
        _review_session(),
        _application_session(status="BLOCKED"),
        _content(),
        confirm_fn=_never_confirm,
    )
    assert result.status == "REFUSED"
    assert result.refusal_reason == "application_not_ready"


async def test_review_application_mismatch_refuses(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    result = await engine.submit(
        _opportunity(),
        _approved_application(),
        _review_session(application_session_id="some-other-session"),
        _application_session(),
        _content(),
        confirm_fn=_never_confirm,
    )
    assert result.status == "REFUSED"
    assert result.refusal_reason == "review_application_mismatch"


async def test_artifact_mismatch_refuses(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    stored_content = TailoredContent(summary="A completely different summary.")
    result = await engine.submit(
        _opportunity(),
        _approved_application(),
        _review_session(),
        _application_session(),
        stored_content,
        confirm_fn=_never_confirm,
    )
    assert result.status == "REFUSED"
    assert result.refusal_reason == "REFUSED_ARTIFACT_MISMATCH"


async def test_no_stored_variant_content_refuses_as_artifact_mismatch(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path)
    result = await engine.submit(
        _opportunity(),
        _approved_application(),
        _review_session(),
        _application_session(),
        None,
        confirm_fn=_never_confirm,
    )
    assert result.status == "REFUSED"
    assert result.refusal_reason == "REFUSED_ARTIFACT_MISMATCH"


async def test_manual_only_source_refuses_without_touching_a_browser(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path)
    result = await engine.submit(
        _opportunity(source="web_search", source_url="https://example.invalid/job/1"),
        _approved_application(),
        _review_session(),
        _application_session(),
        _content(),
        confirm_fn=_never_confirm,
    )
    assert result.status == "REFUSED"
    assert result.refusal_reason == "REFUSED_MANUAL_ONLY_SOURCE"


async def test_prior_definitely_submitted_refuses(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    result = await engine.submit(
        _opportunity(),
        _approved_application(),
        _review_session(),
        _application_session(),
        _content(),
        prior_outcome=SubmissionOutcome.DEFINITELY_SUBMITTED,
        confirm_fn=_never_confirm,
    )
    assert result.status == "REFUSED"
    assert result.refusal_reason == "REFUSED_PRIOR_SUBMITTED"


async def test_prior_outcome_uncertain_refuses(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    result = await engine.submit(
        _opportunity(),
        _approved_application(),
        _review_session(),
        _application_session(),
        _content(),
        prior_outcome=SubmissionOutcome.OUTCOME_UNCERTAIN,
        confirm_fn=_never_confirm,
    )
    assert result.status == "REFUSED"
    assert result.refusal_reason == "REFUSED_PRIOR_UNCERTAIN"


async def test_user_cancellation_never_touches_a_browser(tmp_path: Path) -> None:
    engine = _engine(tmp_path)

    def _cancel() -> bool:
        raise KeyboardInterrupt

    result = await engine.submit(
        _opportunity(),
        _approved_application(),
        _review_session(),
        _application_session(),
        _content(),
        confirm_fn=_cancel,
    )
    assert result.status == "CANCELLED"
    assert result.submitted is False


# ---------------------------------------------------------------------------
# Real-Chromium: the actual click only happens once every gate holds.
# ---------------------------------------------------------------------------

pytestmark_browser = pytest.mark.skipif(
    _chromium_executable() is None,
    reason="no local Chromium build found for real-browser tests",
)


@pytestmark_browser
async def test_full_happy_path_submits_after_every_gate_holds(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    confirmed = {"called": False}

    def _confirm() -> bool:
        confirmed["called"] = True
        return True

    result = await engine.submit(
        _opportunity(),
        _approved_application(),
        _review_session(),
        _application_session(),
        _content(),
        confirm_fn=_confirm,
    )
    assert confirmed["called"] is True
    assert result.status == "SUBMITTED"
    assert result.submitted is True
    assert result.confirmation_id is None  # never fabricated -- see warnings
    assert any("no verified confirmation-id" in w for w in result.warnings)


@pytestmark_browser
async def test_ashby_stub_raises_feature_unavailable(tmp_path: Path) -> None:
    engine = _engine(tmp_path, fixture_path=_FIXTURE)
    with pytest.raises(FeatureUnavailableError):
        await engine.submit(
            _opportunity(source_url=_ASHBY_URL),
            _approved_application(),
            _review_session(provider="ashby"),
            _application_session(provider="ashby", url=_ASHBY_URL),
            _content(),
            confirm_fn=lambda: True,
        )
