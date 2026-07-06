"""Cross-platform text-I/O correctness: every repo-owned read/write of
real (potentially non-ASCII) content must use an explicit ``encoding=
"utf-8"``, never the platform default.

Found from a real Windows pytest run (430 passed, 33 skipped, 11 failed) on
merged `main`: `Path.read_text()`/`Path.write_text()` with no explicit
``encoding`` argument silently falls back to ``locale.getpreferredencoding()``
-- cp1252 on a default Windows install, UTF-8 on this project's Linux/macOS
development and CI sandboxes. Two distinct, real defects followed:

- `tests/_fakes.py::load_fixture` reading `tests/fixtures/hn/whoishiring.json`
  (which carries genuine accented and CJK text -- "Résumé", "リモート | 正社員")
  raised ``UnicodeDecodeError: 'charmap' codec can't decode byte 0x8f`` on
  Windows, failing every test that loads it (`test_hn.py`, `test_discovery_hn.py`).
- `cli.py`'s opportunity-handoff write (`handoff.write_text(opportunity
  .model_dump_json(indent=2))`) raised ``UnicodeEncodeError`` on Windows the
  moment a real discovered opportunity's title/description contained a
  character cp1252 cannot represent at all (observed: U+1F30D 🌍).

This suite does not simulate "being on Windows" (this sandbox's own OS-level
default encoding is UTF-8, and monkeypatching the Python-level
``locale.getpreferredencoding`` function does not change what CPython's `_io`
module actually consults for it -- confirmed empirically, not assumed). It
proves the fix two ways instead, together a complete guarantee: (1) every
fixed call site is spied on to confirm it passes the literal string
``"utf-8"`` as its ``encoding`` argument -- a property that holds identically
regardless of platform, because an explicit argument always overrides the
platform default; (2) real non-ASCII content (CJK, accented Latin, emoji)
is round-tripped through each fixed function on this sandbox's real
filesystem, proving the values survive correctly, not just that the call
doesn't crash.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from career_agent.cli import _load_opportunity, run_discover_command
from career_agent.domain.models import LegalStatusSection, Opportunity, Provenance
from career_agent.llm.promptfoo_gate import (
    diagnose_prompt_drift,
    verify_promptfoo_results,
)
from career_agent.storage.profile import load_master_profile, save_legal_status
from tests._fakes import load_fixture


def _spy_on_encoding(monkeypatch: pytest.MonkeyPatch, method_name: str) -> list[object]:
    """Record the ``encoding=`` kwarg passed to every ``Path.<method_name>``
    call for the duration of the test, then restore the real method.

    Works identically on any OS: this inspects the argument the code
    actually passes, not the platform's actual default-encoding behavior
    (which this sandbox cannot simulate for Windows -- see module
    docstring). An explicit ``"utf-8"`` here is a guarantee that holds on
    every platform, by Python's own documented contract for ``encoding=``.
    """
    seen: list[object] = []
    original = getattr(Path, method_name)

    def spy(self: Path, *args: object, **kwargs: object) -> object:
        seen.append(kwargs.get("encoding"))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, method_name, spy)
    return seen


# ---------------------------------------------------------------------------
# Family A: tests/_fakes.py::load_fixture
# ---------------------------------------------------------------------------


def test_load_fixture_passes_explicit_utf8(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _spy_on_encoding(monkeypatch, "read_text")
    load_fixture("hn", "whoishiring.json")
    assert seen == ["utf-8"]


def test_load_fixture_preserves_real_multilingual_content() -> None:
    """The exact fixture that crashed on Windows -- proves the accented
    and CJK substrings decode correctly, not just that loading succeeds."""
    fixture = load_fixture("hn", "whoishiring.json")
    # ensure_ascii=False so real Unicode characters appear literally in the
    # dumped text instead of being escaped to \uXXXX sequences.
    raw = json.dumps(fixture, ensure_ascii=False)
    assert "Résumé" in raw
    assert "リモート" in raw  # "Remote"
    assert "正社員" in raw  # "regular employee"


# ---------------------------------------------------------------------------
# Family B: cli.py's opportunity handoff write/read
# ---------------------------------------------------------------------------


def _emoji_opportunity() -> Opportunity:
    return Opportunity(
        id="opp-emoji",
        company_id="acme",
        canonical_company="acme.com",
        title="Remote Software Engineer \U0001f30d",  # U+1F30D EARTH GLOBE
        source="ats_api",
        source_url="https://boards.greenhouse.io/acme/jobs/1",
        provenance=Provenance(
            method="structured_api",
            reference="https://boards.greenhouse.io/acme/jobs/1",
            extraction_confidence=1.0,
        ),
        description_raw="Über-collaborative team, 日本語 OK.",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class _SingleSource:
    def __init__(self, opportunity: Opportunity) -> None:
        self._opportunity = opportunity

    async def fetch(self, since: datetime) -> list[Opportunity]:
        return [self._opportunity]


async def test_opportunity_handoff_write_passes_explicit_utf8(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from career_agent.storage.sqlite import SqliteOpportunityRepository

    seen = _spy_on_encoding(monkeypatch, "write_text")
    repo = SqliteOpportunityRepository(tmp_path / "db.sqlite")
    await run_discover_command(
        [("boardA", _SingleSource(_emoji_opportunity()))],
        repo,
        since=datetime(2026, 1, 1, tzinfo=UTC),
        out_dir=tmp_path / "opps",
    )
    assert seen == ["utf-8"]


async def test_opportunity_handoff_round_trips_emoji_and_cjk(
    tmp_path: Path,
) -> None:
    """The exact real-world shape that crashed on Windows: an emoji in the
    title, non-Latin script in the description -- written by discover's
    real handoff path, read back by apply's real loader, content intact."""
    from career_agent.storage.sqlite import SqliteOpportunityRepository

    repo = SqliteOpportunityRepository(tmp_path / "db.sqlite")
    out_dir = tmp_path / "opps"
    await run_discover_command(
        [("boardA", _SingleSource(_emoji_opportunity()))],
        repo,
        since=datetime(2026, 1, 1, tzinfo=UTC),
        out_dir=out_dir,
    )
    handoff_path = out_dir / "opp-emoji.json"
    assert handoff_path.exists()

    # The file on disk is valid, real UTF-8 JSON -- decode the raw bytes
    # directly (not via the loader) to prove the write itself is correct.
    raw_bytes = handoff_path.read_bytes()
    payload = json.loads(raw_bytes.decode("utf-8"))
    assert payload["title"] == "Remote Software Engineer \U0001f30d"

    # And the real apply-side loader reads it back correctly too.
    loaded = _load_opportunity(handoff_path)
    assert loaded.title == "Remote Software Engineer \U0001f30d"
    assert loaded.description_raw == "Über-collaborative team, 日本語 OK."


