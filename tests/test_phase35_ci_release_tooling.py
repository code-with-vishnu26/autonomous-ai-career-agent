"""Phase 35 (ADR-0057): CI and release-tooling guards.

Pins the pure logic of the release-artifact scripts CI depends on, and pins
the CI workflow's fail-closed shape (no ``continue-on-error``, no
referenced secret, both required OSes present, no live-call opt-in) -- so a
future edit that would quietly reintroduce a leaked artifact, a hidden
failure, or a secret-bearing job fails a test instead of shipping unnoticed.
No live call, no network, no subprocess is made by these tests.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    path = _REPO_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_verify = _load_script("verify_release_artifacts.py")


def test_real_env_file_is_forbidden_but_env_example_is_not() -> None:
    names = ["career_agent/x.py", ".env", ".env.example", "sub/.env"]
    bad = _verify._forbidden_entries(names, check_test_paths=False)
    assert ".env" in bad
    assert "sub/.env" in bad
    assert ".env.example" not in bad


def test_wheel_check_flags_test_paths_but_sdist_check_does_not() -> None:
    names = ["pkg/tests/test_x.py", "pkg/core.py"]
    assert _verify._forbidden_entries(names, check_test_paths=True) == [
        "pkg/tests/test_x.py"
    ]
    assert _verify._forbidden_entries(names, check_test_paths=False) == []


def test_database_and_spreadsheet_and_promptfoo_results_are_forbidden() -> None:
    names = [
        "data/career_agent.db",
        "export.xlsx",
        "promptfoo/results/groq.json",
        "career_agent/domain/models.py",
    ]
    bad = _verify._forbidden_entries(names, check_test_paths=False)
    assert "data/career_agent.db" in bad
    assert "export.xlsx" in bad
    assert "promptfoo/results/groq.json" in bad
    assert "career_agent/domain/models.py" not in bad


def test_smoke_test_wheel_script_is_importable_and_has_main() -> None:
    """Import-only check (no subprocess/venv creation is exercised here --
    that would make a real environment call, which is a full end-to-end
    concern proven by CI on every OS, not a unit test's job)."""
    module = _load_script("smoke_test_wheel.py")
    assert callable(module.main)


def test_ci_workflow_is_fail_closed_and_covers_both_required_oses() -> None:
    """Plain string checks, deliberately not a full YAML parse -- PyYAML is
    only a transitive dependency here, not a declared one, and this file's
    small, stable shape doesn't need a real parser to pin."""
    workflow_path = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert workflow_path.is_file()
    raw = workflow_path.read_text(encoding="utf-8")

    # No hidden-failure escape hatches (rules 16-17 of the Phase 35 brief).
    # Matched as a YAML key (with the colon), not merely as a substring --
    # this file's own explanatory prose legitimately mentions the phrase.
    assert "continue-on-error:" not in raw
    assert 'errors="ignore"' not in raw
    assert "errors='ignore'" not in raw

    assert "push:" in raw
    assert "pull_request:" in raw
    assert "ubuntu-latest" in raw
    assert "windows-latest" in raw

    # Minimal token scope: read-only, no write/publish capability granted.
    assert "permissions:" in raw
    assert "contents: read" in raw

    # No step references a secret -- a live/paid call structurally cannot
    # happen from this workflow (no key is ever available to it).
    assert "secrets." not in raw


def test_release_scripts_exist_and_are_referenced_by_ci() -> None:
    ci = (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    for script in ("verify_release_artifacts.py", "smoke_test_wheel.py"):
        assert (_REPO_ROOT / "scripts" / script).is_file()
        assert script in ci
