"""Per-variant funnel counts from real outcomes (Phase 15, ADR-0039).

**Statistical honesty at personal N is the whole design.** This system
will see tens of applications, not thousands. So this module reports raw
counts and funnel-stage conversion ONLY: no significance testing, no
Thompson sampling / bandit routing, no "variant A is better" verdicts --
below N≈:data:`MIN_N_FOR_COMPARISON` per variant, those would be noise
dressed as insight. "3/12 interviews vs 1/9" is reported as exactly that,
and every rendered report carries an explicit small-sample caveat
(:data:`SMALL_SAMPLE_CAVEAT`). Insights are descriptive, never
prescriptive, until N genuinely supports more -- and "more" is its own
future pre-brief, not a threshold this module silently crosses.

Variants are keyed to ``(prompt_version, profile_version, ATS band)`` --
the three things that actually distinguish one application's *content
recipe* from another's. The FULL outcome history is read, not just the
latest event: a rejection after an interview and a rejection at screen
are different facts (the ``stage`` field carries that), and an
application that was viewed, got a response, then a rejection counts in
all three stages -- the funnel counts events reached, not final states.
"""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, Field

#: Below this many applications per variant, comparisons are noise --
#: recorded here as data so the boundary is visible, not folklore.
MIN_N_FOR_COMPARISON = 50

SMALL_SAMPLE_CAVEAT = (
    "CAVEAT: personal-scale sample sizes. These are raw counts, not "
    "statistics -- differences between variants at this N are not "
    "evidence about which recipe to prefer. No significance testing or "
    "automated routing is applied below N="
    f"{MIN_N_FOR_COMPARISON} per variant (ADR-0039)."
)

_FUNNEL_KINDS = ("viewed", "response", "interview", "offer", "rejection")


def ats_band(total: float | None) -> str:
    """Bucket an ATS score into a coarse, honest band (or 'ungated')."""
    if total is None:
        return "ungated"
    if total >= 85:
        return "85+"
    if total >= 75:
        return "75-84"
    if total >= 60:
        return "60-74"
    return "<60"


class VariantFunnel(BaseModel):
    """Raw counts for one (prompt, profile, ATS band) recipe. Counts only."""

    prompt_version: str
    profile_version: str
    band: str
    applications: int = 0
    viewed: int = 0
    response: int = 0
    interview: int = 0
    offer: int = 0
    rejection: int = 0
    #: Rejection stages matter: post-interview != at-screen.
    rejection_stages: dict[str, int] = Field(default_factory=dict)


class FunnelReport(BaseModel):
    """Every variant's raw funnel, plus the mandatory caveat."""

    variants: list[VariantFunnel]
    caveat: str = SMALL_SAMPLE_CAVEAT


def build_funnel_report(
    application_rows: list[dict[str, object]],
    outcome_rows: list[dict[str, object]],
) -> FunnelReport:
    """Aggregate the FULL outcome history into per-variant raw counts."""
    by_variant: dict[tuple[str, str, str], VariantFunnel] = {}
    variant_of_application: dict[str, tuple[str, str, str]] = {}

    for row in application_rows:
        key = (
            str(row.get("prompt_version", "")),
            str(row.get("profile_version", "")),
            ats_band(
                float(row["ats_total"]) if row.get("ats_total") is not None else None
            ),
        )
        variant_of_application[str(row["id"])] = key
        if key not in by_variant:
            by_variant[key] = VariantFunnel(
                prompt_version=key[0], profile_version=key[1], band=key[2]
            )
        by_variant[key].applications += 1

    stage_counts: dict[tuple[str, str, str], dict[str, int]] = defaultdict(dict)
    for outcome in outcome_rows:
        key = variant_of_application.get(str(outcome["application_id"]))
        if key is None:
            continue  # outcome for an application this store never recorded
        kind = str(outcome["kind"])
        variant = by_variant[key]
        if kind in _FUNNEL_KINDS:
            setattr(variant, kind, getattr(variant, kind) + 1)
        if kind == "rejection":
            stage = str(outcome.get("stage") or "unspecified")
            stages = stage_counts[key]
            stages[stage] = stages.get(stage, 0) + 1
            variant.rejection_stages = dict(stages)

    ordered = sorted(
        by_variant.values(),
        key=lambda v: (v.prompt_version, v.profile_version, v.band),
    )
    return FunnelReport(variants=ordered)


def render_funnel_report(report: FunnelReport) -> str:
    """Human-readable raw-counts report. The caveat is always present."""
    lines: list[str] = [report.caveat, ""]
    if not report.variants:
        lines.append("No applications recorded yet.")
    for variant in report.variants:
        lines.append(
            f"[prompt={variant.prompt_version} profile={variant.profile_version} "
            f"ats={variant.band}] {variant.applications} applied | "
            f"{variant.viewed} viewed | {variant.response} responses | "
            f"{variant.interview} interviews | {variant.offer} offers | "
            f"{variant.rejection} rejections"
        )
        for stage, count in sorted(variant.rejection_stages.items()):
            lines.append(f"    rejection at {stage}: {count}")
    return "\n".join(lines)
