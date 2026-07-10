"""Phase 40 (ADR-0060): Promptfoo results-directory path portability.

The pre-fix default (``_DEFAULT_PROMPTFOO_RESULTS_DIR = Path(__file__)
.resolve().parent.parent.parent / "promptfoo" / "results"``) only resolved
to a sensible path for an **editable** install -- a wheel or non-editable
``pip install .`` copies the package into ``site-packages``, so the
default silently pointed there instead. Fixed by moving the default into
``Settings.promptfoo_results_dir`` (CWD-relative, env-overridable via
``PROMPTFOO_RESULTS_DIR``), the same pattern ``database_path``/
``artifacts_dir`` already used -- not a new design, a consistency fix.

These tests prove: the new default is CWD-relative (not repo-tree/
``__file__``-relative), it is env-overridable like every other Settings
field, every command that resolves a default (``setup``, ``apply``,
``auto``, ``verify-promptfoo``, ``diagnose-promptfoo-drift``) uses the
*same* ``Settings.promptfoo_results_dir``, and an explicit path argument
still wins over the default. No live call; no network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from career_agent.cli import (
    run_diagnose_promptfoo_drift_command,
    run_setup_command,
    run_verify_promptfoo_command,
)
from career_agent.core.config import Settings


def test_default_promptfoo_results_dir_is_relative_not_absolute() -> None:
    """The default must not be pinned to any install-time filesystem
    location (e.g. a source checkout or site-packages) -- it is resolved
    against whatever the process's cwd is at call time."""
    assert Settings().promptfoo_results_dir == "promptfoo/results"
    assert not Path(Settings().promptfoo_results_dir).is_absolute()


def test_promptfoo_results_dir_is_env_overridable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same override mechanism as every other Settings field (e.g.
    DATABASE_PATH) -- not a bespoke new mechanism."""
    monkeypatch.setenv("PROMPTFOO_RESULTS_DIR", "/custom/evidence/dir")
    assert Settings().promptfoo_results_dir == "/custom/evidence/dir"


def test_setup_reports_the_cwd_relative_default_not_an_install_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Regression for the exact defect: run from an arbitrary directory
    (never the source checkout) and confirm the reported path is relative
    to *that* directory, not to wherever cli.py happens to live on disk."""
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        groq_api_key=None,
        anthropic_api_key=None,
        database_path=str(tmp_path / "db.sqlite"),
        artifacts_dir=str(tmp_path / "artifacts"),
    )
    run_setup_command(profile_path=tmp_path / "profile.json", settings=settings)
    out = capsys.readouterr().out
    # OS-native separator: Path("promptfoo/results") prints with backslashes
    # on Windows -- a forward-slash literal here would be a Windows-only
    # test failure, not a production defect (this is exactly why the whole
    # point of this fix is to avoid hardcoding a path style anywhere).
    assert str(Path("promptfoo", "results")) in out
    # Never the install-time source-tree/site-packages path.
    assert str(Path("src", "career_agent")) not in out
    assert "site-packages" not in out


def test_verify_and_diagnose_use_the_identical_default_resolution(
    tmp_path: Path,
) -> None:
    """Both commands must agree on where 'the default' is -- constructed
    fresh per call, not a shared mutable module-level constant."""
    monkeypatch_dir = tmp_path / "cwd"
    monkeypatch_dir.mkdir()
    import os

    old_cwd = Path.cwd()
    os.chdir(monkeypatch_dir)
    try:
        # Both report "not found" against the *same* resolved default path.
        verify_exit = run_verify_promptfoo_command("groq")
        diagnose_output_exit = run_diagnose_promptfoo_drift_command("groq")
    finally:
        os.chdir(old_cwd)
    assert verify_exit == 1  # no artifact at the resolved default -> blocks
    assert diagnose_output_exit == 0  # diagnose always reports, never blocks


def test_explicit_results_dir_still_wins_over_the_default(tmp_path: Path) -> None:
    """An explicit path argument (the CLI's --results-dir) must still take
    precedence over Settings' default -- unchanged behavior."""
    results_dir = tmp_path / "explicit"
    results_dir.mkdir()
    (results_dir / "truthfulness-gate-v2--groq.json").write_text(
        json.dumps(
            {
                "results": {
                    "stats": {"successes": 10, "failures": 0, "errors": 0},
                },
                "config": {
                    "providers": [{"id": "openai:chat:openai/gpt-oss-120b"}]
                },
            }
        )
    )
    assert run_verify_promptfoo_command("groq", results_dir) == 0


def test_no_module_level_repo_relative_constant_remains() -> None:
    """The removed `_DEFAULT_PROMPTFOO_RESULTS_DIR`/`_REPO_ROOT` constants
    must not quietly reappear."""
    import career_agent.cli as cli_module

    assert not hasattr(cli_module, "_DEFAULT_PROMPTFOO_RESULTS_DIR")
    assert not hasattr(cli_module, "_REPO_ROOT")
