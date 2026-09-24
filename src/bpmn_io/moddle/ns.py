# Transposed from bpmn-io/moddle@3124e6a lib/ns.js (MIT).
"""Namespace name parsing transposed from moddle ``lib/ns.js``."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Namespace", "parse_name"]


@dataclass(frozen=True)
class Namespace:
    """A parsed ``prefix:localName`` name."""

    name: str
    prefix: str | None
    local_name: str


def parse_name(name: str, default_prefix: str | None = None) -> Namespace:
    """Parse a ``(prefix:)localName`` name, falling back to ``default_prefix``."""
    parts = name.split(":")

    # no prefix (i.e. only local name)
    if len(parts) == 1:
        local_name = name
        prefix = default_prefix

    # prefix + local name
    elif len(parts) == 2:
        local_name = parts[1]
        prefix = parts[0]

    else:
        msg = "expected <prefix:localName> or <localName>, got " + name
        raise ValueError(msg)

    full_name = (prefix + ":" if prefix else "") + local_name

    return Namespace(name=full_name, prefix=prefix, local_name=local_name)
