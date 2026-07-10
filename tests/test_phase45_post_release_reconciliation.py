"""Phase 45 (ADR-0063): post-release reconciliation drift guards.

Once v1.1.0 was genuinely tagged and its GitHub Release genuinely
published, the release notes (and the README Status) still carried the
pre-release "promotion prepared / pending owner authorization" wording that
was accurate only *before* the tag existed. Phase 45 reconciled that
documentation to the released reality and drew an explicit line between two
different things a reader can conflate:

- **software release state** = ``RELEASED`` (the tag + GitHub Release
  exist), and
- **product safety posture** = ``PREPARE_ONLY`` (the tool never submits to
  any external system).

These guards keep the corrected wording from silently regressing and keep
the two concepts from being collapsed back together. They read only
committed docs and package metadata -- no live call, no network, no git-tag
mutation.
"""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _v1_1_notes() -> str:
    return (_REPO_ROOT / "docs" / "release" / "v1.1.0-notes.md").read_text(
        encoding="utf-8"
    )


def test_v1_1_0_notes_no_longer_claim_tag_or_release_pending() -> None:
    """The stale pre-release wording must be gone now that the tag and
    Release genuinely exist."""
    notes = _v1_1_notes()
    assert "pending owner authorization" not in notes
    assert "Promotion prepared" not in notes


def test_v1_1_0_notes_state_released_software_but_prepare_only_posture() -> None:
    """The notes must assert the software is RELEASED while keeping the
    product's PREPARE_ONLY submission posture -- the two are distinct and
    must not be collapsed."""
    notes = _v1_1_notes()
    assert "RELEASED" in notes
    assert "PREPARE_ONLY" in notes
    # The reconciliation section records the real, verified release facts.
    assert "Post-release reconciliation" in notes


def test_readme_status_reflects_v1_1_0_released_not_v1_0_0() -> None:
    """The README Status section drifted: it still announced v1.0.0 after
    v1.1.0 shipped. It must now name v1.1.0 as released while keeping the
    PREPARE_ONLY posture."""
    readme = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
    status = readme.split("## Status", 1)[1].split("## License", 1)[0]
    assert "v1.1.0" in status
    assert "RELEASED" in status
    assert "PREPARE_ONLY" in status


def test_package_version_unchanged_at_1_1_0() -> None:
    """Phase 45 is documentation reconciliation only -- it must not bump the
    shipped version."""
    assert version("career-agent") == "1.1.0"


def test_v1_0_0_notes_preserved_intact() -> None:
    """Reconciling v1.1.0 must never rewrite the historical v1.0.0 record."""
    v1_notes = (_REPO_ROOT / "docs" / "release" / "v1.0.0-notes.md").read_text(
        encoding="utf-8"
    )
    assert "**GO.**" in v1_notes
    assert "1.0.0rc1" in v1_notes
