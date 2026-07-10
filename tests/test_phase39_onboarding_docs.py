"""Phase 39: onboarding-documentation accuracy guards.

The Phase 36 controlled smoke (and this agent's own first attempt at a
synthetic profile fixture in that phase) both hit the same real confusion:
``career-agent apply``'s actual loader (``load_master_profile`` ->
``_map_work``) expects JSON Resume's camelCase ``startDate``/``endDate``,
not the Pydantic model's own snake_case field names -- and nothing shipped
an example showing the correct shape. This file extracts the README's
work-entry example verbatim and proves it loads through the *real* CLI
loading path, so the docs can never silently drift from what the loader
actually accepts. No live call; no network.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from career_agent.storage.profile import load_master_profile

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _extract_work_entry_example() -> dict:
    readme = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
    match = re.search(r'```json\n(\{.*?"highlights".*?\})\n```', readme, re.DOTALL)
    assert match is not None, "README's example work entry JSON block not found"
    return json.loads(match.group(1))


def test_readme_work_entry_example_loads_through_the_real_cli_loader() -> None:
    """Proves the docs example works via load_master_profile (the path
    `apply`/`setup`/`import-cv` actually use), not merely via a raw
    Pydantic model_validate() call that bypasses the camelCase mapping."""
    work_entry = _extract_work_entry_example()
    assert "startDate" in work_entry  # JSON Resume convention, not start_date
    assert "endDate" in work_entry

    profile = {
        "version": "1",
        "basics": {"name": "Test User", "email": "test@example.com"},
        "work": [work_entry],
        "skills": [],
        "education": [],
        "projects": [],
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "profile.json"
        path.write_text(json.dumps(profile), encoding="utf-8")
        loaded = load_master_profile(path)
    assert loaded.work[0].start_date.isoformat() == work_entry["startDate"]
    assert loaded.work[0].end_date.isoformat() == work_entry["endDate"]


def test_readme_documents_only_editable_install_as_verified() -> None:
    readme = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "no published GitHub Release asset" in readme or "no PyPI" in readme
    assert "pip install -e" in readme


def test_readme_has_separately_labeled_bash_and_powershell_quick_start() -> None:
    readme = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "```powershell" in readme
    assert "Activate.ps1" in readme
    # The old mixed block (bash fence with an inline "# Windows:" comment
    # standing in for a real separate instruction) must not reappear.
    assert "# Windows: .venv" not in readme


def test_readme_points_to_promptfoo_running_instructions() -> None:
    readme = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "promptfoo/README.md" in readme
    assert (_REPO_ROOT / "promptfoo" / "README.md").is_file()
