"""JSON Resume master profile loader/validator (Phase 6, ADR-0017).

The single I/O boundary between the user's data on disk (ADR-0006 — a JSON
Resume file, user-owned, never committed to the repo) and the domain model
(:class:`~career_agent.domain.models.MasterProfile`) everything downstream is
built against. A plain function, not a ``Protocol`` — there is exactly one
profile format and no plausible second implementation on the roadmap; that is
a real choice, not an oversight (see ADR-0017).

Two things this loader enforces that the raw JSON Resume schema does not:

- **Every ``work``/``education``/``skills``/``projects`` entry must carry a
  stable, unique ``id``.** JSON Resume has no native id field; ``id`` here is
  a required extension. It is *rejected*, never inferred or silently written
  back — the "assigned once, never reused" guarantee
  :class:`~career_agent.domain.models.EvidenceRef` depends on (ADR-0012) only
  holds if the id is something the user deliberately committed to, not
  something the loader derived from content that can change on the next edit.
- **``version`` is a deterministic content hash over exactly the fields
  :class:`MasterProfile` models** (``basics``/``work``/``education``/
  ``skills``/``projects``) — never the whole raw file. A JSON Resume section
  this loader doesn't import at all (``awards``, ``publications``,
  ``languages``, ``interests``, ``references``, ``volunteer``, structured
  ``basics.location``/``basics.profiles``) changing must not bump ``version``
  and falsely invalidate every stored ``EvidenceRef`` pointing at facts that
  didn't actually change.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from career_agent.domain.models import (
    BasicsSection,
    EducationEntry,
    MasterProfile,
    ProjectEntry,
    SkillEntry,
    WorkEntry,
)

_ID_SECTIONS = ("work", "education", "skills", "projects")


class ProfileValidationError(ValueError):
    """A master profile file failed validation.

    Raised (never silently patched or inferred around) for the id-stability
    checks this loader adds on top of raw JSON Resume. Other structural
    problems (a missing required field, a malformed date) are surfaced as the
    underlying ``pydantic.ValidationError`` directly, unwrapped — only the id
    checks get a custom message, because a missing id is expected to be the
    first friction point for anyone loading an existing, unmodified resume
    into this system for the first time.
    """


def load_master_profile(path: Path) -> MasterProfile:
    """Load, id-validate, and version a master profile from a JSON Resume file."""
    raw: dict[str, Any] = json.loads(path.read_text())
    _validate_ids(raw)
    profile = MasterProfile(
        version="pending",
        basics=BasicsSection(**_map_basics(raw.get("basics", {}))),
        work=[WorkEntry(**_map_work(e)) for e in raw.get("work", [])],
        education=[
            EducationEntry(**_map_education(e)) for e in raw.get("education", [])
        ],
        skills=[SkillEntry(**_map_skill(e)) for e in raw.get("skills", [])],
        projects=[ProjectEntry(**_map_project(e)) for e in raw.get("projects", [])],
    )
    return profile.model_copy(update={"version": _content_hash(profile)})


def _validate_ids(raw: dict[str, Any]) -> None:
    """Reject any entry missing an ``id``, and any ``id`` reused across entries.

    Checked on the raw dict, before Pydantic construction, so the error names
    the section and index the user actually needs to go fix, rather than a
    generic "field required" pointing at a constructed-and-discarded object.
    """
    seen: dict[str, tuple[str, int]] = {}
    for section in _ID_SECTIONS:
        for index, entry in enumerate(raw.get(section, [])):
            entry_id = entry.get("id")
            if entry_id is None or not str(entry_id).strip():
                raise ProfileValidationError(
                    f'Entry {index} in "{section}" has no "id". Add a stable, '
                    f'unique "id" field to every entry in the "{section}" '
                    f"section of your JSON Resume file -- this is a required "
                    f"extension this system relies on to keep generated "
                    f'resumes traceably linked back to this exact fact. Once '
                    f"set, an id must never change or be reused, even if the "
                    f'entry is later edited. Example: "id": "{section}-{index}".'
                )
            entry_id = str(entry_id)
            if entry_id in seen:
                other_section, other_index = seen[entry_id]
                raise ProfileValidationError(
                    f"Duplicate id {entry_id!r}: used by entry {other_index} "
                    f'in "{other_section}" and entry {index} in "{section}". '
                    f"Every id must be unique across the whole profile, not "
                    f"just within one section."
                )
            seen[entry_id] = (section, index)


def _map_basics(raw: dict[str, Any]) -> dict[str, Any]:
    location = raw.get("location")
    return {
        "name": raw.get("name"),
        "email": raw.get("email"),
        "phone": raw.get("phone"),
        "summary": raw.get("summary"),
        # Structured basics.location (JSON Resume's {address, city, ...}
        # object) is a named, tracked out-of-scope gap (ADR-0017) -- only a
        # plain string location is imported.
        "location": location if isinstance(location, str) else None,
    }


def _map_work(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(entry["id"]),
        "name": entry.get("name"),
        "position": entry.get("position"),
        "start_date": entry.get("startDate"),
        "end_date": entry.get("endDate"),
        "highlights": entry.get("highlights", []),
    }


def _map_education(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(entry["id"]),
        "institution": entry.get("institution"),
        "area": entry.get("area"),
        "study_type": entry.get("studyType"),
        "start_date": entry.get("startDate"),
        "end_date": entry.get("endDate"),
    }


def _map_skill(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(entry["id"]),
        "name": entry.get("name"),
        "level": entry.get("level"),
        "keywords": entry.get("keywords", []),
    }


def _map_project(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(entry["id"]),
        "name": entry.get("name"),
        "description": entry.get("description"),
        "highlights": entry.get("highlights", []),
        "keywords": entry.get("keywords", []),
    }


def _content_hash(profile: MasterProfile) -> str:
    """A deterministic hash over exactly the grounding-relevant fields.

    Same modeled content -> same hash, regardless of the raw file's key
    order or whitespace -- computed from the already-validated
    :class:`MasterProfile`'s own canonical dump, not the raw JSON text.
    """
    grounding = profile.model_dump(mode="json", exclude={"version"})
    canonical = json.dumps(grounding, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"
