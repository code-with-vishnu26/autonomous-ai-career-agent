"""Phase 15 / ADR-0039: the Learn pillar's honest funnel counts."""

from __future__ import annotations

from pathlib import Path

from career_agent.agents.learning.funnel import (
    SMALL_SAMPLE_CAVEAT,
    ats_band,
    build_funnel_report,
    render_funnel_report,
)
from career_agent.cli import run_outcome_command


def _app_row(app_id: str, ats: float | None, prompt: str = "p1") -> dict:
    return {
        "id": app_id,
        "prompt_version": prompt,
        "profile_version": "v1",
        "ats_total": ats,
    }


def _outcome(app_id: str, kind: str, stage: str | None = None) -> dict:
    return {"application_id": app_id, "kind": kind, "stage": stage}


def test_ats_bands():
    assert ats_band(None) == "ungated"
    assert ats_band(59.9) == "<60"
    assert ats_band(74.99) == "60-74"
    assert ats_band(75.0) == "75-84"
    assert ats_band(91.0) == "85+"


def test_full_history_counted_and_rejection_stages_split():
    """An application that was viewed, got a response, interviewed, then
    was rejected post-interview counts at EVERY stage it reached -- and
    post-interview vs at-screen rejections are separated facts."""
    apps = [_app_row("a", 80.0), _app_row("b", 80.0)]
    outcomes = [
        _outcome("a", "viewed"),
        _outcome("a", "response"),
        _outcome("a", "interview"),
        _outcome("a", "rejection", "post-interview"),
        _outcome("b", "rejection", "screen"),
    ]
    report = build_funnel_report(apps, outcomes)
    assert len(report.variants) == 1
    variant = report.variants[0]
    assert variant.applications == 2
    assert variant.viewed == 1
    assert variant.response == 1
    assert variant.interview == 1
    assert variant.rejection == 2
    assert variant.rejection_stages == {"post-interview": 1, "screen": 1}


def test_variants_keyed_by_prompt_profile_and_ats_band():
    apps = [_app_row("a", 80.0, prompt="p1"), _app_row("b", 55.0, prompt="p2")]
    report = build_funnel_report(apps, [])
    keys = {(v.prompt_version, v.band) for v in report.variants}
    assert keys == {("p1", "75-84"), ("p2", "<60")}


def test_report_is_raw_counts_with_mandatory_caveat_no_verdicts():
    """The statistical-honesty guarantee: a 3-vs-1 comparison renders as
    exactly that -- raw numbers -- with the small-sample caveat ALWAYS
    present and no prescriptive better/worse/significant language."""
    apps = [_app_row(f"a{i}", 80.0, prompt="p1") for i in range(12)] + [
        _app_row(f"b{i}", 80.0, prompt="p2") for i in range(9)
    ]
    outcomes = [_outcome(f"a{i}", "interview") for i in range(3)] + [
        _outcome("b0", "interview")
    ]
    rendered = render_funnel_report(build_funnel_report(apps, outcomes))
    assert SMALL_SAMPLE_CAVEAT in rendered
    assert "12 applied" in rendered
    assert "3 interviews" in rendered
    assert "9 applied" in rendered
    assert "1 interviews" in rendered
    for banned in ("significant", "better", "worse", "recommend", "winner"):
        assert banned not in rendered.lower()


def test_caveat_present_even_on_an_empty_report():
    rendered = render_funnel_report(build_funnel_report([], []))
    assert SMALL_SAMPLE_CAVEAT in rendered


def test_outcome_command_refuses_unknown_application_id(tmp_path: Path, capsys):
    code = run_outcome_command(tmp_path / "db.sqlite", "ghost", "viewed", None)
    assert code == 1
    assert "No recorded application" in capsys.readouterr().out


def test_outcome_command_refuses_unknown_kind(tmp_path: Path, capsys):
    code = run_outcome_command(tmp_path / "db.sqlite", "any", "ghosted", None)
    assert code == 1
    assert "Unknown outcome kind" in capsys.readouterr().out
