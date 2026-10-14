"""Rule/config resolvers for the lint port (upstream ``lib/resolver/``)."""

from __future__ import annotations

from bpmn_io.lint.resolver.node_resolver import NodeResolver
from bpmn_io.lint.resolver.static_resolver import StaticResolver

__all__ = ["NodeResolver", "StaticResolver"]
