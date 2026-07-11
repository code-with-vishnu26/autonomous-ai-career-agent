"""Phase 46 (ADR-0064): Job Search Preferences storage boundary guards.

Mirrors tests/storage/test_profile.py's shape for a much simpler loader:
no camelCase mapping, no id-stability checks -- this schema is entirely
this project's own design.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from career_agent.domain.job_preferences import JobPreferences
from career_agent.storage.job_preferences import (
    example_job_preferences_dict,
    load_job_preferences,
    save_job_preferences,
    write_job_preferences_scaffold,
)


def test_example_dict_round_trips_through_the_real_loader(tmp_path: Path) -> None:
    """The scaffold is the exact shape load_job_preferences accepts."""
    path = tmp_path / "job_preferences.json"
    path.write_text(json.dumps(example_job_preferences_dict()), encoding="utf-8")
    prefs = load_job_preferences(path)
    assert "Backend Developer" in prefs.preferred_titles
    assert prefs.countries == ["India"]
    assert prefs.blacklisted_companies == ["TCS", "Infosys"]


def test_write_scaffold_creates_a_file_and_refuses_to_overwrite(
    tmp_path: Path,
) -> None:
    path = tmp_path / "job_preferences.json"
    assert write_job_preferences_scaffold(path) is True
    original = path.read_text(encoding="utf-8")
    path.write_text('{"preferred_titles": ["Custom"]}', encoding="utf-8")
    assert write_job_preferences_scaffold(path) is False
    assert path.read_text(encoding="utf-8") != original
    assert "Custom" in path.read_text(encoding="utf-8")


def test_write_scaffold_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "job_preferences.json"
    assert write_job_preferences_scaffold(path) is True
    assert path.is_file()


def test_load_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        load_job_preferences(tmp_path / "nonexistent.json")


def test_load_raises_on_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "job_preferences.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_job_preferences(path)


def test_load_raises_on_invalid_field_value(tmp_path: Path) -> None:
    path = tmp_path / "job_preferences.json"
    path.write_text(
        json.dumps({"seniority": "not-a-real-level"}), encoding="utf-8"
    )
    with pytest.raises(ValidationError):
        load_job_preferences(path)


def test_save_then_load_round_trips_every_field(tmp_path: Path) -> None:
    path = tmp_path / "job_preferences.json"
    original = JobPreferences(
        preferred_titles=["Backend Developer"],
        alternative_titles=["Software Engineer"],
        seniority="entry",
        experience_years_min=0,
        experience_years_max=2,
        employment_types=["full_time"],
        work_mode=["remote"],
        countries=["India"],
        salary_min=6.0,
        salary_max=12.0,
        salary_currency="LPA",
        preferred_companies=["Google"],
        blacklisted_companies=["TCS"],
        visa_sponsorship_required=False,
        preferred_technologies=["Python", "FastAPI"],
        max_applications_per_day=5,
        preferred_ats_providers=["greenhouse"],
        time_zone="Asia/Kolkata",
    )
    save_job_preferences(path, original)
    loaded = load_job_preferences(path)
    assert loaded == original


def test_save_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "job_preferences.json"
    save_job_preferences(path, JobPreferences())
    assert path.is_file()


def test_save_overwrites_existing_file_unlike_the_scaffold_writer(
    tmp_path: Path,
) -> None:
    """Unlike write_job_preferences_scaffold (never overwrite), save is the
    real writer the wizard uses on every run and must actually persist
    edits -- verified against a second, different save."""
    path = tmp_path / "job_preferences.json"
    save_job_preferences(path, JobPreferences(preferred_titles=["First"]))
    save_job_preferences(path, JobPreferences(preferred_titles=["Second"]))
    assert load_job_preferences(path).preferred_titles == ["Second"]
