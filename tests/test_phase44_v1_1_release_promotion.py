"""Phase 44 (ADR-0062): v1.1.0 release-promotion drift guards.

Pins the facts the v1.1.0 promotion depends on -- the exact version string
(no pre-release suffix), the presence of the v1.1.0 release notes stating
the decision, that the v1.0.0 record was preserved (not rewritten), and
that this repo still commits no tag or publish step -- so a silent
regression fails a test instead of shipping unnoticed. No live call; no
network; no git-tag mutation (this file never creates, moves, or reads the
``v1.0.0`` tag).
"""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_version_is_exactly_v1_1_0_stable() -> None:
    """v1.1.0 is a stable minor release (ADR-0062), not a candidate."""
    installed = version("career-agent")
    assert installed == "1.1.0"
    assert "rc" not in installed
    assert "dev" not in installed


def test_pyproject_version_matches_installed_metadata() -> None:
    """The source of truth (pyproject) and the installed metadata agree --
    catches a bump applied to only one of them."""
    import tomllib

    data = tomllib.loads(
        (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert data["project"]["version"] == "1.1.0"


def test_v1_1_0_release_notes_exist_and_state_the_decision() -> None:
    notes = (_REPO_ROOT / "docs" / "release" / "v1.1.0-notes.md").read_text(
        encoding="utf-8"
    )
    assert "**GO**" in notes
    assert "v1.0.0" in notes  # documents what it was promoted from
    # The notes must be honest that the tag is a separate manual step, not
    # something already done or performed by the agent.
    assert "pending owner authorization" in notes


def test_v1_0_0_notes_preserved_and_not_rewritten() -> None:
    """The historical v1.0.0 record is never rewritten by a later release.
    ``**GO.**`` is the v1.0.0 decision marker frozen in that file."""
    v1_notes = (_REPO_ROOT / "docs" / "release" / "v1.0.0-notes.md").read_text(
        encoding="utf-8"
    )
    assert "**GO.**" in v1_notes
    assert "1.0.0rc1" in v1_notes


def test_readiness_audit_adr_exists() -> None:
    assert (
        _REPO_ROOT
        / "docs"
        / "adr"
        / "0062-v1-1-readiness-audit-and-version-decision.md"
    ).is_file()


def test_no_git_tag_or_publish_step_committed() -> None:
    """Tagging/publishing stays a manual, separate maintainer act -- no
    workflow in this repo creates or pushes a tag or uploads to PyPI."""
    ci_workflow = (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    lowered = ci_workflow.lower()
    assert "git tag" not in ci_workflow
    assert "push --tags" not in ci_workflow
    assert "pypi" not in lowered
    assert "twine upload" not in lowered
