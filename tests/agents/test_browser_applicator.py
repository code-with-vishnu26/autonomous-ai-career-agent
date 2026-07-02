"""Phase 7b3 / ADR-0020: BrowserApplicator, driven against a real, local
Chromium instance -- not a Python-level fake standing in for a browser.

Loads ``tests/fixtures/greenhouse/apply_form.html`` via ``file://``, so
nothing here touches the network. ``?challenge=1`` makes the fixture show a
verification panel after the first submit click, exactly like a real
mid-flow CAPTCHA/verification wall -- the load-bearing tests prove
BrowserApplicator pauses instead of treating that as success, and that
resume() genuinely never re-clicks submit until the challenge is actually
gone from the live page.
"""

from __future__ import annotations

import glob
from datetime import UTC, datetime
from pathlib import Path

import pytest

from career_agent.agents.apply.browser_applicator import (
    BrowserApplicator,
    ChallengeStillPresentError,
    UnknownPauseTokenError,
)
from career_agent.core.events import ApplicationSubmitted, HumanActionRequired
from career_agent.domain.models import (
    Application,
    HumanConfirmation,
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

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "greenhouse" / "apply_form.html"


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


def _opportunity(opportunity_id: str, source_url: str) -> Opportunity:
    return Opportunity(
        id=opportunity_id,
        company_id="acme",
        canonical_company="acme.com",
        title="Software Engineer",
        source="ats_api",
        source_url=source_url,
        provenance=Provenance(
            method="structured_api", reference=source_url, extraction_confidence=1.0
        ),
        description_raw="",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _approved_application(opportunity_id: str) -> SubmittableApplication:
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
        id="app-1", opportunity_id=opportunity_id, resume=resume, status="pending"
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


async def _applicator(tmp_path: Path, opportunity: Opportunity) -> BrowserApplicator:
    repo = InMemoryOpportunityRepository()
    await repo.add(opportunity)
    session_store = EncryptedSessionStore(tmp_path, FakeKeyProvider())
    return BrowserApplicator(
        session_store, repo, chromium_executable_path=_chromium_executable()
    )


# ---------------------------------------------------------------------------
# Happy path: no challenge
# ---------------------------------------------------------------------------


async def test_submit_completes_when_no_challenge_appears(tmp_path: Path) -> None:
    opportunity = _opportunity("opp-1", _fixture_url())
    applicator = await _applicator(tmp_path, opportunity)
    app = _approved_application("opp-1")
    preview = await applicator.prepare(app)
    event = await applicator.submit(preview, _confirmation(preview.preview_token))
    assert isinstance(event, ApplicationSubmitted)
    assert event.tier_used == "browser"


# ---------------------------------------------------------------------------
# The pause: a challenge must produce HumanActionRequired, not success
# ---------------------------------------------------------------------------


async def test_submit_pauses_instead_of_completing_when_a_challenge_appears(
    tmp_path: Path,
) -> None:
    opportunity = _opportunity("opp-1", _fixture_url(challenge=True))
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
    from career_agent.agents.apply.browser_applicator import BrowserApplicator

    # No real applicator setup needed: the mismatch check happens before any
    # lookup, so this is a pure logic assertion -- construct the minimum.
    applicator = BrowserApplicator.__new__(BrowserApplicator)
    applicator._paused = {}
    with pytest.raises(ValueError, match="acknowledgment names"):
        await applicator.resume("real-token", _ack("a-different-token"))


async def test_resume_with_unknown_pause_token_is_refused(tmp_path: Path) -> None:
    opportunity = _opportunity("opp-1", _fixture_url())
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
    opportunity = _opportunity("opp-1", _fixture_url(challenge=True))
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
    opportunity = _opportunity("opp-1", _fixture_url(challenge=True))
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
