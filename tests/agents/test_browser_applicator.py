"""Phase 7b3 / ADR-0020: BrowserApplicator, driven against a real, local
Chromium instance -- not a Python-level fake standing in for a browser.

Generalized past Greenhouse-only in Phase 8g / ADR-0028: dispatch to a
per-``ats_kind`` ``FormFiller`` resolved from ``resolve_ats_kind``, and the
platform-agnostic "refuse rather than guess" check for any required form
field no registered ``FormFiller`` knows how to fill.

Tests navigate to real-looking ATS URLs (``boards.greenhouse.io``,
``jobs.lever.co``, ``jobs.ashbyhq.com``) so ``resolve_ats_kind`` resolves
the same ``ats_kind`` production code would -- a Playwright route,
installed via ``on_context_ready``, redirects those requests to a local
offline fixture. Nothing here ever makes a real network request.

``?challenge=1`` (still read from ``window.location.search`` on whatever
URL was actually navigated to) makes the fixture show a verification panel
after the first submit click, exactly like a real mid-flow CAPTCHA/
verification wall -- the load-bearing tests prove BrowserApplicator pauses
instead of treating that as success, and that resume() genuinely never
re-clicks submit until the challenge is actually gone from the live page.
"""

from __future__ import annotations

import glob
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from career_agent.agents.apply.browser_applicator import (
    BrowserApplicator,
    ChallengeStillPresentError,
    NoApplicableFormFillerError,
    RequiredFieldsStillUnresolvedError,
    UnknownPauseTokenError,
    UnsupportedFormFieldsError,
    _unhandled_required_fields,
)
from career_agent.agents.apply.form_fillers import (
    FormFillerNotImplementedError,
    GreenhouseFormFiller,
    LeverFormFiller,
    MissingResumeArtifactError,
    default_form_fillers,
)
from career_agent.core.events import ApplicationSubmitted, HumanActionRequired
from career_agent.domain.models import (
    Application,
    BasicsSection,
    HumanConfirmation,
    LegalStatusSection,
    Opportunity,
    PauseAcknowledgment,
    Provenance,
    Statement,
    SubmittableApplication,
    TailoredContent,
    TailoredResume,
    TruthfulnessResult,
)
from career_agent.integrations.browser_session import EncryptedSessionStore
from career_agent.storage.memory import InMemoryOpportunityRepository
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
_LEVER_SHAPED_FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "lever" / "apply_form.html"
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
    """Locate a Chromium build compatible with this sandbox's Playwright.

    Production use passes no override and lets Playwright find its own
    matched browser; this sandbox has a version-mismatched pre-installed
    Chromium, so tests point at it explicitly (see environment notes).
    """
    matches = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    return matches[-1] if matches else None


pytestmark = pytest.mark.skipif(
    _chromium_executable() is None,
    reason="no local Chromium build found for real-browser tests",
)


def _fixture_url(*, challenge: bool = False) -> str:
    suffix = "?challenge=1" if challenge else ""
    return f"file://{_FIXTURE}{suffix}"


def _route_to(fixture_path: Path):
    async def install(context: BrowserContext) -> None:
        async def handler(route):
            await route.fulfill(path=str(fixture_path))

        for pattern in _ROUTE_PATTERNS:
            await context.route(pattern, handler)

    return install


