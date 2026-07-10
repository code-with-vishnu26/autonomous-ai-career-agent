"""Cross-platform clean-venv install + smoke test for a built wheel.

Creates a throwaway virtual environment, installs the most recently built
wheel from ``dist/``, and exercises two offline, network-free entry points:
``career-agent --help`` and ``career-agent setup`` (in a scratch directory).
Used by CI on every supported OS so "the package installs and runs" is
*proven* identically on Linux and Windows via one script, rather than
duplicated as OS-conditional shell steps that could silently drift apart.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def _bin_dir(env_dir: Path) -> Path:
    return env_dir / ("Scripts" if sys.platform == "win32" else "bin")


def _exe(env_dir: Path, name: str) -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    return _bin_dir(env_dir) / f"{name}{suffix}"


def main() -> int:
    """Install the latest built wheel into a fresh venv and smoke-test it."""
    wheels = sorted(Path("dist").glob("*.whl"))
    if not wheels:
        print(
            "FAIL: no wheel found in dist/ -- run `python -m build` first",
            file=sys.stderr,
        )
        return 1
    wheel = wheels[-1]

    with tempfile.TemporaryDirectory(prefix="career-agent-smoke-") as tmp:
        env_dir = Path(tmp) / "venv"
        venv.EnvBuilder(with_pip=True).create(env_dir)

        pip = _exe(env_dir, "pip")
        subprocess.run([str(pip), "install", "--quiet", str(wheel)], check=True)

        cli = _exe(env_dir, "career-agent")
        subprocess.run([str(cli), "--help"], check=True)

        scratch = Path(tmp) / "scratch"
        scratch.mkdir()
        subprocess.run([str(cli), "setup"], check=True, cwd=scratch)
        if not (scratch / "profile.json").is_file():
            print(
                "FAIL: `career-agent setup` did not write profile.json",
                file=sys.stderr,
            )
            return 1

    print(f"OK: {wheel.name} installs cleanly; --help and setup smoke pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
