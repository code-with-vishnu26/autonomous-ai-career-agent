"""Phase 13 / ADR-0037: the real `career-agent discover` command core."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from career_agent.cli import run_discover_command
from career_agent.domain.models import Opportunity, Provenance
from career_agent.storage.sqlite import SqliteOpportunityRepository


def _opp(opportunity_id: str, ats_ref: str | None = "n1") -> Opportunity:
    return Opportunity(
        id=opportunity_id,
        company_id="acme",
        canonical_company="acme",
        title=f"Engineer {opportunity_id}",
        source="job_board",
        source_url="https://example.invalid/1",
        provenance=Provenance(
            method="structured_api",
            reference="https://example.invalid/api",
            extraction_confidence=1.0,
        ),
        ats_ref=ats_ref,
        description_raw="",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class _FakeSource:
    def __init__(self, found):
        self._found = found

    async def fetch(self, since):
        return self._found


class _BrokenSource:
    async def fetch(self, since):
        raise RuntimeError("api down")


async def test_discover_persists_dedups_and_writes_handoff_files(
    tmp_path: Path, capsys
) -> None:
    repo = SqliteOpportunityRepository(tmp_path / "db.sqlite")
    out_dir = tmp_path / "opps"
    sources = [
        ("one", _FakeSource([_opp("a"), _opp("b")])),
        ("two", _FakeSource([_opp("a")])),  # duplicate across sources
        ("broken", _BrokenSource()),  # one failing source must not sink the run
    ]
    code = await run_discover_command(
        sources, repo, since=datetime(2026, 1, 1, tzinfo=UTC), out_dir=out_dir
    )
    assert code == 0
    written = sorted(path.name for path in out_dir.glob("*.json"))
    assert written == ["a.json", "b.json"]  # duplicate produced no second file

    # The handoff file is the exact Opportunity JSON `apply` consumes.
    loaded = Opportunity.model_validate(
        json.loads((out_dir / "a.json").read_text())
    )
    assert loaded.id == "a"

    output = capsys.readouterr().out
    assert "[broken] FAILED: api down" in output  # visible, never silent
    assert "[two] 1 fetched, 0 new" in output
    assert "2 new opportunities" in output


async def test_discover_observation_hooks_are_optional_and_additive(
    tmp_path: Path,
) -> None:
    """Phase 63: on_new_opportunity/on_source_error are opt-in, no behavior change."""
    repo = SqliteOpportunityRepository(tmp_path / "db.sqlite")
    out_dir = tmp_path / "opps"
    sources = [
        ("one", _FakeSource([_opp("a"), _opp("b")])),
        ("two", _FakeSource([_opp("a")])),  # duplicate across sources
        ("broken", _BrokenSource()),
    ]
    new_ids: list[str] = []
    errors: list[str] = []
    code = await run_discover_command(
        sources,
        repo,
        since=datetime(2026, 1, 1, tzinfo=UTC),
        out_dir=out_dir,
        on_new_opportunity=lambda opp: new_ids.append(opp.id),
        on_source_error=lambda name, exc: errors.append(f"{name}: {exc}"),
    )
    assert code == 0
    assert sorted(new_ids) == ["a", "b"]
    assert errors == ["broken: api down"]
