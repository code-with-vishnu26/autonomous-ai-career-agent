"""Phase 67 (ADR-0085): prepare_application_for_review's browserless logic.

The real LLM tailoring (`ResumeVariantEngine.build_materials`) and provider
selection are monkeypatched with lightweight fakes -- these tests exercise
only the new logic: building a READY_FOR_REVIEW ApplicationSession from
tailored materials without a browser, and raising TruthfulnessRejectedError
when the gate refuses the draft.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from career_agent import cli
from career_agent.core.config import Settings
from career_agent.domain.models import (
    BasicsSection,
    MasterProfile,
    Opportunity,
    Provenance,
)


def _opportunity() -> Opportunity:
    return Opportunity(
        id="opp-1",
        company_id="acme",
        canonical_company="Acme Corp",
        title="Backend Engineer",
        source="ats_api",
        source_url="https://boards.greenhouse.io/acme/jobs/1",
        provenance=Provenance(
            method="structured_api",
            reference="https://boards.greenhouse.io/acme/jobs/1",
            extraction_confidence=1.0,
        ),
        description_raw="Python role.",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _profile() -> MasterProfile:
    return MasterProfile(
        version="sha256:x",
        basics=BasicsSection(name="Ada", email="ada@example.com", summary="Eng."),
    )


@pytest.fixture(autouse=True)
def _stub_llm_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize provider selection + the promptfoo gate -- not under test."""
    verifier = SimpleNamespace(prompt_version="v1", provider_id="fake")
    monkeypatch.setattr(cli, "select_claim_verifier", lambda _settings: verifier)
    monkeypatch.setattr(cli, "select_content_drafter", lambda _settings: object())
    monkeypatch.setattr(cli, "select_semantic_matcher", lambda _settings: object())
    monkeypatch.setattr(
        cli, "verify_promptfoo_results", lambda *_a, **_k: None
    )


async def test_builds_a_browserless_ready_for_review_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    variant = SimpleNamespace(id="variant-9")
    materials = SimpleNamespace(
        tailoring=SimpleNamespace(submittable=object()),
        cover_letter=SimpleNamespace(body="Dear Acme..."),
        closest_prior_variant=None,
        new_variant=variant,
    )

    async def _fake_build_materials(self, *_a, **_k):  # noqa: ANN001, ANN002
        return materials

    monkeypatch.setattr(
        "career_agent.agents.resume.materials.ResumeVariantEngine.build_materials",
        _fake_build_materials,
    )
    saved: list[object] = []
    monkeypatch.setattr(
        "career_agent.storage.sqlite.SqliteResumeVariantStore.save",
        lambda self, v, *, user_id: saved.append((v, user_id)),
    )
    monkeypatch.setattr(
        "career_agent.storage.sqlite.SqliteResumeVariantStore.by_category",
        lambda self, category: [],
    )

    settings = Settings(_env_file=None)
    settings = settings.model_copy(update={"database_path": str(tmp_path / "db")})

    session = await cli.prepare_application_for_review(
        opportunity=_opportunity(),
        profile=_profile(),
        settings=settings,
        user_id="user-1",
    )

    assert session.status == "READY_FOR_REVIEW"
    assert session.company == "Acme Corp"
    assert session.job_title == "Backend Engineer"
    assert session.opportunity_id == "opp-1"
    assert session.resume_variant_id == "variant-9"
    assert session.cover_letter_body == "Dear Acme..."
    # Browserless: no fields pre-filled here; that happens at submit.
    assert session.filled_fields == []
    assert session.detected_fields == []
    assert saved == [(variant, "user-1")]


async def test_raises_when_truthfulness_gate_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rejection = SimpleNamespace(category="fabrication", detail="Invented a job.")
    materials = SimpleNamespace(
        tailoring=SimpleNamespace(
            submittable=None,
            application=SimpleNamespace(
                resume=SimpleNamespace(
                    truthfulness=SimpleNamespace(rejections=[rejection])
                )
            ),
        ),
        cover_letter=None,
        closest_prior_variant=None,
        new_variant=None,
    )

    async def _fake_build_materials(self, *_a, **_k):  # noqa: ANN001, ANN002
        return materials

    monkeypatch.setattr(
        "career_agent.agents.resume.materials.ResumeVariantEngine.build_materials",
        _fake_build_materials,
    )
    monkeypatch.setattr(
        "career_agent.storage.sqlite.SqliteResumeVariantStore.by_category",
        lambda self, category: [],
    )

    settings = Settings(_env_file=None)
    settings = settings.model_copy(update={"database_path": str(tmp_path / "db")})

    with pytest.raises(cli.TruthfulnessRejectedError, match="fabrication"):
        await cli.prepare_application_for_review(
            opportunity=_opportunity(),
            profile=_profile(),
            settings=settings,
            user_id="user-1",
        )
