"""Job Search Preferences loader/writer (Phase 46, ADR-0064).

The I/O boundary between the user's ``job_preferences.json`` on disk and
:class:`~career_agent.domain.job_preferences.JobPreferences`. Mirrors
:mod:`career_agent.storage.profile`'s shape (scaffold + write-once +
loader), but is simpler: this schema has no external convention to map
(unlike JSON Resume's camelCase), so the on-disk shape *is* the model's own
field names -- ``model_validate``/``model_dump_json`` directly, no mapping
layer, no id-stability checks (nothing here is referenced by a stable
:class:`~career_agent.domain.models.EvidenceRef` the way profile entries
are).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from career_agent.domain.job_preferences import JobPreferences


def example_job_preferences_dict() -> dict[str, Any]:
    """A schema-correct scaffold with realistic (not just placeholder) values.

    Kept in lockstep with :class:`JobPreferences` by a round-trip test, so
    it can never silently drift into an unloadable shape.
    """
    return {
        "preferred_titles": ["Backend Developer", "Python Developer"],
        "alternative_titles": ["Software Engineer", "AI Engineer"],
        "seniority": "entry",
        "experience_years_min": 0,
        "experience_years_max": 2,
        "employment_types": ["full_time"],
        "work_mode": ["remote"],
        "countries": ["India"],
        "states": [],
        "cities": [],
        "salary_min": 6.0,
        "salary_max": 12.0,
        "salary_currency": "LPA",
        "preferred_companies": ["Google", "Microsoft", "Amazon"],
        "blacklisted_companies": ["TCS", "Infosys"],
        "industries": [],
        "visa_sponsorship_required": None,
        "work_authorization": None,
        "preferred_technologies": ["Python", "FastAPI", "Docker", "React"],
        "keywords_include": [],
        "keywords_exclude": [],
        "max_applications_per_day": None,
        "require_human_confirmation": True,
        "auto_tailor_resume": True,
        "auto_generate_cover_letter": False,
        "preferred_ats_providers": [],
        "time_zone": None,
    }


def write_job_preferences_scaffold(path: Path) -> bool:
    """Write the example preferences to ``path`` if absent; never overwrite.

    Returns ``True`` if the scaffold was written, ``False`` if a file
    already exists at ``path`` (left completely untouched -- this never
    destroys a user's saved preferences).
    """
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(example_job_preferences_dict(), indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return True


def load_job_preferences(path: Path) -> JobPreferences:
    """Load and validate job search preferences from ``path``.

    Explicit ``encoding="utf-8"`` -- the same rationale as
    ``load_master_profile``: a preference value (a company name, a city)
    can carry non-ASCII content, and without this, ``Path.read_text()``
    falls back to the platform's default encoding (cp1252 on Windows).
    Raises ``OSError``/``json.JSONDecodeError``/``pydantic.ValidationError``
    on a missing, malformed, or invalid file -- callers are responsible for
    catching these and printing a clean message, the same contract as
    ``load_master_profile``.
    """
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return JobPreferences.model_validate(raw)


def save_job_preferences(path: Path, preferences: JobPreferences) -> None:
    """Write ``preferences`` to ``path``, creating parent directories as needed.

    Unlike ``save_legal_status`` (which patches one key into an existing
    profile), this is a full-file writer: job preferences have no other
    sections to preserve. Explicit ``encoding="utf-8"`` for the same reason
    as every other read/write in this module.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        preferences.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
