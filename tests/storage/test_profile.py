"""Phase 6: JSON Resume master profile loader/validator (ADR-0017)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from career_agent.storage.profile import ProfileValidationError, load_master_profile


def _write(tmp_path: Path, data: dict[str, Any], name: str = "profile.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data))
    return path


def _valid_profile() -> dict[str, Any]:
    return {
        "basics": {
            "name": "Ada Lovelace",
            "email": "ada@example.com",
            "phone": "555-0100",
            "summary": "Engineer.",
            "location": "Remote",
        },
        "work": [
            {
                "id": "work-techco",
                "name": "Techco",
                "position": "Software Engineer",
                "startDate": "2022-01-01",
                "endDate": None,
                "highlights": ["Built REST APIs serving 2M requests/day"],
            }
        ],
        "education": [
            {
                "id": "edu-1",
                "institution": "Example University",
                "area": "Computer Science",
                "studyType": "BSc",
                "startDate": "2016-09-01",
                "endDate": "2020-06-01",
            }
        ],
        "skills": [
            {"id": "skill-python", "name": "Python", "level": "Expert", "keywords": []},
        ],
        "projects": [
            {
                "id": "proj-internal",
                "name": "Internal Tool",
                "description": "A tool.",
                "highlights": ["Built an internal tool"],
                "keywords": [],
            }
        ],
    }


# ---------------------------------------------------------------------------
# Loading and mapping
# ---------------------------------------------------------------------------


def test_loads_a_valid_profile(tmp_path: Path) -> None:
    path = _write(tmp_path, _valid_profile())
    profile = load_master_profile(path)
    assert profile.basics.name == "Ada Lovelace"
    assert profile.basics.email == "ada@example.com"
    assert profile.work[0].id == "work-techco"
    assert profile.work[0].position == "Software Engineer"
    assert profile.work[0].start_date.isoformat() == "2022-01-01"
    assert profile.work[0].end_date is None
    assert profile.education[0].study_type == "BSc"
    assert profile.skills[0].name == "Python"
    assert profile.projects[0].name == "Internal Tool"


def test_loads_links_from_json_resume_profiles_and_url_fields(tmp_path: Path) -> None:
    """Phase 72/ADR-0090: basics.url -> website_url, basics.profiles[] ->
    linkedin_url/github_url by network, anything else into other_links."""
    data = _valid_profile()
    data["basics"]["url"] = "https://ada.dev"
    data["basics"]["profiles"] = [
        {"network": "LinkedIn", "username": "ada", "url": "https://linkedin.com/in/ada"},
        {"network": "GitHub", "username": "ada", "url": "https://github.com/ada"},
        {"network": "Twitter", "username": "ada", "url": "https://twitter.com/ada"},
    ]
    data["projects"][0]["url"] = "https://github.com/ada/tool"
    profile = load_master_profile(_write(tmp_path, data))
    assert profile.basics.website_url == "https://ada.dev"
    assert profile.basics.linkedin_url == "https://linkedin.com/in/ada"
    assert profile.basics.github_url == "https://github.com/ada"
    assert profile.basics.other_links == ["https://twitter.com/ada"]
    assert profile.projects[0].url == "https://github.com/ada/tool"


def test_missing_links_load_as_none_and_empty_list(tmp_path: Path) -> None:
    profile = load_master_profile(_write(tmp_path, _valid_profile()))
    assert profile.basics.website_url is None
    assert profile.basics.linkedin_url is None
    assert profile.basics.github_url is None
    assert profile.basics.other_links == []
    assert profile.projects[0].url is None


# ---------------------------------------------------------------------------
# Version: deterministic content hash, scoped to grounding fields only
# ---------------------------------------------------------------------------


def test_version_is_deterministic_for_identical_content(tmp_path: Path) -> None:
    path_a = _write(tmp_path, _valid_profile(), "a.json")
    path_b = _write(tmp_path, _valid_profile(), "b.json")
    assert load_master_profile(path_a).version == load_master_profile(path_b).version


def test_version_changes_when_grounding_content_changes(tmp_path: Path) -> None:
    original = _write(tmp_path, _valid_profile(), "a.json")
    changed_data = _valid_profile()
    changed_data["work"][0]["highlights"] = ["A different, unrelated highlight"]
    changed = _write(tmp_path, changed_data, "b.json")
    assert load_master_profile(original).version != load_master_profile(changed).version


def test_version_unchanged_when_an_unmodeled_section_changes(tmp_path: Path) -> None:
    """awards/publications/etc are a named, tracked out-of-scope gap (ADR-0017)
    -- not imported, and must not falsely invalidate every stored EvidenceRef
    by bumping version when they change."""
    original = _write(tmp_path, _valid_profile(), "a.json")
    with_award = _valid_profile()
    with_award["awards"] = [{"title": "Employee of the month"}]
    changed = _write(tmp_path, with_award, "b.json")
    assert load_master_profile(original).version == load_master_profile(changed).version


def test_version_unchanged_when_structured_location_object_changes(
    tmp_path: Path,
) -> None:
    """Structured basics.location is out of scope (ADR-0017); it isn't
    imported at all, so varying its (unimported) content must not move the
    version. Both variants map to the same (absent) modeled location."""
    first = _valid_profile()
    first["basics"]["location"] = {"city": "Springfield", "region": "IL"}
    first_path = _write(tmp_path, first, "a.json")
    second = _valid_profile()
    second["basics"]["location"] = {"city": "Metropolis", "region": "NY"}
    second_path = _write(tmp_path, second, "b.json")
    first_profile = load_master_profile(first_path)
    second_profile = load_master_profile(second_path)
    assert first_profile.version == second_profile.version
    assert first_profile.basics.location is None
    assert second_profile.basics.location is None


# ---------------------------------------------------------------------------
# Id stability: required, loud, never inferred (ADR-0017)
# ---------------------------------------------------------------------------


def test_missing_id_raises_an_actionable_error(tmp_path: Path) -> None:
    data = _valid_profile()
    del data["work"][0]["id"]
    path = _write(tmp_path, data)
    with pytest.raises(ProfileValidationError) as exc_info:
        load_master_profile(path)
    message = str(exc_info.value)
    assert "work" in message
    assert "id" in message.lower()


def test_empty_id_raises_an_actionable_error(tmp_path: Path) -> None:
    data = _valid_profile()
    data["skills"][0]["id"] = "   "
    path = _write(tmp_path, data)
    with pytest.raises(ProfileValidationError, match="skills"):
        load_master_profile(path)


def test_duplicate_id_within_a_section_raises(tmp_path: Path) -> None:
    data = _valid_profile()
    data["skills"].append(
        {"id": "skill-python", "name": "Django", "level": None, "keywords": []}
    )
    path = _write(tmp_path, data)
    with pytest.raises(ProfileValidationError, match="Duplicate id"):
        load_master_profile(path)


def test_duplicate_id_across_different_sections_raises(tmp_path: Path) -> None:
    """The uniqueness requirement is global, not per-section -- a work entry
    and a project entry accidentally sharing an id is exactly the ambiguity
    the id-stability guarantee exists to prevent."""
    data = _valid_profile()
    data["projects"][0]["id"] = "work-techco"  # collides with the work entry
    path = _write(tmp_path, data)
    with pytest.raises(ProfileValidationError, match="Duplicate id"):
        load_master_profile(path)


def test_ids_are_never_inferred_or_silently_written_back(tmp_path: Path) -> None:
    """A missing id is a hard failure, not a loader-assigned default -- this
    is the whole point of requiring ids explicitly rather than deriving them
    from content that can change on the next edit."""
    data = _valid_profile()
    del data["projects"][0]["id"]
    path = _write(tmp_path, data)
    with pytest.raises(ProfileValidationError):
        load_master_profile(path)
    # the file on disk is untouched -- no silent write-back happened
    assert "id" not in json.loads(path.read_text())["projects"][0]


# ---------------------------------------------------------------------------
# Other validation errors: surfaced from Pydantic directly, not re-wrapped
# ---------------------------------------------------------------------------


def test_missing_required_field_surfaces_the_raw_pydantic_error(
    tmp_path: Path,
) -> None:
    data = _valid_profile()
    del data["work"][0]["startDate"]
    path = _write(tmp_path, data)
    with pytest.raises(ValidationError):
        load_master_profile(path)
