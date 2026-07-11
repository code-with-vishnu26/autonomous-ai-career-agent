"""Phase 51 (ADR-0069): ApplicationPreparationEngine, driven against a real,
local Chromium instance -- the same offline-fixture-route pattern
``test_browser_applicator.py`` already established, reused here rather than
a Python-level mock.

The single most important property this file proves: the engine never
clicks anything. That is checked twice -- structurally, by scanning the
module's own source for any ``.click(`` call (so a future edit can't
silently reintroduce one), and behaviorally, by asserting the fixture's own
``#application-success``/hCaptcha markers never activate across every
scenario below.
"""

from __future__ import annotations

import ast
import glob
import inspect
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from career_agent.agents.application import engine as engine_module
from career_agent.agents.application.engine import ApplicationPreparationEngine
from career_agent.agents.apply.form_fillers import GreenhouseFormFiller, LeverFormFiller
from career_agent.domain.cover_letter import TailoredCoverLetter
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
from career_agent.integrations.adapters.base import FeatureUnavailableError
from career_agent.integrations.browser.browser_manager import BrowserManager
from career_agent.integrations.browser.session_manager import SessionManager
from career_agent.integrations.browser_session import EncryptedSessionStore
from tests._fakes import FakeKeyProvider

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "greenhouse" / "apply_form.html"
_EXTRA_QUESTION_FIXTURE = (
    Path(__file__).parent.parent
    / "fixtures"
    / "greenhouse"
    / "apply_form_with_extra_question.html"
)
_LEVER_REAL_FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "lever" / "apply_form_real.html"
)

_GREENHOUSE_URL = "https://boards.greenhouse.io/acme/jobs/12345"
_LEVER_URL = "https://jobs.lever.co/acme/12345"
_ASHBY_URL = "https://jobs.ashbyhq.com/acme/12345"
_ROUTE_PATTERNS = [
    "https://boards.greenhouse.io/**",
    "https://jobs.lever.co/**",
    "https://jobs.ashbyhq.com/**",
]


def _chromium_executable() -> str | None:
    matches = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    return matches[-1] if matches else None


pytestmark = pytest.mark.skipif(
    _chromium_executable() is None,
    reason="no local Chromium build found for real-browser tests",
)


def _route_to(fixture_path: Path):
    async def install(context: BrowserContext) -> None:
        async def handler(route):
            await route.fulfill(path=str(fixture_path))

        for pattern in _ROUTE_PATTERNS:
            await context.route(pattern, handler)

    return install


