"""Command-line entry point for the Autonomous AI Career Agent.

``confirm_submission`` (Phase 8c, ADR-0024) is this project's first real,
executable source of a :class:`~career_agent.domain.models.HumanConfirmation`.
Every structural guarantee built through Phase 8 -- the truthfulness gate,
the token-bound confirmation that gates real submission -- has only ever
been exercised against a fixture-constructed confirmation until this
function exists. It is deliberately minimal: read a yes/no-shaped answer
from stdin, construct a confirmation naming the exact preview shown, or
abort cleanly on anything else. No formatting polish, no retry loop --
prove the mechanism, not the product, same as every other first pass in
this project.

``main()`` remains the Phase 1 placeholder. Wiring ``confirm_submission``
into a real ``career-agent apply <id>`` command is separate, later work.
"""

from __future__ import annotations

import getpass
from collections.abc import Callable
from datetime import UTC, datetime

from career_agent import __version__
from career_agent.domain.models import HumanConfirmation, SubmissionPreview

_YES = {"y", "yes"}


def confirm_submission(
    preview: SubmissionPreview,
    *,
    input_fn: Callable[[str], str] = input,
    confirmed_by: str | None = None,
) -> HumanConfirmation | None:
    """Show ``preview`` and ask for an explicit yes/no confirmation.

    Returns ``None`` -- never a :class:`HumanConfirmation` -- for anything
    other than an exact "y"/"yes" (case-insensitive) answer, including
    empty or malformed input. There is no default-to-yes path: silence or
    an unrecognized answer is treated as "no," not as "proceed."
    """
    print(f"Tier: {preview.tier}")
    print(f"Target: {preview.target}")
    print("Content:")
    print(preview.rendered_content)
    print()
    answer = input_fn("Submit this application? [y/N]: ").strip().lower()
    if answer not in _YES:
        return None
    return HumanConfirmation(
        preview_token=preview.preview_token,
        confirmed_by=confirmed_by or getpass.getuser(),
        confirmed_at=datetime.now(UTC),
    )


def main() -> None:
    """Print a placeholder banner.

    Replaced by the real CLI (run/plan/discover/apply/...) in later phases.
    """
    print(f"Autonomous AI Career Agent v{__version__} — scaffolding (Phase 1).")
    print("Not yet runnable; see ROADMAP.md for the build plan.")


if __name__ == "__main__":
    main()
