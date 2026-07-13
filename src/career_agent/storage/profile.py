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
    LegalStatusSection,
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


def example_profile_dict() -> dict[str, Any]:
    """A minimal, schema-correct JSON Resume scaffold with placeholder values.

    Phase 25 (ADR-0051): the exact shape :func:`load_master_profile` accepts
    -- JSON Resume with this project's required ``id`` extension on every
    ``work``/``education``/``skills``/``projects`` entry, plus the optional
    ``legal_status`` block. Every value is an obvious placeholder ("Your
    Name", "you@example.com"); nothing here is real evidence, and the
    scaffold's whole purpose is to be *edited* into real facts by the user.
    Kept in lockstep with the loader by a round-trip test, so it can never
    silently drift into an unloadable shape.
    """
    return {
        "basics": {
            "name": "Your Name",
            "email": "you@example.com",
            "phone": "+00 000 000 000",
            "location": "City, Country",
            "summary": (
                "One or two sentences describing who you are professionally. "
                "Replace this with your own summary -- it is the grounding "
                "for every tailored resume."
            ),
        },
        "work": [
            {
                "id": "work-1",
                "name": "Example Company",
                "position": "Your Job Title",
                "startDate": "2022-01-01",
                # Omit "endDate" for a current role; add "endDate": "2024-06-30"
                # (YYYY-MM-DD) for a past one.
                "highlights": [
                    "A concrete, truthful accomplishment with a real metric.",
                    "Another accomplishment -- only claims you can substantiate.",
                ],
            }
        ],
        "education": [
            {
                "id": "education-1",
                "institution": "Example University",
                "area": "Your Field of Study",
                "studyType": "BSc",
                "startDate": "2018-09-01",
                "endDate": "2021-06-01",
            }
        ],
        "skills": [
            {
                "id": "skill-1",
                "name": "Example Skill Group",
                "level": "Advanced",
                "keywords": ["Python", "SQL", "A tool you actually use"],
            }
        ],
        "projects": [
            {
                "id": "project-1",
                "name": "Example Project",
                "description": "What the project was and your role in it.",
                "highlights": ["A truthful, specific outcome."],
                "keywords": ["A relevant technology"],
            }
        ],
    }


def write_profile_scaffold(path: Path) -> bool:
    """Write the example profile to ``path`` if absent; never overwrite.

    Returns ``True`` if the scaffold was written, ``False`` if a file
    already exists at ``path`` (in which case it is left completely
    untouched -- this never destroys a user's real profile). Explicit
    ``encoding="utf-8"`` for the same reason :func:`load_master_profile`
    reads that way.
    """
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(example_profile_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return True


def load_master_profile(path: Path) -> MasterProfile:
    """Load, id-validate, and version a master profile from a JSON Resume file.

    Explicit ``encoding="utf-8"`` -- a real résumé routinely carries
    non-ASCII names/content, and without this, ``Path.read_text()`` falls
    back to the platform's default encoding (cp1252 on Windows), which
    cannot decode it.
    """
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
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
        # legal_status (Phase 8j/13): a this-project extension to JSON
        # Resume, round-tripped by save_legal_status below. Absent keys
        # stay None -- "never asked," never an implicit "no."
        legal_status=LegalStatusSection(**raw.get("legal_status", {})),
    )
    return profile.model_copy(update={"version": compute_profile_version(profile)})


def validate_master_profile_ids(profile: MasterProfile) -> None:
    """Re-run the same id-stability checks on an already-constructed profile.

    Phase 64 (ADR-0082): a web-submitted profile (JSON body, not a JSON
    Resume file) never goes through :func:`load_master_profile` at all, but
    must satisfy the exact same "every id present, none reused across
    sections" guarantee -- reuses :func:`_validate_ids` directly rather than
    re-implementing the check, since a validated :class:`MasterProfile`'s
    own ``model_dump`` uses the identical ``"id"`` key per entry that the
    raw-file check already expects.
    """
    _validate_ids(profile.model_dump(mode="json"))


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


def compute_profile_version(profile: MasterProfile) -> str:
    """A deterministic hash over exactly the grounding-relevant fields.

    Same modeled content -> same hash, regardless of the raw file's key
    order or whitespace -- computed from the already-validated
    :class:`MasterProfile`'s own canonical dump, not the raw JSON text.
    Public (Phase 64, ADR-0082): a DB-backed store recomputes ``version``
    the same way :func:`load_master_profile` always has, rather than
    reimplementing the hash.
    """
    grounding = profile.model_dump(mode="json", exclude={"version"})
    canonical = json.dumps(grounding, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


def save_legal_status(path: Path, legal_status: LegalStatusSection) -> None:
    """Write ``legal_status`` into the profile file -- the first profile writer.

    Phase 13 (ADR-0037): touches ONLY the ``legal_status`` key; every other
    section -- including JSON Resume sections this loader does not model at
    all (awards, publications, ...) -- is preserved byte-for-byte as parsed.
    A ``None`` field is written as ``null`` (still "never asked"), never
    coerced to ``false``. The profile's ``version`` is a content hash
    recomputed at load time, so the next ``load_master_profile`` call
    naturally yields a new version; nothing here (or anywhere) rewrites the
    frozen ``profile_version``/``applicant``/``legal_status`` snapshots
    already recorded on existing Applications -- a version bump never
    retroactively alters history (ADR-0027/0032 discipline).
    """
    # Explicit encoding="utf-8" on both sides -- json.dumps' ensure_ascii
    # default currently makes this write ASCII-only regardless, but the
    # read must be explicit (a real profile carries non-ASCII content),
    # and leaving the write implicit would make this boundary silently
    # depend on an incidental default rather than a guaranteed contract.
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    raw["legal_status"] = legal_status.model_dump(mode="json")
    path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
