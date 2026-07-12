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

Phase 41 added the sdist top-level allowlist below after a real leak: an
untracked, non-``.gitignore``d local tool directory (``.claude/``,
Claude Code's own session state) ended up in a built sdist because
hatchling's default sdist packaging includes anything not explicitly
git-ignored -- untracked-but-not-ignored is not the same as excluded. A
suffix/fragment blocklist can never catch an unanticipated *directory*;
only a positive allowlist can, so a genuinely new top-level source file
requires a deliberate one-line addition here rather than silently passing.
"""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path

_FORBIDDEN_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".xlsx")
_FORBIDDEN_NAME_FRAGMENTS = ("promptfoo/results",)
_WHEEL_ONLY_FORBIDDEN_PATH_PARTS = ("tests", "test")

# Every top-level entry a legitimate sdist may contain (Phase 41). Anything
# else -- most plausibly a leaked local/untracked directory that isn't
# covered by .gitignore -- fails closed instead of silently shipping.
_SDIST_ALLOWED_TOP_LEVEL = frozenset(
    {
        ".env.example",
        ".github",
        ".gitignore",
        "ARCHITECTURE.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "PKG-INFO",
        "README.md",
        "RELEASE_CHECKLIST.md",
        "ROADMAP.md",
        "SECURITY.md",
        "docs",
        # Phase 55: the React dashboard frontend's source (node_modules/
        # dist are excluded via .gitignore -- see the "Node / frontend"
        # section there for why they're listed at the *root* .gitignore
        # rather than relying on frontend/.gitignore alone).
        "frontend",
        "promptfoo",
        "pyproject.toml",
        "requirements.txt",
        "research",
        "scripts",
        "src",
        "tests",
        # Phase 59 (ADR-0076): real, tracked deployment infrastructure --
        # not a leaked local artifact. docker.env/production.env.example
        # are safe, placeholder-only templates (never a real secret; see
        # .gitignore's own carve-out next to `.env`/`.env.*`).
        ".dockerignore",
        "Dockerfile.backend",
        "Dockerfile.frontend",
        "Dockerfile.frontend.dev",
        "deploy",
        "docker-compose.yml",
        "docker-compose.dev.yml",
        "docker-compose.prod.yml",
        "docker.env",
        "production.env.example",
    }
)


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


def _sdist_top_level_violations(names: list[str]) -> list[str]:
    """Every top-level entry not in the explicit allowlist.

    Strips the sdist's own wrapper directory (e.g. ``career_agent-1.0.0/``)
    before comparing against ``_SDIST_ALLOWED_TOP_LEVEL``.
    """
    seen: set[str] = set()
    for name in names:
        parts = name.split("/")
        if len(parts) < 2:
            continue  # the wrapper directory entry itself
        seen.add(parts[1])
    return sorted(seen - _SDIST_ALLOWED_TOP_LEVEL)


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
        (wheels[-1], _wheel_names, True, False),
        (sdists[-1], _sdist_names, False, True),
    )
    for path, loader, check_test_paths, check_top_level in targets:
        names = loader(path)
        bad = _forbidden_entries(names, check_test_paths=check_test_paths)
        unexpected = _sdist_top_level_violations(names) if check_top_level else []
        if unexpected:
            exit_code = 1
            print(
                f"FAIL: unexpected top-level entries in {path.name} (not in "
                "the sdist allowlist -- likely a leaked local/untracked "
                "directory):",
                file=sys.stderr,
            )
            for entry in unexpected:
                print(f"  {entry}", file=sys.stderr)
        if bad:
            exit_code = 1
            print(f"FAIL: forbidden entries in {path.name}:", file=sys.stderr)
            for entry in bad:
                print(f"  {entry}", file=sys.stderr)
        if not bad and not unexpected:
            print(f"OK: {path.name} -- {len(names)} entries, none forbidden")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