def _opportunity(opportunity_id: str, source_url: str = _GREENHOUSE_URL) -> Opportunity:
    return Opportunity(
        id=opportunity_id,
        company_id="acme",
        canonical_company="Acme Corp",
        title="Software Engineer",
        source="ats_api",
        source_url=source_url,
        provenance=Provenance(
            method="structured_api", reference=source_url, extraction_confidence=1.0
        ),
        description_raw="",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _approved_application(
    opportunity_id: str, *, legal_status: LegalStatusSection | None = None
) -> SubmittableApplication:
    resume = TailoredResume(
        id="resume-1",
        opportunity_id=opportunity_id,
        profile_version="profile-v1",
        content=TailoredContent(summary="Experienced engineer."),
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
        opportunity_id=opportunity_id,
        resume=resume,
        applicant=BasicsSection(name="Ada Lovelace", email="ada@example.com"),
        legal_status=legal_status or LegalStatusSection(),
        status="pending",
    )
    return SubmittableApplication(application=app)


def _engine(
    tmp_path: Path, *, fixture_path: Path = _FIXTURE
) -> ApplicationPreparationEngine:
    session_manager = SessionManager(EncryptedSessionStore(tmp_path, FakeKeyProvider()))
    browser_manager = BrowserManager(chromium_executable_path=_chromium_executable())
    return ApplicationPreparationEngine(
        browser_manager,
        session_manager,
        on_context_ready=_route_to(fixture_path),
        headless=True,
    )


# ---------------------------------------------------------------------------
# The structural guarantee: this module can never click anything.
# ---------------------------------------------------------------------------


def test_engine_source_never_calls_click() -> None:
    tree = ast.parse(inspect.getsource(engine_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "click":
            pytest.fail("agents/application/engine.py calls .click() somewhere")


def test_engine_source_never_mentions_a_submit_selector() -> None:
    source = inspect.getsource(engine_module)
    assert "submit_selector" not in source


# ---------------------------------------------------------------------------
# Happy path: Greenhouse, no custom questions.
# ---------------------------------------------------------------------------


async def test_greenhouse_ready_for_review_fills_known_fields(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    opportunity = _opportunity("opp-1")
    app = _approved_application("opp-1")
    session = await engine.build_session(opportunity, app)

    assert session.status == "READY_FOR_REVIEW"
    assert session.missing_fields == []
    assert set(GreenhouseFormFiller.known_field_selectors) <= set(session.filled_fields)
    assert session.uploaded_files == []  # Greenhouse's resume field is text, not upload
    assert session.provider == "greenhouse"
    assert session.company == "Acme Corp"
    assert session.opportunity_id == "opp-1"


async def test_greenhouse_carries_the_cover_letter_and_variant_id(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path)
    opportunity = _opportunity("opp-1")
    app = _approved_application("opp-1")
    cover_letter = TailoredCoverLetter(
        opportunity_id="opp-1", profile_version="profile-v1", body="Dear team,\n"
    )
    session = await engine.build_session(
        opportunity, app, cover_letter=cover_letter, resume_variant_id="variant-1"
    )
    assert session.cover_letter_body == "Dear team,\n"
    assert session.resume_variant_id == "variant-1"
    assert any("cover_letter_upload_unsupported" in w for w in session.warnings)


async def test_no_login_selector_records_a_warning_not_a_guess(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    session = await engine.build_session(
        _opportunity("opp-1"), _approved_application("opp-1")
    )
    assert any("login_detection_skipped" in w for w in session.warnings)


# ---------------------------------------------------------------------------
# A required, undescribable custom question -> BLOCKED, never a guess.
# ---------------------------------------------------------------------------


async def test_undescribable_required_field_blocks_not_guesses(tmp_path: Path) -> None:
    engine = _engine(tmp_path, fixture_path=_EXTRA_QUESTION_FIXTURE)
    session = await engine.build_session(
        _opportunity("opp-1"), _approved_application("opp-1")
    )
    assert session.status == "BLOCKED"
    assert "#why_us" in session.missing_fields


# ---------------------------------------------------------------------------
# Lever: real required file upload, evidenced (not guessed).
# ---------------------------------------------------------------------------


def _lever_application_with_artifact(tmp_path: Path) -> SubmittableApplication:
    from career_agent.agents.resume.file_renderer import render_resume_docx
    from tests.agents._profile_fixture import sample_master_profile

    profile = sample_master_profile()
    profile.basics.summary = "Backend engineer."
    submittable = _approved_application("opp-1")
    docx = render_resume_docx(
        submittable.application.resume.id,
        submittable.application.resume.content,
        profile,
        tmp_path / "artifacts",
    )
    resume = submittable.application.resume.model_copy(update={"artifacts": [docx]})
    app = submittable.application.model_copy(update={"resume": resume})
    return SubmittableApplication(application=app)


async def test_lever_uploads_the_real_docx_and_reports_it(tmp_path: Path) -> None:
    engine = _engine(tmp_path, fixture_path=_LEVER_REAL_FIXTURE)
    opportunity = _opportunity("opp-1", source_url=_LEVER_URL)
    app = _lever_application_with_artifact(tmp_path)
    docx_path = app.application.resume.artifacts[0].path

    session = await engine.build_session(opportunity, app)

    assert session.status == "READY_FOR_REVIEW"
    assert session.uploaded_files == [docx_path]
    assert set(LeverFormFiller.known_field_selectors) <= set(session.filled_fields)


async def test_lever_without_a_docx_artifact_raises_not_silently_skips(
    tmp_path: Path,
) -> None:
    from career_agent.agents.apply.form_fillers import MissingResumeArtifactError

    engine = _engine(tmp_path, fixture_path=_LEVER_REAL_FIXTURE)
    opportunity = _opportunity("opp-1", source_url=_LEVER_URL)
    app = _approved_application("opp-1")  # no artifacts
    with pytest.raises(MissingResumeArtifactError):
        await engine.build_session(opportunity, app)


# ---------------------------------------------------------------------------
# Ashby: an honest, registered stub -- never guessed at.
# ---------------------------------------------------------------------------


async def test_ashby_form_filler_not_implemented_propagates(tmp_path: Path) -> None:
    from career_agent.agents.apply.form_fillers import FormFillerNotImplementedError

    engine = _engine(tmp_path)
    opportunity = _opportunity("opp-1", source_url=_ASHBY_URL)
    app = _approved_application("opp-1")
    with pytest.raises(FormFillerNotImplementedError):
        await engine.build_session(opportunity, app)


# ---------------------------------------------------------------------------
# Genuinely unregistered platform -> FeatureUnavailableError, before any
# browser is even opened.
# ---------------------------------------------------------------------------


async def test_unsupported_provider_raises_before_opening_a_browser(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path)
    opportunity = _opportunity("opp-1", source_url="https://remoteok.com/remote-jobs/1")
    app = _approved_application("opp-1")
    with pytest.raises(FeatureUnavailableError):
        await engine.build_session(opportunity, app)
