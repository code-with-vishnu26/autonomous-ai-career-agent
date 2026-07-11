"""Job Search Preferences: a search/behavior configuration, not a fact record.

Pure data, validation, and one deterministic algorithm (query generation)
only -- no I/O, matching every other module in this package. See ADR-0064
for why this is a wholly separate model from
:class:`~career_agent.domain.models.MasterProfile`, never merged into it.

Unlike ``MasterProfile``, this schema is entirely this project's own design
(not JSON Resume), so its on-disk field names are exactly its Python field
names -- no camelCase-to-snake_case mapping layer, and therefore none of the
"the loader expects a different shape than the model" confusion that
``storage/profile.py`` has to document and guard against for the master
profile (see that module's docstring, and Phase 36/39's history).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

EmploymentType = Literal[
    "full_time", "part_time", "contract", "internship", "temporary"
]
WorkMode = Literal["remote", "hybrid", "onsite"]
Seniority = Literal[
    "intern", "entry", "junior", "mid", "senior", "lead", "principal", "staff"
]
AtsProvider = Literal["greenhouse", "lever", "ashby", "workday"]


class JobPreferences(BaseModel):
    """What kind of job the user is looking for, and how to behave.

    Distinct from :class:`MasterProfile`'s "what is true about the
    candidate" (ADR-0064) -- this is search/behavior configuration, not a
    fact record. Every field is optional / defaults to an empty collection:
    an absent preference means "no constraint," never an implicit
    exclusion. Fields
    marked *not yet enforced* below are captured now as configuration
    surface for a future phase to wire up; storing them today does not
    claim they currently change any runtime behavior beyond what each
    docstring says explicitly. In particular:

    - ``require_human_confirmation`` is informational only. The real
      confirmation boundary (:func:`~career_agent.cli.confirm_submission`,
      the execution-safety boundary, ADR-0018/0050) is hardcoded and does
      not read this field -- setting it to ``False`` has **no effect** on
      the mandatory confirmation step; the field cannot be used to bypass
      it.
    - ``auto_tailor_resume`` and ``auto_generate_cover_letter`` are not yet
      wired to any conditional behavior; ``apply`` always tailors today,
      and cover-letter generation does not exist yet in this codebase.
    - ``max_applications_per_day`` is stored but not yet enforced by
      ``auto``/``apply``.
    - ``blacklisted_companies``/``preferred_companies``/``industries``/
      ``salary_*``/``visa_sponsorship_required``/``work_authorization``/
      ``preferred_ats_providers`` are not yet consumed by the Decide layer
      (:mod:`career_agent.agents.planner.decide`), which retains its own,
      separate ``Settings``-driven filters
      (``decide_blacklist_companies``/``decide_allowed_locations``/
      ``decide_remote_only``) as the authoritative discovery/ranking filter
      for now. Reconciling the two is a named, deferred decision, not an
      oversight.

    Only ``preferred_titles``/``alternative_titles``/``work_mode``/
    ``countries``/``keywords_exclude`` are actually consumed this phase, by
    :func:`generate_search_queries`.
    """

    preferred_titles: list[str] = Field(default_factory=list)
    alternative_titles: list[str] = Field(default_factory=list)
    seniority: Seniority | None = None
    experience_years_min: int | None = None
    experience_years_max: int | None = None
    employment_types: list[EmploymentType] = Field(default_factory=list)
    work_mode: list[WorkMode] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    states: list[str] = Field(default_factory=list)
    cities: list[str] = Field(default_factory=list)
    salary_min: float | None = None
    salary_max: float | None = None
    #: Free text (e.g. ``"USD"``, ``"LPA"``) -- deliberately not a strict
    #: ISO-4217 code: "LPA" (lakhs per annum) and similar regional units in
    #: real use are not currency codes at all.
    salary_currency: str | None = None
    preferred_companies: list[str] = Field(default_factory=list)
    blacklisted_companies: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    #: ``None`` means "not specified" -- never an implicit "no," the same
    #: discipline as ``LegalStatusSection`` (ADR-0032).
    visa_sponsorship_required: bool | None = None
    work_authorization: str | None = None
    preferred_technologies: list[str] = Field(default_factory=list)
    keywords_include: list[str] = Field(default_factory=list)
    keywords_exclude: list[str] = Field(default_factory=list)
    max_applications_per_day: int | None = None
    require_human_confirmation: bool = True
    auto_tailor_resume: bool = True
    auto_generate_cover_letter: bool = False
    preferred_ats_providers: list[AtsProvider] = Field(default_factory=list)
    #: IANA time zone name (e.g. ``"Asia/Kolkata"``); stored as free text,
    #: not validated against a timezone database.
    time_zone: str | None = None

    @model_validator(mode="after")
    def _validate_ranges(self) -> JobPreferences:
        if self.experience_years_min is not None and self.experience_years_min < 0:
            raise ValueError("experience_years_min must be >= 0")
        if self.experience_years_max is not None and self.experience_years_max < 0:
            raise ValueError("experience_years_max must be >= 0")
        if (
            self.experience_years_min is not None
            and self.experience_years_max is not None
            and self.experience_years_min > self.experience_years_max
        ):
            raise ValueError(
                "experience_years_min must be <= experience_years_max"
            )
        if self.salary_min is not None and self.salary_min < 0:
            raise ValueError("salary_min must be >= 0")
        if self.salary_max is not None and self.salary_max < 0:
            raise ValueError("salary_max must be >= 0")
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_min > self.salary_max
        ):
            raise ValueError("salary_min must be <= salary_max")
        if (
            self.max_applications_per_day is not None
            and self.max_applications_per_day < 1
        ):
            raise ValueError("max_applications_per_day must be >= 1")
        return self


def _dedup_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        cleaned = item.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def generate_search_queries(
    preferences: JobPreferences, *, max_queries: int = 10
) -> list[str]:
    """Turn preferences into a bounded list of search-query strings.

    Deterministic, pure, and the only part of :class:`JobPreferences` wired
    into discovery this phase (ADR-0064): title x location combinations
    (``"Remote"`` when ``"remote" in work_mode``, then each configured
    country), falling back to the bare title when no location is
    configured. Deduplicated, order-preserving, capped at ``max_queries``
    to bound the number of discovery API calls a large preference set could
    otherwise fan out into. A query is dropped if it contains any
    ``keywords_exclude`` term (case-insensitive substring) -- the same
    "never search for what the user explicitly excluded" intent as the
    field's name. Returns an empty list if no titles are configured at all
    (nothing to search for), which callers must treat as "no
    preference-derived queries," not an error.
    """
    titles = _dedup_preserve_order(
        preferences.preferred_titles + preferences.alternative_titles
    )
    if not titles:
        return []

    exclude_terms = [
        k.strip().lower() for k in preferences.keywords_exclude if k.strip()
    ]

    def _excluded(text: str) -> bool:
        lowered = text.lower()
        return any(term in lowered for term in exclude_terms)

    location_tokens: list[str] = []
    if "remote" in preferences.work_mode:
        location_tokens.append("Remote")
    location_tokens += _dedup_preserve_order(preferences.countries)

    queries: list[str] = []
    for title in titles:
        if _excluded(title):
            continue
        candidates = (
            [f"{title} {loc}".strip() for loc in location_tokens]
            if location_tokens
            else [title]
        )
        for candidate in candidates:
            if candidate in queries or _excluded(candidate):
                continue
            queries.append(candidate)
            if len(queries) >= max_queries:
                return queries
    return queries
