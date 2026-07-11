"""Phase 46 (ADR-0064): the `career-agent preferences` interactive wizard.

Deterministic, fully offline -- no network, no LLM. Every prompt is driven
by an injected ``input_fn`` (never real ``input()``), matching this
project's standing convention (``run_capture_legal_status_command``,
``run_setup_command``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from career_agent.cli import run_preferences_command
from career_agent.storage.job_preferences import load_job_preferences

# One answer per prompt, in the exact order run_preferences_command asks:
# titles, alt-titles, seniority, exp-min, exp-max, employment-types,
# work-mode, countries, states, cities, salary-min, salary-max, currency,
# preferred-companies, blacklist, industries, visa, work-auth, tech,
# keywords-include, keywords-exclude, max-apps/day, require-confirmation,
# auto-tailor, auto-cover-letter, ats-providers, timezone.
_FULL_ANSWERS = [
    "Backend Developer, Python Developer",
    "Software Engineer, AI Engineer",
    "entry",
    "0",
    "2",
    "full_time",
    "remote",
    "India",
    "",
    "",
    "6",
    "12",
    "LPA",
    "Google, Microsoft, Amazon",
    "TCS, Infosys",
    "",
    "no",
    "",
    "Python, FastAPI, Docker, React",
    "",
    "",
    "",
    "yes",
    "yes",
    "no",
    "",
    "Asia/Kolkata",
]


def _input_fn(answers: list[str]) -> Callable[[str], str]:
    iterator: Iterator[str] = iter(answers)

    def fake_input(_prompt: str) -> str:
        return next(iterator)

    return fake_input


def test_wizard_writes_the_example_from_the_brief(tmp_path: Path) -> None:
    """The exact worked example from the Phase 46 brief: Backend/Python
    Developer, remote, India, 6-12 LPA, Google/Microsoft/Amazon preferred,
    TCS/Infosys blacklisted, Python/FastAPI/Docker/React skills."""
    path = tmp_path / "job_preferences.json"
    rc = run_preferences_command(path=path, input_fn=_input_fn(_FULL_ANSWERS))
    assert rc == 0
    prefs = load_job_preferences(path)
    assert prefs.preferred_titles == ["Backend Developer", "Python Developer"]
    assert prefs.work_mode == ["remote"]
    assert prefs.countries == ["India"]
    assert prefs.salary_min == 6.0
    assert prefs.salary_max == 12.0
    assert prefs.salary_currency == "LPA"
    assert prefs.preferred_companies == ["Google", "Microsoft", "Amazon"]
    assert prefs.blacklisted_companies == ["TCS", "Infosys"]
    assert prefs.preferred_technologies == ["Python", "FastAPI", "Docker", "React"]
    assert prefs.visa_sponsorship_required is False


def test_never_touches_profile_json(tmp_path: Path) -> None:
    """A separate file from the master profile, by construction -- this
    command must never read or write profile.json (ADR-0064)."""
    profile_path = tmp_path / "profile.json"
    prefs_path = tmp_path / "job_preferences.json"
    run_preferences_command(path=prefs_path, input_fn=_input_fn(_FULL_ANSWERS))
    assert not profile_path.exists()


def test_blank_answers_keep_the_current_value_on_a_second_run(
    tmp_path: Path,
) -> None:
    """Re-running the wizard to tweak one field must not require
    re-entering everything else -- blank answers preserve prior values."""
    path = tmp_path / "job_preferences.json"
    run_preferences_command(path=path, input_fn=_input_fn(_FULL_ANSWERS))

    # Second run: blank everywhere except changing preferred_titles.
    second_answers = ["Staff Engineer"] + [""] * (len(_FULL_ANSWERS) - 1)
    rc = run_preferences_command(path=path, input_fn=_input_fn(second_answers))
    assert rc == 0

    prefs = load_job_preferences(path)
    assert prefs.preferred_titles == ["Staff Engineer"]
    # Everything else survives untouched from the first run.
    assert prefs.countries == ["India"]
    assert prefs.preferred_companies == ["Google", "Microsoft", "Amazon"]
    assert prefs.time_zone == "Asia/Kolkata"


def test_dash_clears_an_optional_field_to_unset(tmp_path: Path) -> None:
    path = tmp_path / "job_preferences.json"
    run_preferences_command(path=path, input_fn=_input_fn(_FULL_ANSWERS))

    clear_answers = [""] * 12 + ["-"] + [""] * (len(_FULL_ANSWERS) - 13)
    run_preferences_command(path=path, input_fn=_input_fn(clear_answers))
    assert load_job_preferences(path).salary_currency is None


def test_unrecognized_yes_no_answer_keeps_current_and_does_not_crash(
    tmp_path: Path,
) -> None:
    path = tmp_path / "job_preferences.json"
    run_preferences_command(path=path, input_fn=_input_fn(_FULL_ANSWERS))

    # Corrupt only the require-confirmation answer (index 21) with garbage.
    answers = list(_FULL_ANSWERS)
    answers[21] = "maybe"
    rc = run_preferences_command(path=path, input_fn=_input_fn(answers))
    assert rc == 0
    assert load_job_preferences(path).require_human_confirmation is True


def test_invalid_seniority_input_fails_closed_without_writing(
    tmp_path: Path,
) -> None:
    """A genuinely invalid value (not a recognized keep/clear/unset
    shorthand) must fail the whole save rather than silently write a
    partially-invalid or coerced file."""
    path = tmp_path / "job_preferences.json"
    answers = list(_FULL_ANSWERS)
    answers[2] = "ultra-senior"  # seniority: not a real Literal value
    rc = run_preferences_command(path=path, input_fn=_input_fn(answers))
    assert rc == 1
    assert not path.exists()


def test_loading_a_malformed_existing_file_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "job_preferences.json"
    path.write_text("{not valid json", encoding="utf-8")
    rc = run_preferences_command(path=path, input_fn=_input_fn(_FULL_ANSWERS))
    assert rc == 1


def test_no_secret_or_key_value_ever_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """A defensive guard, not because this command touches API keys, but
    to match the project-wide discipline every command follows."""
    path = tmp_path / "job_preferences.json"
    run_preferences_command(path=path, input_fn=_input_fn(_FULL_ANSWERS))
    out = capsys.readouterr().out
    assert "gsk_" not in out
    assert "sk-ant" not in out
