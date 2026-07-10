"""Fail-closed inspection of built release artifacts (wheel + sdist).

Used by CI and by ``RELEASE_CHECKLIST.md`` so the same check runs the same
way everywhere: no secrets, no real ``.env``, no databases, no spreadsheet/CV
exports, and no Promptfoo result artifacts end up inside a built
distribution. Exits non-zero (fail-closed) on any forbidden entry, a missing
``dist/`` artifact, or a malformed archive -- it never silently passes an
ambiguous case.

The **sdist** (source distribution) is expected to contain ``tests/`` --
that is normal, intentional Python packaging practice (a source archive is
meant to be buildable and testable) and is not a privacy or secrecy issue.
The **wheel** (built distribution) is not, so ``tests/`` is only flagged
there. ``.env.example`` is an intentionally committed, secret-free template
(placeholder keys only) and is explicitly exempted from the ``.env`` check;
a real ``.env`` file is not.
"""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path

_FORBIDDEN_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".xlsx")
_FORBIDDEN_NAME_FRAGMENTS = ("promptfoo/results",)
_WHEEL_ONLY_FORBIDDEN_PATH_PARTS = ("tests", "test")


def _is_real_env_file(lower_name: str) -> bool:
    """A real, secret-bearing ``.env`` -- never the safe ``.env.example``."""
    basename = lower_name.rsplit("/", 1)[-1]
    return basename == ".env"


def _forbidden_entries(names: list[str], *, check_test_paths: bool) -> list[str]:
    bad: list[str] = []
    for name in names:
        lower = name.lower().replace("\\", "/")
        parts = [p for p in lower.split("/") if p]
        if check_test_paths and any(
            part in _WHEEL_ONLY_FORBIDDEN_PATH_PARTS for part in parts
        ):
            bad.append(name)
            continue
        if _is_real_env_file(lower):
            bad.append(name)
            continue
        if any(lower.endswith(suffix) for suffix in _FORBIDDEN_SUFFIXES):
            bad.append(name)
            continue
        if any(fragment in lower for fragment in _FORBIDDEN_NAME_FRAGMENTS):
            bad.append(name)
    return bad


def _wheel_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        return zf.namelist()


def _sdist_names(path: Path) -> list[str]:
    with tarfile.open(path, "r:gz") as tf:
        return tf.getnames()


def main() -> int:
    """Check the latest built wheel and sdist for forbidden content."""
    dist = Path("dist")
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    if not wheels:
        print(
            "FAIL: no wheel found in dist/ -- run `python -m build` first",
            file=sys.stderr,
        )
        return 1
    if not sdists:
        print(
            "FAIL: no sdist found in dist/ -- run `python -m build` first",
            file=sys.stderr,
        )
        return 1

    exit_code = 0
    targets = (
        (wheels[-1], _wheel_names, True),
        (sdists[-1], _sdist_names, False),
    )
    for path, loader, check_test_paths in targets:
        names = loader(path)
        bad = _forbidden_entries(names, check_test_paths=check_test_paths)
        if bad:
            exit_code = 1
            print(f"FAIL: forbidden entries in {path.name}:", file=sys.stderr)
            for entry in bad:
                print(f"  {entry}", file=sys.stderr)
        else:
            print(f"OK: {path.name} -- {len(names)} entries, none forbidden")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
