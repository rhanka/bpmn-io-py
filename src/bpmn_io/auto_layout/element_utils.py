# Transposed from bpmn-io/bpmn-auto-layout@1.3.0 lib/utils/elementUtils.js (MIT).
"""Element predicates and tree search transposed from ``lib/utils/elementUtils.js``."""

from __future__ import annotations

from typing import Any, TypeAlias

from bpmn_io._js import is_truthy

__all__ = ["find_element_in_tree", "is_boundary_event", "is_connection"]

#: A dynamic moddle element; the attribute shape varies by type.
Element: TypeAlias = Any


def is_connection(element: Element) -> bool:
    """Return whether ``element`` is a connection (has a ``sourceRef``)."""
    return is_truthy(element.get("sourceRef"))


def is_boundary_event(element: Element) -> bool:
    """Return whether ``element`` is a boundary event (has an ``attachedToRef``)."""
    return is_truthy(element.get("attachedToRef"))


def find_element_in_tree(
    current: Element, target: Element, visited: set[Any] | None = None
) -> bool:
    """Return whether ``target`` is reachable from ``current`` via ``outgoing`` refs."""
    if current is target:
        return True

    seen = visited if visited is not None else set()
    if current in seen:
        return False

    seen.add(current)

    outgoing: Any = current.get("outgoing")
    if not is_truthy(outgoing) or len(outgoing) == 0:
        return False

    return any(find_element_in_tree(edge.get("targetRef"), target, seen) for edge in outgoing)
