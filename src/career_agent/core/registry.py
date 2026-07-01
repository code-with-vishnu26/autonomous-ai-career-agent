"""Plugin registry: how capabilities self-register without core rewrites (ADR-0004).

Plugins are keyed by ``(extension-point protocol, name)`` so that, for
example, a ``SearchProvider`` named ``"google"`` and a ``NotificationSink``
named ``"google"`` never collide. Registration uses the decorator +
explicit-discovery model (ADR-0004's "Option A"): a plugin class is decorated
with :func:`register`, and :func:`discover` imports a package's modules so
those decorators run, then registers every decorated class into a given
:class:`PluginRegistry`.

Discovery always targets an *explicit* registry, so importing a plugin module
never mutates global state as a side effect -- tests register into a fresh
registry rather than a shared singleton.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType
from typing import TypeVar

P = TypeVar("P")

_EXTENSION_POINT_ATTR = "__plugin_extension_point__"
_NAME_ATTR = "__plugin_name__"


class PluginError(Exception):
    """Base class for plugin-registry errors."""


class DuplicatePluginError(PluginError):
    """Raised when a second plugin is registered under an existing key."""


class PluginNotFoundError(PluginError):
    """Raised when a lookup finds no plugin for the requested key."""


class PluginRegistry:
    """A registry of plugins keyed by ``(extension-point protocol, name)``.

    The registry stores plugin *instances*. It is generic over the extension
    point at the call site (``register``/``get``/``all`` are typed on the
    protocol you pass), so lookups return correctly-typed objects without the
    registry needing to know any concrete plugin.
    """

    def __init__(self) -> None:
        """Create an empty registry."""
        self._plugins: dict[tuple[type, str], object] = {}

    def register(self, extension_point: type[P], name: str, plugin: P) -> None:
        """Register ``plugin`` under ``(extension_point, name)``.

        Raises :class:`DuplicatePluginError` if that exact key is already
        taken -- misconfiguration fails loudly at registration time, not
        silently at lookup.
        """
        key = (extension_point, name)
        if key in self._plugins:
            raise DuplicatePluginError(
                f"{extension_point.__name__} plugin {name!r} already registered"
            )
        self._plugins[key] = plugin

    def get(self, extension_point: type[P], name: str) -> P:
        """Return the single plugin registered under ``(extension_point, name)``.

        Raises :class:`PluginNotFoundError` if absent.
        """
        try:
            plugin = self._plugins[(extension_point, name)]
        except KeyError:
            raise PluginNotFoundError(
                f"no {extension_point.__name__} plugin named {name!r}"
            ) from None
        return plugin  # type: ignore[return-value]

    def all(self, extension_point: type[P]) -> list[P]:
        """Return every plugin registered for ``extension_point``.

        This is what the Planner iterates to rank providers by capability and
        health (ADR-0002).
        """
        return [
            plugin  # type: ignore[misc]
            for (ep, _name), plugin in self._plugins.items()
            if ep is extension_point
        ]

    def names(self, extension_point: type[P]) -> list[str]:
        """Return the names registered under ``extension_point``."""
        return [
            name for (ep, name) in self._plugins if ep is extension_point
        ]

    def extension_points(self) -> list[type]:
        """Return every extension point that has at least one plugin."""
        seen: dict[type, None] = {}
        for ep, _name in self._plugins:
            seen.setdefault(ep, None)
        return list(seen)


def register(extension_point: type[P], name: str):
    """Class decorator marking a plugin for registration under a key.

    Records the extension point and name on the class; the actual
    registration into a :class:`PluginRegistry` happens in :func:`discover`.
    The class is returned unchanged, so decorating never instantiates or
    mutates global state on its own.
    """

    def decorate(cls: type[P]) -> type[P]:
        setattr(cls, _EXTENSION_POINT_ATTR, extension_point)
        setattr(cls, _NAME_ATTR, name)
        return cls

    return decorate


def _iter_modules(package: ModuleType) -> list[ModuleType]:
    """Import and return every submodule of ``package`` (recursively)."""
    modules: list[ModuleType] = []
    for _finder, mod_name, _is_pkg in pkgutil.walk_packages(
        package.__path__, prefix=f"{package.__name__}."
    ):
        modules.append(importlib.import_module(mod_name))
    return modules


def discover(package: ModuleType, registry: PluginRegistry) -> list[str]:
    """Import ``package``'s modules and register every decorated plugin class.

    Each :func:`register`-decorated class found is instantiated (with no
    arguments) and registered into ``registry``. Returns the names of the
    plugins registered, for logging/assertion. Registration always targets
    the passed ``registry`` -- discovery has no hidden global side effect.

    Config-bearing plugins (API keys, rate limits) will register through a
    factory variant in a later phase; today's plugins are zero-arg
    constructible, which is all the Phase 3 machinery needs to prove out.
    """
    registered: list[str] = []
    for module in _iter_modules(package):
        for obj in vars(module).values():
            if not isinstance(obj, type):
                continue
            # only classes decorated in *this* module, not inherited markers
            if _NAME_ATTR not in obj.__dict__:
                continue
            extension_point = getattr(obj, _EXTENSION_POINT_ATTR)
            name = getattr(obj, _NAME_ATTR)
            registry.register(extension_point, name, obj())
            registered.append(name)
    return registered
