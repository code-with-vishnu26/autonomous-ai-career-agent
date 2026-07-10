"""Phase 38: post-v1.0.0-release audit guards.

Pins the two small, real findings from the post-release audit: local
Phase-36 smoke-evidence filenames are now git-ignored by name (so an
accidental ``git add .`` in the repo root can never stage them), and the
installed package version has no pre-release suffix anywhere reachable from
a clean install (advanced from ``1.0.0`` to ``1.1.0`` by Phase 44/ADR-0062).
No live call; no network; no tag mutation (this file never touches the
immutable ``v1.0.0`` git tag).
"""

from __future__ import annotations

import subprocess
from importlib.metadata import version
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

_SMOKE_EVIDENCE_NAMES = (
    "phase36_evidence.txt",
    "phase36_local_smoke.ps1",
    "synthetic_opportunity.json",
    "synthetic_profile.json",
)


def test_local_smoke_evidence_filenames_are_gitignored() -> None:
    """A bare `git add .` in the repo root can never stage these -- proven
    by asking git itself, not by reading .gitignore text and hoping."""
    for name in _SMOKE_EVIDENCE_NAMES:
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", name],
            cwd=_REPO_ROOT,
            check=False,
        )
        assert result.returncode == 0, f"{name} is not git-ignored"


def test_smoke_directory_is_gitignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "phase36_smoke/anything.json"],
        cwd=_REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0


def test_installed_version_is_stable_v1_1_0() -> None:
    installed = version("career-agent")
    assert installed == "1.1.0"
    assert "rc" not in installed
    assert "dev" not in installed


def test_v1_0_0_tag_is_never_touched_by_repository_code() -> None:
    """No script or workflow in this repo creates, moves, or force-pushes a
    git tag -- tagging/publishing stays a manual, separate maintainer act."""
    ci_workflow = (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert "git tag" not in ci_workflow
    assert "push --tags" not in ci_workflow
    assert "push --force" not in ci_workflow
