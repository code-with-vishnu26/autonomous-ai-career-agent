"""Fail-closed check that no new potential secret was introduced (Phase 61, ADR-0079).

Re-runs ``detect-secrets scan`` against the tracked ``.secrets.baseline`` and
compares the result to what's committed, ignoring the one field
(``generated_at``) that changes on every run regardless of content. A diff
means the scan found something the committed baseline doesn't already
record -- either a real new secret (fix it) or a new false positive (run
``detect-secrets audit .secrets.baseline`` locally, review it, and commit
the updated baseline).

Never auto-updates or auto-commits the baseline itself -- a security gate
that silently rewrites its own gate on every run isn't a gate.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BASELINE_PATH = _REPO_ROOT / ".secrets.baseline"
_EXCLUDES = (
    "\\.venv/",
    "node_modules/",
    "frontend/dist/",
    "\\.git/",
    # The baseline records secrets as hex-encoded hashes -- without this,
    # each hash looks like a fresh high-entropy secret to detect-secrets,
    # so scanning the baseline file against itself snowballs its own
    # findings on every run.
    "^\\.secrets\\.baseline$",
)


def _normalized(baseline_text: str) -> dict:
    """Strip fields that vary by machine/checkout path, not by content.

    ``generated_at`` changes on every run. The ``is_baseline_file`` filter
    entry records ``--baseline``'s *absolute path*, which is this
    repository's checkout location -- different between a contributor's
    machine and CI's runner, so comparing it raw would fail this check on
    every single run regardless of whether any secret actually changed.
    """
    data = json.loads(baseline_text)
    data.pop("generated_at", None)
    for entry in data.get("filters_used", []):
        if entry.get("path") == "detect_secrets.filters.common.is_baseline_file":
            entry.pop("filename", None)
    return data


def main() -> int:
    """Return 0 if a fresh scan matches the committed baseline, else 1."""
    before = _normalized(_BASELINE_PATH.read_text(encoding="utf-8"))

    args = ["detect-secrets", "scan", "--baseline", str(_BASELINE_PATH)]
    for pattern in _EXCLUDES:
        args += ["--exclude-files", pattern]
    subprocess.run(args, cwd=_REPO_ROOT, check=True)

    after = _normalized(_BASELINE_PATH.read_text(encoding="utf-8"))

    if before != after:
        print(
            "New potential secret(s) found -- .secrets.baseline no longer "
            "matches what's committed. If this is a real secret, remove it. "
            "If it's a false positive, run "
            "`detect-secrets audit .secrets.baseline` locally, review the "
            "finding, and commit the updated baseline.",
            file=sys.stderr,
        )
        return 1

    print("No new potential secrets -- .secrets.baseline unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
