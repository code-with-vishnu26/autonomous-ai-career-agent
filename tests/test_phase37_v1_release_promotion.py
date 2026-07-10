"""Phase 37 (ADR-0059): v1.0.0 release-promotion drift guards.

Pins the facts the v1.0.0 GO decision depends on -- the exact version
string (no ``-rc`` suffix), the presence of the final release notes and
this ADR, and that the historical rc1 record was preserved (not rewritten)
-- so a silent regression (an accidental version bump back to a
pre-release suffix, a deleted release-notes file, an edited historical
ADR) fails a test instead of shipping unnoticed. No live call; no network.
"""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_release_version_has_no_prerelease_suffix() -> None:
    """The current release is stable, not a release candidate. Advanced from
    v1.0.0 to v1.1.0 by Phase 44/ADR-0062 (still no ``-rc`` suffix)."""
    installed = version("career-agent")
    assert installed == "1.1.0"
    assert "rc" not in installed


def test_final_release_notes_exist_and_state_go() -> None:
    notes = (_REPO_ROOT / "docs" / "release" / "v1.0.0-notes.md").read_text(
        encoding="utf-8"
    )
    assert "**GO.**" in notes
    assert "1.0.0rc1" in notes  # documents what it was promoted from


def test_historical_rc1_notes_preserved_and_marked_superseded() -> None:
    """The historical record is never rewritten -- only a pointer is added.
    ``667 passed`` is the original Phase 34 baseline count frozen in that
    file; its presence proves the historical body text was not silently
    updated to match this phase's own (different) numbers."""
    rc1_notes = (
        _REPO_ROOT / "docs" / "release" / "v1.0.0-rc1-notes.md"
    ).read_text(encoding="utf-8")
    assert "Superseded" in rc1_notes
    assert "667 passed" in rc1_notes


def test_promotion_adr_exists() -> None:
    assert (
        _REPO_ROOT / "docs" / "adr" / "0059-v1-0-0-release-promotion.md"
    ).is_file()


def test_no_git_tag_or_publish_artifact_committed() -> None:
    """This phase explicitly does not tag or publish -- that's a manual,
    separate maintainer action, never something a phase does on its own."""
    ci_workflow = (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert "pypi" not in ci_workflow.lower()
    assert "twine upload" not in ci_workflow.lower()
