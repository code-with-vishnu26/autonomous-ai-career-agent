"""Tests for career_agent.core.registry."""

from __future__ import annotations

import pytest

from career_agent.core.interfaces import (
    NotificationSink,
    SearchProvider,
    SearchQuery,
)
from career_agent.core.registry import (
    DuplicatePluginError,
    PluginNotFoundError,
    PluginRegistry,
    discover,
    register,
)


class _ProviderA:
    capabilities = None

    async def health(self):  # pragma: no cover - not exercised here
        ...

    async def search(self, query):  # pragma: no cover - not exercised here
        ...


class _SinkA:
    async def notify(self, event):  # pragma: no cover - not exercised here
        ...


def test_register_and_get_round_trips() -> None:
    registry = PluginRegistry()
    plugin = _ProviderA()
    registry.register(SearchProvider, "a", plugin)
    assert registry.get(SearchProvider, "a") is plugin


def test_duplicate_key_raises() -> None:
    registry = PluginRegistry()
    registry.register(SearchProvider, "a", _ProviderA())
    with pytest.raises(DuplicatePluginError):
        registry.register(SearchProvider, "a", _ProviderA())


def test_missing_key_raises() -> None:
    registry = PluginRegistry()
    with pytest.raises(PluginNotFoundError):
        registry.get(SearchProvider, "nope")


def test_same_name_across_extension_points_does_not_collide() -> None:
    """A SearchProvider "x" and a NotificationSink "x" must coexist -- keying
    is by (extension point, name), not name alone."""
    registry = PluginRegistry()
    provider = _ProviderA()
    sink = _SinkA()
    registry.register(SearchProvider, "x", provider)
    registry.register(NotificationSink, "x", sink)
    assert registry.get(SearchProvider, "x") is provider
    assert registry.get(NotificationSink, "x") is sink


def test_all_returns_only_matching_extension_point() -> None:
    registry = PluginRegistry()
    p1, p2 = _ProviderA(), _ProviderA()
    registry.register(SearchProvider, "a", p1)
    registry.register(SearchProvider, "b", p2)
    registry.register(NotificationSink, "a", _SinkA())
    assert set(registry.all(SearchProvider)) == {p1, p2}
    assert registry.names(SearchProvider) == ["a", "b"]
    assert set(registry.extension_points()) == {SearchProvider, NotificationSink}


def test_register_decorator_records_marker_without_instantiating() -> None:
    """The decorator only records metadata; it never builds an instance or
    touches a registry on its own."""
    instantiated = []

    @register(SearchProvider, "decorated")
    class _Decorated:
        def __init__(self) -> None:
            instantiated.append(True)

    assert _Decorated.__plugin_name__ == "decorated"
    assert _Decorated.__plugin_extension_point__ is SearchProvider
    assert instantiated == []  # decoration did not instantiate


def test_discover_registers_the_in_tree_example_plugin() -> None:
    """discover() imports a package and registers its decorated plugins into
    the *given* registry -- proving the register-and-discover flow end to end."""
    from career_agent.plugins import examples

    registry = PluginRegistry()
    registered = discover(examples, registry)

    assert "echo" in registered
    provider = registry.get(SearchProvider, "echo")
    assert isinstance(provider, SearchProvider)


async def test_discovered_example_plugin_actually_works() -> None:
    from career_agent.plugins import examples

    registry = PluginRegistry()
    discover(examples, registry)
    provider = registry.get(SearchProvider, "echo")

    results = await provider.search(SearchQuery(text="python jobs"))
    assert results[0].snippet == "python jobs"


def test_discover_targets_an_explicit_registry_no_global_side_effect() -> None:
    """Two separate discover() calls populate two separate registries; there
    is no shared global the second call would clash with."""
    from career_agent.plugins import examples

    reg1, reg2 = PluginRegistry(), PluginRegistry()
    discover(examples, reg1)
    discover(examples, reg2)  # would raise DuplicatePluginError if global
    assert reg1.get(SearchProvider, "echo") is not reg2.get(SearchProvider, "echo")