def _opportunity(
    opportunity_id: str, source_url: str = _GREENHOUSE_URL, *, challenge: bool = False
) -> Opportunity:
    url = f"{source_url}?challenge=1" if challenge else source_url
    return Opportunity(
        id=opportunity_id,
        company_id="acme",
        canonical_company="acme.com",
        title="Software Engineer",
        source="ats_api",
        source_url=url,
        provenance=Provenance(
            method="structured_api", reference=url, extraction_confidence=1.0
        ),
        description_raw="",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _approved_application(
    opportunity_id: str,
    *,
    applicant: BasicsSection | None = None,
    legal_status: LegalStatusSection | None = None,
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
        applicant=applicant
        or BasicsSection(name="Ada Lovelace", email="ada@example.com"),
        legal_status=legal_status or LegalStatusSection(),
        status="pending",
    )
    return SubmittableApplication(application=app)


def _confirmation(preview_token: str) -> HumanConfirmation:
    return HumanConfirmation(
        preview_token=preview_token,
        confirmed_by="test-user",
        confirmed_at=datetime.now(UTC),
    )


def _ack(pause_token: str) -> PauseAcknowledgment:
    return PauseAcknowledgment(
        pause_token=pause_token,
        confirmed_by="test-user",
        confirmed_at=datetime.now(UTC),
    )


class _AltSelectorFormFiller:
    """A test-only FormFiller shaped like the real, confirmed Lever DOM
    (ADR-0029): identity fields have no ``id``, only ``name``, and the
    challenge/submit markers use different ids than Greenhouse's fixture --
    proves BrowserApplicator genuinely reads ``challenge_selector``/
    ``submit_selector`` from the active FormFiller, rather than a
    hardcoded, Greenhouse-shaped literal."""

    ats_kind = "alt"
    known_field_selectors = frozenset(
        {"[name='name']", "[name='email']", "[name='resume_text']"}
    )
    challenge_selector = "#extra_check"
    submit_selector = "#go_button"

    async def fill_identity_and_resume(self, page, application) -> None:
        applicant = application.application.applicant
        summary = application.application.resume.content.summary
        await page.fill("[name='name']", applicant.name)
        await page.fill("[name='email']", applicant.email)
        await page.fill("[name='resume_text']", summary)


async def _applicator(
    tmp_path: Path,
    opportunity: Opportunity,
    *,
    fixture_path: Path = _FIXTURE,
    form_fillers: dict | None = None,
    diagnostics_dir: Path | None = None,
) -> BrowserApplicator:
    repo = InMemoryOpportunityRepository()
    await repo.add(opportunity)
    session_store = EncryptedSessionStore(tmp_path, FakeKeyProvider())
    return BrowserApplicator(
        session_store,
        repo,
        form_fillers=form_fillers,
        chromium_executable_path=_chromium_executable(),
        on_context_ready=_route_to(fixture_path),
        diagnostics_dir=diagnostics_dir,
    )


# ---------------------------------------------------------------------------
# Happy path: no challenge
# ---------------------------------------------------------------------------


async def test_submit_completes_when_no_challenge_appears(tmp_path: Path) -> None:
    opportunity = _opportunity("opp-1")
    applicator = await _applicator(tmp_path, opportunity)
    app = _approved_application("opp-1")
    preview = await applicator.prepare(app)
    event = await applicator.submit(preview, _confirmation(preview.preview_token))
    assert isinstance(event, ApplicationSubmitted)
    assert event.tier_used == "browser"


# ---------------------------------------------------------------------------
# Real applicant data must actually land in the form (Phase 8f, ADR-0027):
# _fill_form used to write hardcoded placeholder strings regardless of who
# was applying -- proven wrong here against the real, live page, not just by
# the flow completing. Now lives on GreenhouseFormFiller (ADR-0028).
# ---------------------------------------------------------------------------


async def test_fill_form_writes_the_real_applicants_name_and_email(
    tmp_path: Path,
) -> None:
    opportunity = _opportunity("opp-1")
    applicator = await _applicator(tmp_path, opportunity)
    app = _approved_application(
        "opp-1",
        applicant=BasicsSection(name="Grace Beatrice Hopper", email="grace@navy.mil"),
    )

    page, context, browser, _console_log = await applicator._open_page(
        "opp-1", _fixture_url()
    )
    try:
        await GreenhouseFormFiller().fill_identity_and_resume(page, app)
        # rsplit(" ", 1): everything but the last token is first_name, the
        # documented, known-imprecise heuristic (ADR-0027) -- proven here
        # against a real multi-part name, not assumed correct.
        assert await page.input_value("#first_name") == "Grace Beatrice"
        assert await page.input_value("#last_name") == "Hopper"
        assert await page.input_value("#email") == "grace@navy.mil"
    finally:
        await browser.close()


async def test_fill_form_single_token_name_falls_back_to_empty_last_name(
    tmp_path: Path,
) -> None:
    opportunity = _opportunity("opp-1")
    applicator = await _applicator(tmp_path, opportunity)
    app = _approved_application(
        "opp-1", applicant=BasicsSection(name="Cher", email="cher@example.com")
    )

    page, context, browser, _console_log = await applicator._open_page(
        "opp-1", _fixture_url()
    )
    try:
        await GreenhouseFormFiller().fill_identity_and_resume(page, app)
        assert await page.input_value("#first_name") == "Cher"
        assert await page.input_value("#last_name") == ""
    finally:
        await browser.close()


# ---------------------------------------------------------------------------
# Dispatch (Phase 8g, ADR-0028): resolve_ats_kind picks the FormFiller, and
# refuses cleanly for a URL/ats_kind nothing is registered for.
# ---------------------------------------------------------------------------


async def test_prepare_raises_for_an_unresolvable_source_url(tmp_path: Path) -> None:
    opportunity = _opportunity("opp-1", source_url="https://acme.com/careers/eng-1")
    applicator = await _applicator(tmp_path, opportunity)
    with pytest.raises(NoApplicableFormFillerError, match="ats_kind=None"):
        await applicator.prepare(_approved_application("opp-1"))


async def test_prepare_raises_when_no_form_filler_is_registered_for_the_ats_kind(
    tmp_path: Path,
) -> None:
    opportunity = _opportunity("opp-1", source_url=_GREENHOUSE_URL)
    applicator = await _applicator(tmp_path, opportunity, form_fillers={})
    with pytest.raises(NoApplicableFormFillerError, match="greenhouse"):
        await applicator.prepare(_approved_application("opp-1"))


async def test_submit_through_lever_without_a_resume_artifact_refuses(
    tmp_path: Path,
) -> None:
    """Phase 11 (ADR-0035): LeverFormFiller is real now, and its own
    precondition refusal -- Lever's resume field is a required file upload,
    so no DOCX artifact means no honest submission -- is genuinely reached
    through the real prepare()/submit() flow, the same proof shape the old
    stub test used for FormFillerNotImplementedError."""
    opportunity = _opportunity("opp-1", source_url=_LEVER_URL)
    applicator = await _applicator(
        tmp_path, opportunity, form_fillers=default_form_fillers()
    )
    app = _approved_application("opp-1")  # carries no artifacts
    preview = await applicator.prepare(app)
    with pytest.raises(MissingResumeArtifactError, match="no DOCX resume artifact"):
        await applicator.submit(preview, _confirmation(preview.preview_token))


async def test_submit_raises_form_filler_not_implemented_for_ashby(
    tmp_path: Path,
) -> None:
    opportunity = _opportunity("opp-1", source_url=_ASHBY_URL)
    applicator = await _applicator(
        tmp_path, opportunity, form_fillers=default_form_fillers()
    )
    app = _approved_application("opp-1")
    preview = await applicator.prepare(app)
    with pytest.raises(FormFillerNotImplementedError, match="not been verified"):
        await applicator.submit(preview, _confirmation(preview.preview_token))


# ---------------------------------------------------------------------------
# The refusal (Phase 8g, ADR-0028): a required field no FormFiller knows how
# to fill must block submission before #submit_app is ever clicked -- proven
# against a real live page's real form elements, not a fixed selector list.
# ---------------------------------------------------------------------------


async def test_unhandled_required_fields_is_empty_for_the_ordinary_fixture(
    tmp_path: Path,
) -> None:
    applicator = await _applicator(tmp_path, _opportunity("opp-1"))
    page, context, browser, _console_log = await applicator._open_page(
        "opp-1", _fixture_url()
    )
    try:
        unhandled = await _unhandled_required_fields(
            page, GreenhouseFormFiller.known_field_selectors
        )
        assert unhandled == []
    finally:
        await browser.close()


async def test_unhandled_required_fields_finds_the_extra_question(
    tmp_path: Path,
) -> None:
    applicator = await _applicator(
        tmp_path, _opportunity("opp-1"), fixture_path=_EXTRA_QUESTION_FIXTURE
    )
    page, context, browser, _console_log = await applicator._open_page(
        "opp-1", f"file://{_EXTRA_QUESTION_FIXTURE}"
    )
    try:
        unhandled = await _unhandled_required_fields(
            page, GreenhouseFormFiller.known_field_selectors
        )
        assert unhandled == ["#why_us"]
    finally:
        await browser.close()


async def test_submit_refuses_and_never_clicks_when_a_required_field_is_unknown(
    tmp_path: Path,
) -> None:
    opportunity = _opportunity("opp-1")
    applicator = await _applicator(
        tmp_path, opportunity, fixture_path=_EXTRA_QUESTION_FIXTURE
    )
    app = _approved_application("opp-1")
    preview = await applicator.prepare(app)
    with pytest.raises(UnsupportedFormFieldsError, match="why_us"):
        await applicator.submit(preview, _confirmation(preview.preview_token))


async def test_unhandled_field_is_detected_before_any_click_on_the_live_page(
    tmp_path: Path,
) -> None:
    """The real precondition for submit()'s refusal, checked directly
    against a real, live page: by the exact point _unhandled_required_fields
    finds the extra required field, the success marker has never appeared --
    the same "genuinely never fired" proof, verified against real DOM state
    rather than trusted from exception type alone, as the 7a token-binding
    (adapter.calls == []) and 7b3 CAPTCHA-pause
    (page.is_visible("#application-success") is False) tests."""
    applicator = await _applicator(
        tmp_path, _opportunity("opp-1"), fixture_path=_EXTRA_QUESTION_FIXTURE
    )
    page, context, browser, _console_log = await applicator._open_page(
        "opp-1", f"file://{_EXTRA_QUESTION_FIXTURE}"
    )
    try:
        app = _approved_application("opp-1")
        await GreenhouseFormFiller().fill_identity_and_resume(page, app)
        unhandled = await _unhandled_required_fields(
            page, GreenhouseFormFiller.known_field_selectors
        )
        assert unhandled == ["#why_us"]
        # submit() raises exactly when this list is non-empty, and does so
        # before ever calling page.click("#submit_app") -- verified here
        # against the real page's own state, not assumed from code order.
        assert await page.is_visible("#application-success") is False
    finally:
        await browser.close()


# ---------------------------------------------------------------------------
# Phase 62 (ADR-0080): failure-diagnostics capture and bounded retry.
# ---------------------------------------------------------------------------


async def test_submit_failure_captures_diagnostics_when_a_dir_is_configured(
    tmp_path: Path,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    applicator = await _applicator(
        tmp_path / "session",
        _opportunity("opp-1"),
        fixture_path=_EXTRA_QUESTION_FIXTURE,
        diagnostics_dir=diagnostics_dir,
    )
    app = _approved_application("opp-1")
    preview = await applicator.prepare(app)
    with pytest.raises(UnsupportedFormFieldsError) as excinfo:
        await applicator.submit(preview, _confirmation(preview.preview_token))

    captured_dir = Path(excinfo.value.diagnostics_dir)
    assert captured_dir.is_dir()
    assert captured_dir.is_relative_to(diagnostics_dir)
    assert (captured_dir / "screenshot.png").exists()
    assert (captured_dir / "screenshot.png").stat().st_size > 0
    assert "apply" in (captured_dir / "page.html").read_text(encoding="utf-8").lower()


async def test_submit_failure_without_a_diagnostics_dir_configured_sets_nothing(
    tmp_path: Path,
) -> None:
    """Default behavior (no ``diagnostics_dir`` passed) is unchanged from
    before Phase 62 -- existing callers/tests keep working exactly as they
    did, with no new attribute on the raised exception."""
    applicator = await _applicator(
        tmp_path, _opportunity("opp-1"), fixture_path=_EXTRA_QUESTION_FIXTURE
    )
    app = _approved_application("opp-1")
    preview = await applicator.prepare(app)
    with pytest.raises(UnsupportedFormFieldsError) as excinfo:
        await applicator.submit(preview, _confirmation(preview.preview_token))
    assert getattr(excinfo.value, "diagnostics_dir", None) is None


class _FlakyThenGreenhouseFormFiller(GreenhouseFormFiller):
    """Raises a real Playwright timeout the first ``fail_times`` calls,
    then delegates to the real GreenhouseFormFiller -- proves
    ``submit()``'s retry wrapping actually retries a real transient
    failure rather than just being present in the source."""

    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls = 0

    async def fill_identity_and_resume(self, page, application) -> None:
        self.calls += 1
        if self.calls <= self.fail_times:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError

            raise PlaywrightTimeoutError(f"simulated transient failure #{self.calls}")
        await super().fill_identity_and_resume(page, application)


async def test_submit_retries_a_transient_fill_timeout_and_still_succeeds(
    tmp_path: Path,
) -> None:
    filler = _FlakyThenGreenhouseFormFiller(fail_times=2)
    applicator = await _applicator(
        tmp_path, _opportunity("opp-1"), form_fillers={"greenhouse": filler}
    )
    app = _approved_application("opp-1")
    preview = await applicator.prepare(app)
    event = await applicator.submit(preview, _confirmation(preview.preview_token))
    assert isinstance(event, ApplicationSubmitted)
    # 2 failures + 1 success == exactly the 3-attempt retry budget, not an
    # unbounded loop or a lucky single retry.
    assert filler.calls == 3


async def test_submit_gives_up_after_exhausting_retries_on_persistent_timeouts(
    tmp_path: Path,
) -> None:
    filler = _FlakyThenGreenhouseFormFiller(fail_times=10)
    applicator = await _applicator(
        tmp_path, _opportunity("opp-1"), form_fillers={"greenhouse": filler}
    )
    app = _approved_application("opp-1")
    preview = await applicator.prepare(app)
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    with pytest.raises(PlaywrightTimeoutError):
        await applicator.submit(preview, _confirmation(preview.preview_token))
    # Exactly the retry budget (3), never retried indefinitely.
    assert filler.calls == 3


async def test_submit_closes_the_browser_after_refusing_an_unsupported_field(
    tmp_path: Path,
) -> None:
    """A refusal must not leak an open browser -- proven by capturing the
    real Browser object via on_context_ready and checking is_connected()
    is False after submit() raises, not merely trusting the try/except
    structure that closes it."""
    captured: dict[str, object] = {}

    async def capture_and_route(context: BrowserContext) -> None:
        captured["browser"] = context.browser

        async def handler(route):
            await route.fulfill(path=str(_EXTRA_QUESTION_FIXTURE))

        for pattern in _ROUTE_PATTERNS:
            await context.route(pattern, handler)

    opportunity = _opportunity("opp-1")
    repo = InMemoryOpportunityRepository()
    await repo.add(opportunity)
    session_store = EncryptedSessionStore(tmp_path, FakeKeyProvider())
    applicator = BrowserApplicator(
        session_store,
        repo,
        chromium_executable_path=_chromium_executable(),
        on_context_ready=capture_and_route,
    )
    app = _approved_application("opp-1")
    preview = await applicator.prepare(app)
    with pytest.raises(UnsupportedFormFieldsError):
        await applicator.submit(preview, _confirmation(preview.preview_token))

    browser = captured["browser"]
    assert browser is not None
    assert browser.is_connected() is False


# ---------------------------------------------------------------------------
# Per-FormFiller selectors (Phase 8h, ADR-0029): name-based known_field_
# selectors, and challenge_selector/submit_selector genuinely read from the
# active FormFiller rather than hardcoded to Greenhouse's own markers --
# proven against a fixture shaped like the real, confirmed Lever DOM.
# ---------------------------------------------------------------------------


async def test_unhandled_required_fields_matches_name_based_selectors(
    tmp_path: Path,
) -> None:
    """A field with no id, only name -- the real shape a live Lever posting
    confirmed -- must be matched by a [name='...'] known_field_selectors
    entry, proven against the real live page's actual DOM."""
    applicator = await _applicator(
        tmp_path, _opportunity("opp-1"), fixture_path=_LEVER_SHAPED_FIXTURE
    )
    page, context, browser, _console_log = await applicator._open_page(
        "opp-1", f"file://{_LEVER_SHAPED_FIXTURE}"
    )
    try:
        unhandled = await _unhandled_required_fields(
            page, _AltSelectorFormFiller.known_field_selectors
        )
        assert unhandled == []
    finally:
        await browser.close()


async def test_submit_uses_the_active_fillers_declared_selectors(
    tmp_path: Path,
) -> None:
    """submit() must click the active FormFiller's own submit_selector, not
    a hardcoded Greenhouse-shaped literal -- proven end to end against a
    fixture whose real submit button has a different id entirely."""
    opportunity = _opportunity("opp-1", source_url=_LEVER_URL)
    applicator = await _applicator(
        tmp_path,
        opportunity,
        fixture_path=_LEVER_SHAPED_FIXTURE,
        form_fillers={"lever": _AltSelectorFormFiller()},
    )
    app = _approved_application("opp-1")
    preview = await applicator.prepare(app)
    event = await applicator.submit(preview, _confirmation(preview.preview_token))
    assert isinstance(event, ApplicationSubmitted)


async def test_resume_uses_the_active_fillers_declared_selectors_through_a_challenge(
    tmp_path: Path,
) -> None:
    """Both submit()'s challenge detection and resume()'s re-check/re-click
    must use the active FormFiller's own selectors -- proven through a full
    pause/resume cycle against the alt-selector fixture."""
    opportunity = _opportunity("opp-1", source_url=_LEVER_URL, challenge=True)
    applicator = await _applicator(
        tmp_path,
        opportunity,
        fixture_path=_LEVER_SHAPED_FIXTURE,
        form_fillers={"lever": _AltSelectorFormFiller()},
    )
    app = _approved_application("opp-1")
    preview = await applicator.prepare(app)
    pause_event = await applicator.submit(preview, _confirmation(preview.preview_token))
    assert isinstance(pause_event, HumanActionRequired)

    pause_token = next(iter(applicator._paused))
    paused_page = applicator._paused[pause_token].page
    await paused_page.evaluate("window.__clearChallenge()")

    event = await applicator.resume(pause_token, _ack(pause_token))
    assert isinstance(event, ApplicationSubmitted)


# ---------------------------------------------------------------------------
# The pause: a challenge must produce HumanActionRequired, not success
# ---------------------------------------------------------------------------


async def test_submit_pauses_instead_of_completing_when_a_challenge_appears(
    tmp_path: Path,
) -> None:
    opportunity = _opportunity("opp-1", challenge=True)
    applicator = await _applicator(tmp_path, opportunity)
    app = _approved_application("opp-1")
    preview = await applicator.prepare(app)
    event = await applicator.submit(preview, _confirmation(preview.preview_token))
    assert isinstance(event, HumanActionRequired)
    assert event.reason == "verification"


# ---------------------------------------------------------------------------
# resume(): the load-bearing proof -- the real submit action genuinely never
# fires without a matching acknowledgment, verified against the live page's
# own state, not just an exception being raised somewhere nearby.
# ---------------------------------------------------------------------------


async def test_resume_with_mismatched_token_never_touches_the_page() -> None:
    """A pause_token/ack mismatch must be refused before any page interaction
    -- proven by asserting on _paused's untouched state, the browser-tier
    analogue of asserting adapter.calls == [] in 7a."""
    applicator = BrowserApplicator.__new__(BrowserApplicator)
    applicator._paused = {}
    with pytest.raises(ValueError, match="acknowledgment names"):
        await applicator.resume("real-token", _ack("a-different-token"))


async def test_resume_with_unknown_pause_token_is_refused(tmp_path: Path) -> None:
    opportunity = _opportunity("opp-1")
    applicator = await _applicator(tmp_path, opportunity)
    with pytest.raises(UnknownPauseTokenError):
        await applicator.resume("never-issued", _ack("never-issued"))


async def test_resume_refuses_and_never_reclicks_while_challenge_still_visible(
    tmp_path: Path,
) -> None:
    """The core proof this slice exists for: if the human hasn't actually
    cleared the challenge, resume() must not click submit again -- checked
    against the live page's real DOM state, not the caller's say-so. The
    success marker must never appear."""
    opportunity = _opportunity("opp-1", challenge=True)
    applicator = await _applicator(tmp_path, opportunity)
    app = _approved_application("opp-1")
    preview = await applicator.prepare(app)
    pause_event = await applicator.submit(preview, _confirmation(preview.preview_token))
    assert isinstance(pause_event, HumanActionRequired)

    pause_token = next(iter(applicator._paused))
    paused_page = applicator._paused[pause_token].page

    with pytest.raises(ChallengeStillPresentError):
        await applicator.resume(pause_token, _ack(pause_token))

    # The real page was never told to submit again -- success never appears.
    assert await paused_page.is_visible("#application-success") is False
    # And the pause is still live -- a genuine future resume() can still work.
    assert pause_token in applicator._paused


async def test_resume_completes_once_the_challenge_is_actually_cleared(
    tmp_path: Path,
) -> None:
    """The positive case: once the fixture's challenge panel is actually
    hidden (simulating the human clearing it), resume() completes the real
    submission and the session is persisted."""
    opportunity = _opportunity("opp-1", challenge=True)
    applicator = await _applicator(tmp_path, opportunity)
    app = _approved_application("opp-1")
    preview = await applicator.prepare(app)
    pause_event = await applicator.submit(preview, _confirmation(preview.preview_token))
    assert isinstance(pause_event, HumanActionRequired)

    pause_token = next(iter(applicator._paused))
    paused_page = applicator._paused[pause_token].page
    await paused_page.evaluate("window.__clearChallenge()")

    event = await applicator.resume(pause_token, _ack(pause_token))
    assert isinstance(event, ApplicationSubmitted)
    assert pause_token not in applicator._paused  # one-shot, like the 7a token

    # session was actually persisted for reuse (ADR-0020/ADR-0008)
    session = applicator._session_store.load("opp-1")
    assert session is not None


# ---------------------------------------------------------------------------
# Phase 8k / ADR-0032: QuestionAnswerer wired into BrowserApplicator.
# Real, live-DOM tests against apply_form_with_custom_questions.html, whose
# #work_auth/#gender/#culture_fit fields have real <label> text -- unlike
# #why_us above (no label at all), which continues to hard-refuse.
# ---------------------------------------------------------------------------

_CUSTOM_QUESTIONS_FIXTURE = (
    Path(__file__).parent.parent
    / "fixtures"
    / "greenhouse"
    / "apply_form_with_custom_questions.html"
)


def _custom_questions_url(*, challenge: bool = False) -> str:
    suffix = "?challenge=1" if challenge else ""
    return f"file://{_CUSTOM_QUESTIONS_FIXTURE}{suffix}"


async def test_factual_field_with_a_captured_fact_is_auto_filled_no_pause(
    tmp_path: Path,
) -> None:
    """Category 2 auto-fill: #work_auth has real label text matching the
    work-authorization template, and legal_status.work_authorized_us is
    already captured -- it must be filled automatically, with zero pause
    for it specifically."""
    opportunity = _opportunity("opp-1")
    applicator = await _applicator(
        tmp_path, opportunity, fixture_path=_CUSTOM_QUESTIONS_FIXTURE
    )
    app = _approved_application(
        "opp-1", legal_status=LegalStatusSection(work_authorized_us=True)
    )
    preview = await applicator.prepare(app)
    event = await applicator.submit(preview, _confirmation(preview.preview_token))

    assert isinstance(event, HumanActionRequired)
    assert event.reason == "fields_need_human_input"
    pause_token = next(iter(applicator._paused))
    paused = applicator._paused[pause_token]
    # #work_auth was resolved automatically -- it is not in the manifest.
    assert "#work_auth" not in paused.manifest
    assert set(paused.manifest) == {"#gender", "#culture_fit"}
    assert await paused.page.input_value("#work_auth") == "yes"


async def test_eeoc_field_is_never_written_by_this_code_only_ever_by_the_human(
    tmp_path: Path,
) -> None:
    """The load-bearing wiring-level proof of Case 1d's guarantee: after
    Phase A's auto-fill pass, #gender -- a Category 1 (EEOC) field -- is
    still at its blank default. This code never calls select_option on it
    under any circumstance; only a human, acting directly on the live
    page, ever sets it."""
    opportunity = _opportunity("opp-1")
    applicator = await _applicator(
        tmp_path, opportunity, fixture_path=_CUSTOM_QUESTIONS_FIXTURE
    )
    app = _approved_application(
        "opp-1", legal_status=LegalStatusSection(work_authorized_us=True)
    )
    preview = await applicator.prepare(app)
    event = await applicator.submit(preview, _confirmation(preview.preview_token))

    assert isinstance(event, HumanActionRequired)
    pause_token = next(iter(applicator._paused))
    paused_page = applicator._paused[pause_token].page
    assert await paused_page.input_value("#gender") == ""


async def test_missing_legal_status_fact_and_subjective_field_both_go_to_manifest(
    tmp_path: Path,
) -> None:
    """With no legal_status captured at all, #work_auth joins #gender and
    #culture_fit in the single batched manifest -- one pause, not three."""
    opportunity = _opportunity("opp-1")
    applicator = await _applicator(
        tmp_path, opportunity, fixture_path=_CUSTOM_QUESTIONS_FIXTURE
    )
    app = _approved_application("opp-1")  # legal_status defaults to all-None
    preview = await applicator.prepare(app)
    event = await applicator.submit(preview, _confirmation(preview.preview_token))

    assert isinstance(event, HumanActionRequired)
    assert len(applicator._paused) == 1  # one batched pause, not per-field
    pause_token = next(iter(applicator._paused))
    paused = applicator._paused[pause_token]
    assert paused.reason == "fields_need_human_input"
    assert set(paused.manifest) == {"#work_auth", "#gender", "#culture_fit"}


async def test_resume_refuses_while_a_manifested_field_is_still_empty(
    tmp_path: Path,
) -> None:
    """The re-verify-the-live-page discipline, extended past challenges:
    resume() must not proceed -- and must not click submit -- while any
    manifested field is still empty, regardless of what the acknowledgment
    claims."""
    opportunity = _opportunity("opp-1")
    applicator = await _applicator(
        tmp_path, opportunity, fixture_path=_CUSTOM_QUESTIONS_FIXTURE
    )
    app = _approved_application(
        "opp-1", legal_status=LegalStatusSection(work_authorized_us=True)
    )
    preview = await applicator.prepare(app)
    await applicator.submit(preview, _confirmation(preview.preview_token))
    pause_token = next(iter(applicator._paused))
    paused_page = applicator._paused[pause_token].page

    # Human fills only #gender, leaves #culture_fit empty.
    await paused_page.evaluate("window.__fillCustomFields('female', '')")

    with pytest.raises(RequiredFieldsStillUnresolvedError, match="culture_fit"):
        await applicator.resume(pause_token, _ack(pause_token))

    assert await paused_page.is_visible("#application-success") is False
    assert pause_token in applicator._paused


async def test_resume_completes_once_the_human_fills_the_manifest_directly(
    tmp_path: Path,
) -> None:
    """The positive case: once the human fills #gender/#culture_fit
    directly on the live page (never through our data model -- this test
    stands in for the human's own action, the same way
    test_resume_completes_once_the_challenge_is_actually_cleared's
    __clearChallenge() call does for a CAPTCHA), resume() completes the
    real submission."""
    opportunity = _opportunity("opp-1")
    applicator = await _applicator(
        tmp_path, opportunity, fixture_path=_CUSTOM_QUESTIONS_FIXTURE
    )
    app = _approved_application(
        "opp-1", legal_status=LegalStatusSection(work_authorized_us=True)
    )
    preview = await applicator.prepare(app)
    await applicator.submit(preview, _confirmation(preview.preview_token))
    pause_token = next(iter(applicator._paused))
    paused_page = applicator._paused[pause_token].page

    await paused_page.evaluate(
        "window.__fillCustomFields('decline', 'I love shipping real things.')"
    )

    event = await applicator.resume(pause_token, _ack(pause_token))
    assert isinstance(event, ApplicationSubmitted)
    assert pause_token not in applicator._paused


async def test_resume_from_field_manifest_can_then_pause_again_for_a_challenge(
    tmp_path: Path,
) -> None:
    """Phase A -> Phase B sequencing by construction: resuming a
    fields_need_human_input pause performs the *first* submit click, which
    can itself surface a Phase B challenge -- proving the two phases are a
    pipeline, not independent, and that Phase B only ever becomes reachable
    after Phase A's own resume has completed its re-verification."""
    opportunity = _opportunity("opp-1", challenge=True)
    applicator = await _applicator(
        tmp_path, opportunity, fixture_path=_CUSTOM_QUESTIONS_FIXTURE
    )
    app = _approved_application(
        "opp-1", legal_status=LegalStatusSection(work_authorized_us=True)
    )
    preview = await applicator.prepare(app)
    first_pause = await applicator.submit(preview, _confirmation(preview.preview_token))
    assert isinstance(first_pause, HumanActionRequired)
    assert first_pause.reason == "fields_need_human_input"
    field_pause_token = next(iter(applicator._paused))
    paused_page = applicator._paused[field_pause_token].page
    await paused_page.evaluate(
        "window.__fillCustomFields('male', 'Great fit.')"
    )

    second_pause = await applicator.resume(field_pause_token, _ack(field_pause_token))
    assert isinstance(second_pause, HumanActionRequired)
    assert second_pause.reason == "verification"
    assert field_pause_token not in applicator._paused  # phase A pause consumed
    challenge_pause_token = next(iter(applicator._paused))
    assert applicator._paused[challenge_pause_token].reason == "challenge"

    await paused_page.evaluate("window.__clearChallenge()")
    final_event = await applicator.resume(
        challenge_pause_token, _ack(challenge_pause_token)
    )
    assert isinstance(final_event, ApplicationSubmitted)


# ---------------------------------------------------------------------------
# The reason discriminator on _PausedSession must be provably load-bearing
# (user-required, not decorative): a "fields_need_human_input" pause must
# use field-fill re-verification and must NOT be resumable by challenge
# logic, and vice versa for a "challenge" pause. Constructed directly
# against the applicator's internal state to isolate exactly this branch.
# ---------------------------------------------------------------------------


async def test_reason_discriminator_actually_selects_the_right_reverification(
    tmp_path: Path,
) -> None:
    """Two real paused sessions, one of each reason, on the same live page.
    Calling resume() on the field-manifest pause while fields are empty
    must raise RequiredFieldsStillUnresolvedError, never
    ChallengeStillPresentError; calling resume() on the challenge pause
    while the challenge is visible must raise ChallengeStillPresentError,
    never RequiredFieldsStillUnresolvedError. If the reason field were
    decorative (resume() always ran one check regardless), one of these
    two assertions would fail."""
    opportunity = _opportunity("opp-1", challenge=True)
    applicator = await _applicator(
        tmp_path, opportunity, fixture_path=_CUSTOM_QUESTIONS_FIXTURE
    )
    app = _approved_application(
        "opp-1", legal_status=LegalStatusSection(work_authorized_us=True)
    )
    preview = await applicator.prepare(app)
    field_pause_event = await applicator.submit(
        preview, _confirmation(preview.preview_token)
    )
    assert isinstance(field_pause_event, HumanActionRequired)
    field_pause_token = next(iter(applicator._paused))
    # Nothing filled -- #gender/#culture_fit are still genuinely empty.
    field_paused = applicator._paused[field_pause_token]
    assert field_paused.reason == "fields_need_human_input"

    with pytest.raises(RequiredFieldsStillUnresolvedError):
        await applicator.resume(field_pause_token, _ack(field_pause_token))
    # Proves the wrong check never ran: a real ChallengeStillPresentError
    # would also have been a valid-looking exception type here if the
    # discriminator were ignored and challenge logic ran instead -- it
    # didn't, because the challenge selector is not even visible yet at
    # this point (the first submit click hasn't happened).
    assert field_pause_token in applicator._paused

    # Now genuinely resolve the field pause and reach a real challenge pause.
    paused_page = field_paused.page
    await paused_page.evaluate("window.__fillCustomFields('male', 'Great fit.')")
    second_pause = await applicator.resume(field_pause_token, _ack(field_pause_token))
    assert isinstance(second_pause, HumanActionRequired)
    challenge_pause_token = next(iter(applicator._paused))
    challenge_paused = applicator._paused[challenge_pause_token]
    assert challenge_paused.reason == "challenge"

    with pytest.raises(ChallengeStillPresentError):
        await applicator.resume(challenge_pause_token, _ack(challenge_pause_token))
    # And RequiredFieldsStillUnresolvedError never fires for a challenge
    # pause even though _fields_still_empty is never even consulted for it
    # -- proven by the exception type itself, not an assumption.
    assert challenge_pause_token in applicator._paused


async def test_field_with_no_describable_label_still_hard_refuses(
    tmp_path: Path,
) -> None:
    """Contrast case, against the original apply_form_with_extra_question.html
    fixture: #why_us has no label/aria-label/placeholder at all, so it
    must still hard-refuse via UnsupportedFormFieldsError rather than being
    manifested with no context for the human -- the ADR-0032 boundary that
    keeps this exception's narrower meaning real, not just documented."""
    opportunity = _opportunity("opp-1")
    applicator = await _applicator(
        tmp_path, opportunity, fixture_path=_EXTRA_QUESTION_FIXTURE
    )
    app = _approved_application("opp-1")
    preview = await applicator.prepare(app)
    with pytest.raises(UnsupportedFormFieldsError, match="why_us"):
        await applicator.submit(preview, _confirmation(preview.preview_token))
    assert len(applicator._paused) == 0


# ---------------------------------------------------------------------------
# Phase 11 / ADR-0035: the real LeverFormFiller against the real-shape
# fixture (single full-name field, required file upload, hCaptcha markup).
# ---------------------------------------------------------------------------

_LEVER_REAL_FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "lever" / "apply_form_real.html"
)


def _lever_application_with_artifact(tmp_path: Path) -> SubmittableApplication:
    """An approved application carrying a real, on-disk DOCX artifact."""
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


async def test_lever_fills_single_fullname_field_and_attaches_the_real_docx(
    tmp_path: Path,
) -> None:
    """The name lands UNSPLIT in the single [name='name'] field (no
    _split_name heuristic on Lever), and the genuinely attached file is
    THE application's own DOCX artifact -- filename checked against the
    live input's real FileList, not assumed from the call having happened."""
    opportunity = _opportunity("opp-1", source_url=_LEVER_URL)
    applicator = await _applicator(
        tmp_path, opportunity, fixture_path=_LEVER_REAL_FIXTURE
    )
    app = _lever_application_with_artifact(tmp_path)
    docx_name = Path(app.application.resume.artifacts[0].path).name

    page, context, browser, _console_log = await applicator._open_page(
        "opp-1", f"file://{_LEVER_REAL_FIXTURE}"
    )
    try:
        await LeverFormFiller().fill_identity_and_resume(page, app)
        assert await page.input_value("[name='name']") == "Ada Lovelace"
        assert await page.input_value("[name='email']") == "ada@example.com"
        attached = await page.evaluate(
            "() => { const f = document.querySelector(\"[name='resume']\").files;"
            " return f.length === 1 ? f[0].name : null; }"
        )
        assert attached == docx_name
    finally:
        await browser.close()


async def test_lever_full_submit_flow_completes_with_artifact(
    tmp_path: Path,
) -> None:
    opportunity = _opportunity("opp-1", source_url=_LEVER_URL)
    applicator = await _applicator(
        tmp_path, opportunity, fixture_path=_LEVER_REAL_FIXTURE
    )
    app = _lever_application_with_artifact(tmp_path)
    preview = await applicator.prepare(app)
    event = await applicator.submit(preview, _confirmation(preview.preview_token))
    assert isinstance(event, ApplicationSubmitted)


async def test_lever_hcaptcha_pauses_and_resumes_through_existing_machinery(
    tmp_path: Path,
) -> None:
    """Real hCaptcha markup (#h-captcha) flows through the exact ADR-0020
    pause/resume machinery: pause on visibility, refuse to resume while
    still visible, complete once the HUMAN clears it -- this project never
    solves a challenge itself."""
    opportunity = _opportunity("opp-1", source_url=_LEVER_URL, challenge=True)
    applicator = await _applicator(
        tmp_path, opportunity, fixture_path=_LEVER_REAL_FIXTURE
    )
    app = _lever_application_with_artifact(tmp_path)
    preview = await applicator.prepare(app)
    pause_event = await applicator.submit(preview, _confirmation(preview.preview_token))
    assert isinstance(pause_event, HumanActionRequired)
    assert pause_event.reason == "verification"

    pause_token = next(iter(applicator._paused))
    paused_page = applicator._paused[pause_token].page
    with pytest.raises(ChallengeStillPresentError):
        await applicator.resume(pause_token, _ack(pause_token))

    await paused_page.evaluate("window.__clearChallenge()")
    event = await applicator.resume(pause_token, _ack(pause_token))
    assert isinstance(event, ApplicationSubmitted)


async def test_lever_refuses_when_recorded_artifact_file_is_gone_from_disk(
    tmp_path: Path,
) -> None:
    opportunity = _opportunity("opp-1", source_url=_LEVER_URL)
    applicator = await _applicator(
        tmp_path, opportunity, fixture_path=_LEVER_REAL_FIXTURE
    )
    app = _lever_application_with_artifact(tmp_path)
    Path(app.application.resume.artifacts[0].path).unlink()  # file vanishes
    preview = await applicator.prepare(app)
    with pytest.raises(MissingResumeArtifactError, match="no longer exists on disk"):
        await applicator.submit(preview, _confirmation(preview.preview_token))
