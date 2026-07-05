"""Phase 13 / ADR-0037: the first MasterProfile writer (legal-status capture).

The load-bearing guarantee, injection-verified: unrecognized input can
NEVER become an answer -- in either polarity. Skip/garbage leaves a fact
exactly as it was (None stays "never asked"). The writer touches only the
legal_status key; unmodeled JSON Resume sections survive byte-identical.
"""

from __future__ import annotations

import json
from pathlib import Path

from career_agent.cli import run_capture_legal_status_command
from career_agent.domain.models import LegalStatusSection
from career_agent.storage.profile import load_master_profile, save_legal_status

_PROFILE = {
    "basics": {"name": "Ada Lovelace", "email": "ada@example.com", "summary": "Eng."},
    "work": [
        {
            "id": "work-1",
            "name": "Techco",
            "position": "Engineer",
            "startDate": "2022-01-01",
        }
    ],
    "skills": [{"id": "skill-1", "name": "Python"}],
    # A JSON Resume section this project does not model at all -- must
    # survive the writer byte-identical.
    "awards": [{"title": "Best Debugger", "date": "2024-01-01"}],
}


def _write_profile(tmp_path: Path) -> Path:
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(_PROFILE))
    return path


def test_save_legal_status_round_trips_and_preserves_unmodeled_sections(
    tmp_path: Path,
) -> None:
    path = _write_profile(tmp_path)
    before = load_master_profile(path)
    assert before.legal_status.work_authorized_us is None

    save_legal_status(
        path, LegalStatusSection(work_authorized_us=True, requires_sponsorship=None)
    )
    after = load_master_profile(path)
    assert after.legal_status.work_authorized_us is True
    assert after.legal_status.requires_sponsorship is None  # null stayed null
    assert after.version != before.version  # content hash naturally moved

    raw = json.loads(path.read_text())
    assert raw["awards"] == _PROFILE["awards"]  # unmodeled section untouched
    assert raw["work"] == _PROFILE["work"]


def test_capture_flow_yes_and_skip(tmp_path: Path) -> None:
    path = _write_profile(tmp_path)
    answers = iter(["yes", "skip"])
    code = run_capture_legal_status_command(
        path, input_fn=lambda _prompt: next(answers)
    )
    assert code == 0
    profile = load_master_profile(path)
    assert profile.legal_status.work_authorized_us is True
    assert profile.legal_status.requires_sponsorship is None  # skip = never asked


def test_unrecognized_input_never_becomes_an_answer(tmp_path: Path) -> None:
    """The no-default guarantee: garbage and empty input leave the fact
    exactly as it was -- None stays None, and an existing captured value
    is not clobbered either."""
    path = _write_profile(tmp_path)
    answers = iter(["definitely!", ""])
    run_capture_legal_status_command(path, input_fn=lambda _prompt: next(answers))
    profile = load_master_profile(path)
    assert profile.legal_status.work_authorized_us is None
    assert profile.legal_status.requires_sponsorship is None

    # Pre-captured value + garbage input: the value survives unchanged.
    save_legal_status(path, LegalStatusSection(work_authorized_us=False))
    answers = iter(["whatever", "nope?"])
    run_capture_legal_status_command(path, input_fn=lambda _prompt: next(answers))
    profile = load_master_profile(path)
    assert profile.legal_status.work_authorized_us is False  # not flipped
    assert profile.legal_status.requires_sponsorship is None


def test_no_becomes_a_real_captured_false_not_a_default(tmp_path: Path) -> None:
    path = _write_profile(tmp_path)
    answers = iter(["no", "no"])
    run_capture_legal_status_command(path, input_fn=lambda _prompt: next(answers))
    profile = load_master_profile(path)
    # An explicit "no" is a genuine captured answer -- distinct from None.
    assert profile.legal_status.work_authorized_us is False
    assert profile.legal_status.requires_sponsorship is False
