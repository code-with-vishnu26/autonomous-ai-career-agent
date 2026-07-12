"""Phase 58 (ADR-0077): the scheduler structurally cannot submit anything.

AST-based source scan, the same discipline
``tests/agents/test_review_engine.py``'s own no-browser-import test and
``tests/test_application_engine.py``'s no-submit-selector test already
established -- a docstring promise is not a guarantee; a scan of the
actual import statements and any submission-shaped call is.
"""

from __future__ import annotations

import ast
import inspect

from career_agent import scheduler as scheduler_module

_FORBIDDEN_MODULE_FRAGMENTS = (
    "submission",
    "integrations.browser",
    "browser_applicator",
)


def test_scheduler_imports_no_submission_or_browser_module() -> None:
    tree = ast.parse(inspect.getsource(scheduler_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for fragment in _FORBIDDEN_MODULE_FRAGMENTS:
                assert fragment not in node.module.lower(), (
                    f"scheduler.py imports {node.module!r}, containing "
                    f"forbidden fragment {fragment!r}"
                )
        if isinstance(node, ast.Import):
            for alias in node.names:
                for fragment in _FORBIDDEN_MODULE_FRAGMENTS:
                    assert fragment not in alias.name.lower(), (
                        f"scheduler.py imports {alias.name!r}, containing "
                        f"forbidden fragment {fragment!r}"
                    )


def test_scheduler_never_calls_submit_or_click() -> None:
    source = inspect.getsource(scheduler_module)
    assert ".click(" not in source
    assert ".submit(" not in source


def test_scheduler_jobs_are_exactly_the_named_background_jobs() -> None:
    """No job silently added beyond the six named in ADR-0077 -- job
    discovery and analytics refresh were explicitly deferred (no per-user
    profile store / no cached analytics to refresh, respectively)."""
    from career_agent.core.config import Settings
    from career_agent.scheduler import build_scheduler

    scheduler = build_scheduler(Settings())
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert job_ids == {
        "reminders",
        "daily_digest",
        "weekly_digest",
        "notification_cleanup",
        "expired_token_cleanup",
        "retry_failed_webhooks",
    }
