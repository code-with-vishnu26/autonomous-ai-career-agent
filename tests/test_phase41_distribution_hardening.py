"""Phase 41: installed-package and distribution hardening guards.

Two real findings, both from actually building fresh artifacts and
inspecting them, not from assumption:

1. hatchling's default sdist packaging includes anything not explicitly
   ``.gitignore``d -- untracked-but-not-ignored is not the same as
   excluded. ``.claude/`` (this agent's own local session state) and
   ``.import_linter_cache/`` were neither git-tracked nor in
   ``.gitignore``, so they leaked into a real built sdist. Fixed by
   ignoring both; a positive top-level allowlist in
   ``scripts/verify_release_artifacts.py`` now fails closed on any future
   unanticipated top-level entry, since a suffix/fragment blocklist can
   never catch a directory it doesn't already know about.
2. The ``classifiers`` list still said ``Development Status :: 2 -
   Pre-Alpha`` after a tagged, CI-green v1.0.0 stable release.

No live call; no network beyond what a normal ``pip install`` from a
local sdist needs (build isolation), which this file does not invoke.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verify_release_artifacts import (  # noqa: E402
    _SDIST_ALLOWED_TOP_LEVEL,
    _sdist_top_level_violations,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_sdist_allowlist_rejects_an_unanticipated_top_level_entry() -> None:
    """Direct regression for the exact leak: a local, untracked,
    non-gitignored directory must fail closed, not silently pass."""
    names = [
        "career_agent-1.0.0/README.md",
        "career_agent-1.0.0/.claude/scheduled_tasks.lock",
    ]
    violations = _sdist_top_level_violations(names)
    assert ".claude" in violations
    assert "README.md" not in violations


def test_sdist_allowlist_accepts_every_currently_legitimate_entry() -> None:
    names = [f"career_agent-1.0.0/{entry}" for entry in _SDIST_ALLOWED_TOP_LEVEL]
    assert _sdist_top_level_violations(names) == []


def test_claude_and_import_linter_cache_are_gitignored() -> None:
    import subprocess

    for path in (".claude", ".import_linter_cache"):
        # Trailing slash is required: both .gitignore entries are
        # directory-only patterns, and git check-ignore cannot confirm a
        # directory-only match for a path that doesn't exist on disk in
        # the current checkout unless the query path itself ends in "/".
        # Locally this directory may exist (agent session state); on a
        # fresh CI checkout it never does, so the bare name silently
        # fails to match even though the pattern is correct.
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", f"{path}/"],
            cwd=_REPO_ROOT,
            check=False,
        )
        assert result.returncode == 0, f"{path} is not git-ignored"


def test_classifier_reflects_the_actual_stable_release_state() -> None:
    """The v1.0.0 tag + green CI already prove production-stable, not
    pre-alpha -- packaging metadata must agree with that reality."""
    data = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    classifiers = data["project"]["classifiers"]
    assert "Development Status :: 5 - Production/Stable" in classifiers
    assert not any("Pre-Alpha" in c or "Alpha" in c for c in classifiers)


def test_distribution_name_import_name_and_cli_name_are_correctly_distinct() -> (
    None
):
    """Repo name, PyPI distribution name, import package name, and CLI
    executable name are four different strings by design -- pin all four
    so a future edit can't silently conflate them."""
    data = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["name"] == "career-agent"  # PyPI distribution name
    assert data["project"]["scripts"] == {"career-agent": "career_agent.cli:main"}
    assert (_REPO_ROOT / "src" / "career_agent").is_dir()  # import package name
    # The repo name itself (autonomous-ai-career-agent) is none of the above.
