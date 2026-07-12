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
import os
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


def _print_diff(before: dict, after: dict) -> None:
    """Print exactly which result files/entries differ -- diagnostic only.

    Every field detect-secrets records here (``hashed_secret`` is a SHA1
    digest, never the raw match; ``line_number``/``type``) is already safe
    to print -- this is the same information already committed in
    ``.secrets.baseline`` itself, just narrowed to what changed.
    """
    before_files = before.get("results", {})
    after_files = after.get("results", {})
    for filename in sorted(set(before_files) | set(after_files)):
        before_entries = before_files.get(filename, [])
        after_entries = after_files.get(filename, [])
        if before_entries == after_entries:
            continue
        if len(before_entries) != len(after_entries):
            print(
                f"  {filename}: {len(before_entries)} finding(s) in "
                f"baseline, {len(after_entries)} in fresh scan",
                file=sys.stderr,
            )
            continue
        # Same count, different content -- show which field(s) moved.
        for before_entry, after_entry in zip(
            before_entries, after_entries, strict=True
        ):
            if before_entry != after_entry:
                changed = {
                    key
                    for key in {*before_entry, *after_entry}
                    if before_entry.get(key) != after_entry.get(key)
                }
                print(
                    f"  {filename}: entry differs in {sorted(changed)} -- "
                    f"baseline={ {k: before_entry.get(k) for k in changed} }, "
                    f"fresh={ {k: after_entry.get(k) for k in changed} }",
                    file=sys.stderr,
                )
    if before.get("filters_used") != after.get("filters_used"):
        print(f"  filters_used differs: {before.get('filters_used')!r} "
              f"vs {after.get('filters_used')!r}", file=sys.stderr)
    if before.get("plugins_used") != after.get("plugins_used"):
        print(f"  plugins_used differs: {before.get('plugins_used')!r} "
              f"vs {after.get('plugins_used')!r}", file=sys.stderr)


def main() -> int:
    """Return 0 if a fresh scan matches the committed baseline, else 1."""
    before = _normalized(_BASELINE_PATH.read_text(encoding="utf-8"))

    args = ["detect-secrets", "scan", "--baseline", str(_BASELINE_PATH)]
    for pattern in _EXCLUDES:
        args += ["--exclude-files", pattern]
    # PYTHONUTF8 forces every open() detect-secrets makes to default to
    # UTF-8 regardless of OS locale (PEP 540) -- without it, Windows'
    # default locale encoding (not UTF-8) reads non-ASCII file content
    # (e.g. "résumé" in test fixtures) differently than Linux/macOS,
    # producing different hashes for text near it and making a scan of
    # identical committed content disagree by platform alone. Real bug,
    # confirmed by the exact same class of mojibake this project already
    # documented for its own code in ADR-0056.
    subprocess.run(
        args, cwd=_REPO_ROOT, check=True, env={**os.environ, "PYTHONUTF8": "1"}
    )

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
        _print_diff(before, after)
        return 1

    print("No new potential secrets -- .secrets.baseline unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
