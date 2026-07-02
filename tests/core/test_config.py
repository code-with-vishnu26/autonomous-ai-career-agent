"""Tests for career_agent.core.config."""

from __future__ import annotations

from career_agent.core.config import Settings


def test_settings_loads_without_a_dotenv_file_present(monkeypatch, tmp_path) -> None:
    """Settings must not crash when no .env exists (e.g. a fresh checkout);
    every field has a sane default or is Optional."""
    monkeypatch.chdir(tmp_path)  # no .env in this empty directory
    for var in (
        "ANTHROPIC_API_KEY",
        "EXA_API_KEY",
        "GOOGLE_CSE_API_KEY",
        "GOOGLE_CSE_ID",
    ):
        monkeypatch.delenv(var, raising=False)
    settings = Settings()
    assert settings.exa_api_key is None
    assert settings.database_path == "data/career_agent.db"
    assert settings.log_level == "INFO"


def test_settings_reads_from_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EXA_API_KEY", "test-key-123")
    settings = Settings()
    assert settings.exa_api_key == "test-key-123"


def test_settings_never_required_to_construct_a_provider() -> None:
    """The whole point: a provider takes a bare string, never a Settings
    instance -- confirmed by construction succeeding with a plain literal."""
    from career_agent.plugins.search.exa import ExaSearchProvider

    class _NullClient:
        async def get_json(self, url, *, params=None):  # pragma: no cover
            raise AssertionError("not used in this test")

        async def post_json(self, url, *, json, headers=None):  # pragma: no cover
            raise AssertionError("not used in this test")

    provider = ExaSearchProvider(
        api_key="fake-key-not-a-settings-object", client=_NullClient()
    )
    assert provider._api_key == "fake-key-not-a-settings-object"
