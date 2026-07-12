"""Phase 61 (ADR-0079): security headers set by the nginx configs.

Plain text-content assertions (no nginx binary required), matching
``test_docker_compose.py``'s existing "structural validation, no daemon
required" precedent -- the real config-loads-cleanly proof is the `docker`
CI job's ``docker build ./deploy/nginx``, already covered elsewhere.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BASELINE_HEADERS = (
    'add_header X-Content-Type-Options "nosniff" always;',
    'add_header X-Frame-Options "DENY" always;',
    'add_header Referrer-Policy "strict-origin-when-cross-origin" always;',
)


def _read(relative_path: str) -> str:
    return (_REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_edge_conf_sets_baseline_and_csp_headers() -> None:
    conf = _read("deploy/nginx/edge.conf")
    for header in _BASELINE_HEADERS:
        assert header in conf
    assert "Content-Security-Policy" in conf
    assert "default-src 'self'" in conf


def test_frontend_conf_sets_baseline_and_csp_headers() -> None:
    conf = _read("deploy/nginx/frontend.conf")
    for header in _BASELINE_HEADERS:
        assert header in conf
    assert "Content-Security-Policy" in conf
    assert "default-src 'self'" in conf


def test_csp_never_allows_unsafe_inline_or_eval_scripts() -> None:
    """script-src stays strict -- only style-src's documented exception."""
    for relative_path in ("deploy/nginx/edge.conf", "deploy/nginx/frontend.conf"):
        csp_line = next(
            line
            for line in _read(relative_path).splitlines()
            if "Content-Security-Policy" in line
        )
        assert "script-src 'self';" in csp_line
        assert "script-src 'self' 'unsafe-inline'" not in csp_line
        assert "unsafe-eval" not in csp_line


def test_csp_and_baseline_headers_stay_identical_between_edge_and_frontend() -> None:
    """Defense-in-depth duplication (Phase 61) must not silently drift."""
    edge = _read("deploy/nginx/edge.conf")
    frontend = _read("deploy/nginx/frontend.conf")
    for header in (*_BASELINE_HEADERS, "Content-Security-Policy"):
        edge_line = next(line for line in edge.splitlines() if header in line)
        frontend_line = next(line for line in frontend.splitlines() if header in line)
        assert edge_line.strip() == frontend_line.strip()
