"""Phase 59 (ADR-0076): startup configuration validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from career_agent.core.config import Settings
from career_agent.core.startup_validation import validate_startup


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)  # no .env in this empty directory
    for var in ("GROQ_API_KEY", "ANTHROPIC_API_KEY", "JWT_SECRET_KEY", "DATABASE_URL"):
        monkeypatch.delenv(var, raising=False)


def test_missing_jwt_secret_is_a_warning_in_development() -> None:
    report = validate_startup(Settings(environment="development"))
    assert report.ok
    assert any("JWT_SECRET_KEY" in message for message in report.warnings)


def test_missing_jwt_secret_is_an_error_in_production() -> None:
    report = validate_startup(Settings(environment="production"))
    assert not report.ok
    assert any("JWT_SECRET_KEY" in message for message in report.errors)


def test_configured_jwt_secret_in_production_has_no_jwt_error() -> None:
    report = validate_startup(
        Settings(environment="production", jwt_secret_key="s", jwt_cookie_secure=True)
    )
    assert not any("JWT_SECRET_KEY" in message for message in report.errors)


def test_missing_llm_provider_is_a_warning() -> None:
    report = validate_startup(Settings())
    assert any("GROQ_API_KEY" in message for message in report.warnings)


def test_configured_llm_provider_has_no_warning() -> None:
    report = validate_startup(Settings(groq_api_key="k"))
    assert not any("GROQ_API_KEY" in message for message in report.warnings)


def test_database_url_set_warns_it_is_not_yet_consumed() -> None:
    report = validate_startup(Settings(database_url="postgresql://x"))
    assert any("DATABASE_URL" in message for message in report.warnings)


def test_database_url_unset_has_no_warning_about_it() -> None:
    report = validate_startup(Settings())
    assert not any("DATABASE_URL" in message for message in report.warnings)


def test_production_without_cookie_secure_warns() -> None:
    report = validate_startup(
        Settings(environment="production", jwt_secret_key="s", jwt_cookie_secure=False)
    )
    assert any("JWT_COOKIE_SECURE" in message for message in report.warnings)


def test_development_without_cookie_secure_has_no_warning_about_it() -> None:
    report = validate_startup(Settings(environment="development"))
    assert not any("JWT_COOKIE_SECURE" in message for message in report.warnings)
