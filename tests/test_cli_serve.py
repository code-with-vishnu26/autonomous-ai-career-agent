"""Phase 54 (ADR-0072): ``career-agent serve`` argument wiring.

``run_serve_command`` itself blocks forever inside ``uvicorn.run`` -- not
something a unit test should call for real. These tests cover what's
actually reachable: argparse wiring the ``serve`` subcommand correctly
(via ``main``, monkeypatching the command function it dispatches to), and
the missing-``web``-extra guard path.
"""

from __future__ import annotations

import builtins

import pytest

import career_agent.cli as cli_module


def test_serve_subcommand_dispatches_with_default_host_and_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_serve(*, host: str, port: int) -> int:
        captured["host"] = host
        captured["port"] = port
        return 0

    monkeypatch.setattr(cli_module, "run_serve_command", _fake_serve)
    with pytest.raises(SystemExit) as exc_info:
        cli_module.main(["serve"])
    assert exc_info.value.code == 0
    assert captured == {"host": "127.0.0.1", "port": 8000}


def test_serve_subcommand_accepts_host_and_port_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_serve(*, host: str, port: int) -> int:
        captured["host"] = host
        captured["port"] = port
        return 0

    monkeypatch.setattr(cli_module, "run_serve_command", _fake_serve)
    with pytest.raises(SystemExit):
        cli_module.main(["serve", "--host", "0.0.0.0", "--port", "9001"])
    assert captured == {"host": "0.0.0.0", "port": 9001}


def test_serve_without_web_extra_returns_one_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def _blocked_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "uvicorn":
            raise ImportError("simulated missing 'web' extra")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)
    assert cli_module.run_serve_command(host="127.0.0.1", port=8000) == 1