async def test_opportunity_read_passes_explicit_utf8(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "opp.json"
    path.write_text(_emoji_opportunity().model_dump_json(), encoding="utf-8")
    seen = _spy_on_encoding(monkeypatch, "read_text")
    _load_opportunity(path)
    assert seen == ["utf-8"]


# ---------------------------------------------------------------------------
# storage/profile.py: load_master_profile / save_legal_status
# ---------------------------------------------------------------------------


def _profile_payload(name: str) -> dict:
    return {
        "basics": {"name": name, "email": "a@example.com", "summary": "x"},
        "work": [],
        "education": [],
        "skills": [],
        "projects": [],
    }


def test_load_master_profile_passes_explicit_utf8(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "profile.json"
    path.write_text(
        json.dumps(_profile_payload("José Muñoz")), encoding="utf-8"
    )
    seen = _spy_on_encoding(monkeypatch, "read_text")
    load_master_profile(path)
    assert seen == ["utf-8"]


def test_load_master_profile_preserves_accented_name(tmp_path: Path) -> None:
    path = tmp_path / "profile.json"
    path.write_text(
        json.dumps(_profile_payload("José Muñoz")), encoding="utf-8"
    )
    profile = load_master_profile(path)
    assert profile.basics.name == "José Muñoz"


def test_save_legal_status_round_trips_accented_content(tmp_path: Path) -> None:
    path = tmp_path / "profile.json"
    path.write_text(
        json.dumps(_profile_payload("李雷")), encoding="utf-8"  # "李雷"
    )
    save_legal_status(
        path, LegalStatusSection(work_authorized_us=True, requires_sponsorship=False)
    )
    # Read back with the real, explicit-encoding loader.
    profile = load_master_profile(path)
    assert profile.basics.name == "李雷"
    assert profile.legal_status.work_authorized_us is True
    # And the raw file itself is valid UTF-8-decodable JSON.
    raw = path.read_bytes().decode("utf-8")
    json.loads(raw)  # does not raise


def test_save_legal_status_passes_explicit_utf8_on_both_sides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(_profile_payload("Ada")), encoding="utf-8")
    read_seen = _spy_on_encoding(monkeypatch, "read_text")
    write_seen = _spy_on_encoding(monkeypatch, "write_text")
    save_legal_status(path, LegalStatusSection(work_authorized_us=True))
    assert read_seen == ["utf-8"]
    assert write_seen == ["utf-8"]


# ---------------------------------------------------------------------------
# llm/promptfoo_gate.py: results-file reads
# ---------------------------------------------------------------------------


def _write_results_with_non_ascii_detail(path: Path) -> None:
    payload = {
        "results": {
            "stats": {"successes": 10, "failures": 0, "errors": 0},
            "prompts": [{"raw": "café évaluation prompt"}],
        },
        "config": {"providers": [{"id": "openai:chat:openai/gpt-oss-120b"}]},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_verify_promptfoo_results_passes_explicit_utf8(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_results_with_non_ascii_detail(
        tmp_path / "truthfulness-gate-v2--groq.json"
    )
    seen = _spy_on_encoding(monkeypatch, "read_text")
    verify_promptfoo_results("truthfulness-gate-v2", tmp_path, provider_id="groq")
    assert seen == ["utf-8"]


def test_diagnose_prompt_drift_passes_explicit_utf8(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_results_with_non_ascii_detail(
        tmp_path / "truthfulness-gate-v2--groq.json"
    )
    seen = _spy_on_encoding(monkeypatch, "read_text")
    diagnose_prompt_drift("truthfulness-gate-v2", tmp_path, provider_id="groq")
    assert "utf-8" in seen
