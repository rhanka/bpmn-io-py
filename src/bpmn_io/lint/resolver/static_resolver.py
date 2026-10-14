# Transposed from bpmn-io/bpmnlint@de71146 lib/resolver/static-resolver.js (MIT).
"""Static cache resolver, transposed from ``lib/resolver/static-resolver.js``."""

from __future__ import annotations

from typing import Any

__all__ = ["StaticResolver"]


class StaticResolver:
    """Resolve rules and packages from a static cache (upstream ``StaticResolver``)."""

    def __init__(self, cache: dict[str, Any]) -> None:
        """Create the resolver over ``cache`` (keys ``rule:<pkg>/<name>`` etc.)."""
        self.cache = cache

    def resolve_rule(self, pkg: str, rule_name: str) -> object:
        """Resolve the rule factory ``rule_name`` from ``pkg``."""
        return self.resolve("rule", pkg, rule_name)

    def resolve_config(self, pkg: str, config_name: str) -> object:
        """Resolve the config ``config_name`` from ``pkg``."""
        return self.resolve("config", pkg, config_name)

    def resolve(self, type: str, pkg: str, name: str) -> object:  # noqa: A002 - upstream name
        """Resolve ``type`` ``pkg``/``name`` from the cache, raising when unknown."""
        resolved_id = f"{pkg}/{name}"

        resolved = self.cache.get(f"{type}:{resolved_id}")

        if not resolved:
            msg = f"unknown {type} <{resolved_id}>"
            raise ValueError(msg)

        return resolved
