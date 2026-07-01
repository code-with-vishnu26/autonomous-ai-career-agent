"""Enforces the project's dependency-direction contracts in the test suite.

The contracts live in ``pyproject.toml`` under ``[tool.importlinter]`` and are
checked with import-linter. Running them here means a wrong-direction import
(e.g. ``plugins`` importing ``agents``, or ``domain`` importing ``core``)
fails the build, without depending on a separate CI job existing yet.

Skips cleanly if import-linter is not installed, so the suite still runs in a
minimal environment; CI installs the dev extras and enforces it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("importlinter", reason="import-linter (dev extra) not installed")

from importlinter.api import use_cases  # noqa: E402

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_dependency_direction_contracts_hold() -> None:
    """All import-linter contracts in pyproject.toml are kept."""
    passed = use_cases.lint_imports(config_filename=str(PYPROJECT))
    assert passed, (
        "import-linter contracts broken -- a dependency points the wrong way. "
        "Run `lint-imports --config pyproject.toml` to see which."
    )
