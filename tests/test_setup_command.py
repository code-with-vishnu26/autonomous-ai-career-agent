"""Phase 25 / ADR-0051: the `career-agent setup` onboarding command.

Deterministic, fully offline. Proves the scaffold round-trips through the
real loader, never overwrites an existing profile, and that the readiness
report + next-action are computed correctly from state -- with no network,
no LLM, and no secret printed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from career_agent.cli import run_setup_command
from career_agent.core.config import Settings
from career_agent.storage.profile import (
    example_profile_dict,
    load_master_profile,
    write_profile_scaffold,
)


def _no_key_settings(tmp_path: Path) -> Settings:
    """A Settings with no provider keys and tmp data paths (no .env leakage)."""
    return Settings(
        groq_api_key=None,
        anthropic_api_key=None,
        database_path=str(tmp_path / "db.sqlite"),
        artifacts_dir=str(tmp_path / "artifacts"),
    )


def test_example_profile_scaffold_round_trips_through_the_real_loader(
    tmp_path: Path,
) -> None:
    """The scaffold is the exact shape load_master_profile accepts -- it can
    never silently drift into an unloadable form."""
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(example_profile_dict()), encoding="utf-8")
    profile = load_master_profile(path)
    assert profile.basics.name == "Your Name"
    assert profile.work[0].id == "work-1"
    assert profile.version  # a content hash was computed


def test_write_scaffold_creates_a_file_and_refuses_to_overwrite(
    tmp_path: Path,
) -> None:
    path = tmp_path / "profile.json"
    assert write_profile_scaffold(path) is True
    original = path.read_text(encoding="utf-8")

    # A second call must not touch a now-existing (possibly real) profile.
    assert write_profile_scaffold(path) is False
    assert path.read_text(encoding="utf-8") == original


def test_setup_scaffolds_when_missing_and_reports_todo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    profile_path = tmp_path / "profile.json"
    exit_code = run_setup_command(
        profile_path=profile_path,
        settings=_no_key_settings(tmp_path),
        promptfoo_results_dir=tmp_path / "no-results",
    )
    assert exit_code == 0
    assert profile_path.exists()  # scaffold written
    out = capsys.readouterr().out
    assert "wrote a starter profile" in out
    # A freshly-scaffolded (placeholder) profile is not "ready".
    assert "[todo]  Profile" in out
    assert "Next: Edit" in out


def test_setup_never_overwrites_an_existing_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(example_profile_dict()), encoding="utf-8"
    )
    marker = profile_path.read_text(encoding="utf-8")

    run_setup_command(
        profile_path=profile_path,
        settings=_no_key_settings(tmp_path),
        promptfoo_results_dir=tmp_path / "no-results",
    )
    assert profile_path.read_text(encoding="utf-8") == marker  # untouched


def test_setup_reports_ready_profile_but_missing_key_points_at_key_step(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(example_profile_dict()), encoding="utf-8"
    )
    run_setup_command(
        profile_path=profile_path,
        settings=_no_key_settings(tmp_path),
        promptfoo_results_dir=tmp_path / "no-results",
    )
    out = capsys.readouterr().out
    assert "[ready] Profile" in out
    assert "[todo]  LLM provider key" in out
    assert "Set GROQ_API_KEY" in out


def test_setup_all_green_points_at_discover_and_never_prints_the_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(example_profile_dict()), encoding="utf-8"
    )
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "truthfulness-gate-v2--groq.json").write_text("{}", encoding="utf-8")
    settings = Settings(
        groq_api_key="gsk-secret-value-should-never-print",
        anthropic_api_key=None,
        database_path=str(tmp_path / "db.sqlite"),
        artifacts_dir=str(tmp_path / "artifacts"),
    )

    run_setup_command(
        profile_path=profile_path,
        settings=settings,
        promptfoo_results_dir=results_dir,
    )
    out = capsys.readouterr().out
    assert "[ready] Profile" in out
    assert "[ready] LLM provider key" in out
    assert "[ready] Promptfoo validation" in out
    assert "career-agent discover --profile" in out
    # The actual secret value must never appear in output.
    assert "gsk-secret-value-should-never-print" not in out


def test_setup_reports_an_unloadable_profile_without_crashing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    profile_path = tmp_path / "profile.json"
    profile_path.write_text("{ this is not valid json", encoding="utf-8")
    exit_code = run_setup_command(
        profile_path=profile_path,
        settings=_no_key_settings(tmp_path),
        promptfoo_results_dir=tmp_path / "no-results",
    )
    assert exit_code == 0  # advisory, never raises
    out = capsys.readouterr().out
    assert "does not load yet" in out
    assert "[todo]  Profile" in out


def test_main_dispatches_setup_with_the_default_profile_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import career_agent.cli as cli_module

    seen: dict[str, Path] = {}

    def _fake_run_setup_command(*, profile_path: Path) -> int:
        seen["profile_path"] = profile_path
        return 0

    monkeypatch.setattr(cli_module, "run_setup_command", _fake_run_setup_command)
    with pytest.raises(SystemExit) as exc_info:
        cli_module.main(["setup"])
    assert exc_info.value.code == 0
    assert seen["profile_path"] == Path("profile.json")  # documented default
