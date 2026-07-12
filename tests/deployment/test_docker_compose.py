"""Phase 59 (ADR-0076): structural validation of the Compose files.

Two layers, matching this project's existing real-dependency-or-skip
convention (``tests/integrations/adapters/test_base.py``'s Chromium skip):
plain YAML-structure assertions always run (no Docker required, so CI's
plain ``verify`` job -- no Docker involved -- still exercises them); a real
``docker compose config`` invocation is skipped when the ``docker`` CLI
isn't on PATH, and is the thing CI's dedicated ``docker`` job actually
relies on for full validation (semantic checks -- interpolation, merges,
profiles -- a bare YAML parse can't catch).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(filename: str) -> dict:
    return yaml.safe_load((_REPO_ROOT / filename).read_text(encoding="utf-8"))


def test_base_compose_defines_the_five_named_containers() -> None:
    compose = _load("docker-compose.yml")
    expected = {"backend", "frontend", "nginx", "postgres", "redis"}
    assert set(compose["services"]) == expected


def test_backend_and_frontend_are_built_not_pulled() -> None:
    compose = _load("docker-compose.yml")
    services = compose["services"]
    assert services["backend"]["build"]["dockerfile"] == "Dockerfile.backend"
    assert services["frontend"]["build"]["dockerfile"] == "Dockerfile.frontend"


def test_postgres_and_redis_are_gated_behind_profiles() -> None:
    """Neither is consumed by the app yet (ADR-0076) -- `docker compose up`
    with no ``--profile`` flag must not require either to start."""
    compose = _load("docker-compose.yml")
    assert compose["services"]["postgres"]["profiles"] == ["postgres"]
    assert compose["services"]["redis"]["profiles"] == ["redis"]


def test_backend_has_a_readiness_healthcheck() -> None:
    compose = _load("docker-compose.yml")
    healthcheck = compose["services"]["backend"]["healthcheck"]
    assert "/ready" in " ".join(healthcheck["test"])


def test_nginx_publishes_port_80() -> None:
    compose = _load("docker-compose.yml")
    assert "80:80" in compose["services"]["nginx"]["ports"]


def test_dev_overlay_disables_the_edge_proxy_and_enables_reload() -> None:
    dev = _load("docker-compose.dev.yml")
    assert "--reload" in dev["services"]["backend"]["command"]
    assert "profiles" in dev["services"]["nginx"]


def test_prod_overlay_sets_secure_cookies_and_resource_limits() -> None:
    prod = _load("docker-compose.prod.yml")
    assert prod["services"]["backend"]["environment"]["JWT_COOKIE_SECURE"] == "true"
    assert "resources" in prod["services"]["backend"]["deploy"]


def test_every_compose_file_is_valid_yaml() -> None:
    for filename in (
        "docker-compose.yml",
        "docker-compose.dev.yml",
        "docker-compose.prod.yml",
    ):
        assert _load(filename)["services"]


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI not on PATH")
class TestRealDockerComposeConfig:
    """Semantic validation via the real ``docker compose config`` -- catches
    interpolation/merge/profile errors a bare YAML parse cannot."""

    def test_base_compose_is_valid(self) -> None:
        result = subprocess.run(
            ["docker", "compose", "-f", "docker-compose.yml", "config", "--quiet"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr

    def test_dev_overlay_is_valid(self) -> None:
        result = subprocess.run(
            [
                "docker", "compose",
                "-f", "docker-compose.yml", "-f", "docker-compose.dev.yml",
                "config", "--quiet",
            ],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr

    def test_prod_overlay_is_valid(self) -> None:
        result = subprocess.run(
            [
                "docker", "compose",
                "-f", "docker-compose.yml", "-f", "docker-compose.prod.yml",
                "--profile", "postgres", "--profile", "redis",
                "config", "--quiet",
            ],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
