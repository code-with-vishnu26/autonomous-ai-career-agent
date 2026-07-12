"""Phase 61 (ADR-0079): the secret-scanning baseline check.

Real ``detect-secrets`` invocation against a scratch copy of the repo's own
``.secrets.baseline`` -- not mocked, matching this project's existing
``scripts/verify_release_artifacts.py`` precedent of exercising the real
tool against real repository state rather than a synthetic fixture.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from check_secrets_baseline import _normalized, main  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent
#: Everything ``detect-secrets`` itself already excludes (see
#: ``check_secrets_baseline._EXCLUDES``) plus version control -- copying
#: these into a scratch dir would be slow and is never part of the scan.
_SKIP_COPYING = {".venv", "node_modules", "frontend", ".git", "__pycache__"}


def _copy_repo_for_scanning(tmp_path: Path) -> Path:
    """A scratch copy of every file the baseline's own scan could reference.

    Full-tree copy (minus the heavy/irrelevant dirs above) rather than a
    hand-picked subset -- the committed baseline has findings recorded
    against ``tests/``, ``docker.env``, ``promptfoo/``, etc., and a partial
    copy would make ``main()`` report those as newly *missing* rather than
    genuinely re-verifying that the baseline still matches reality.
    """
    scratch = tmp_path / "repo"
    scratch.mkdir()
    for entry in _REPO_ROOT.iterdir():
        if entry.name in _SKIP_COPYING:
            continue
        target = scratch / entry.name
        if entry.is_dir():
            shutil.copytree(entry, target, ignore=shutil.ignore_patterns("dist"))
        else:
            shutil.copy2(entry, target)
    # detect-secrets enumerates scan targets via `git ls-files`, not a raw
    # filesystem walk -- a scratch copy with no `.git` silently scans
    # nothing (empty results) rather than failing loud. A throwaway repo
    # with everything staged is enough; no real history needed.
    subprocess.run(["git", "init", "-q"], cwd=scratch, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"],
        cwd=scratch,
        check=True,
    )
    return scratch


def test_normalized_strips_generated_at() -> None:
    payload = json.dumps({"generated_at": "2026-01-01T00:00:00Z", "results": {}})
    assert "generated_at" not in _normalized(payload)


def test_normalized_strips_the_baseline_files_own_checkout_path() -> None:
    """The ``is_baseline_file`` filter records ``--baseline``'s absolute
    path -- different between a contributor's machine and CI's runner, so
    it must never affect whether two scans are considered "the same"."""
    payload = json.dumps(
        {
            "results": {},
            "filters_used": [
                {
                    "path": "detect_secrets.filters.common.is_baseline_file",
                    "filename": "/home/someone/repo/.secrets.baseline",
                }
            ],
        }
    )
    normalized = _normalized(payload)
    assert "filename" not in normalized["filters_used"][0]
    assert normalized["filters_used"][0]["path"] == (
        "detect_secrets.filters.common.is_baseline_file"
    )


def test_the_committed_baseline_matches_a_fresh_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real, committed ``.secrets.baseline`` must already be up to date --
    this is what CI runs; a red run here means a developer forgot to update
    the baseline for a genuinely new (real or false-positive) finding.

    Runs against a scratch copy, never the real tracked file -- ``main()``
    rewrites the baseline it's pointed at (``generated_at`` at minimum),
    and a test must never leave the working tree dirty as a side effect.
    """
    assert (_REPO_ROOT / ".secrets.baseline").exists()
    scratch = _copy_repo_for_scanning(tmp_path)
    monkeypatch.chdir(scratch)
    monkeypatch.setattr("check_secrets_baseline._REPO_ROOT", scratch)
    monkeypatch.setattr(
        "check_secrets_baseline._BASELINE_PATH", scratch / ".secrets.baseline"
    )
    assert main() == 0


def test_a_freshly_introduced_secret_fails_the_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copies the whole repo into a scratch dir, plants a real-shaped secret
    nothing in the current baseline could match, and confirms the check
    fails closed on it."""
    scratch = _copy_repo_for_scanning(tmp_path)
    (scratch / "src" / "planted_secret.py").write_text(
        'AWS_SECRET_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE1234"\n',
        encoding="utf-8",
    )
    # detect-secrets scans git-tracked files only (see the helper above) --
    # the planted file must be staged too, or it's invisible to the scan.
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"],
        cwd=scratch,
        check=True,
    )
    monkeypatch.chdir(scratch)
    monkeypatch.setattr("check_secrets_baseline._REPO_ROOT", scratch)
    monkeypatch.setattr(
        "check_secrets_baseline._BASELINE_PATH", scratch / ".secrets.baseline"
    )
    assert main() == 1
