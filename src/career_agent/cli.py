"""Command-line entry point for the Autonomous AI Career Agent.

This is a Phase 1 placeholder establishing the entry point wired in
``pyproject.toml`` (``career-agent``). Real commands arrive in later phases.
"""

from __future__ import annotations

from career_agent import __version__


def main() -> None:
    """Print a placeholder banner.

    Replaced by the real CLI (run/plan/discover/...) in later phases.
    """
    print(f"Autonomous AI Career Agent v{__version__} — scaffolding (Phase 1).")
    print("Not yet runnable; see ROADMAP.md for the build plan.")


if __name__ == "__main__":
    main()
