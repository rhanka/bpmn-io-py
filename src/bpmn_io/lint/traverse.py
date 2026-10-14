# Transposed from bpmn-io/bpmnlint@de71146 lib/traverse.js (MIT).
"""Depth-first traversal of a moddle tree, transposed from ``lib/traverse.js``.

Upstream recurses; this port iterates with an explicit stack (same
enter/leave order, same sub-tree skipping when ``enter`` returns ``False``),
so deeply nested diagrams cannot exhaust the Python call stack.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from bpmn_io.moddle.base import ModdleElement

__all__ = ["traverse"]

#: Primitive property types whose values are never traversed (upstream ``isSimpleType``).
_SIMPLE_TYPES = frozenset({"String", "Boolean", "Integer", "Real"})


def traverse(
    element: ModdleElement,
    options: dict[str, Callable[[ModdleElement], object] | None] | None = None,
    *,
    enter: Callable[[ModdleElement], object] | None = None,
    leave: Callable[[ModdleElement], object] | None = None,
) -> None:
    """Traverse ``element`` depth-first, calling ``enter``/``leave`` from ``options``."""
    if options:
        enter = options.get("enter", enter)
        leave = options.get("leave", leave)

    stack: list[tuple[ModdleElement, bool]] = [(element, False)]
    while stack:
        node, expanded = stack.pop()
        if expanded:
            if leave is not None:
                leave(node)
            continue

        enter_result = enter(node) if enter is not None else None

        stack.append((node, True))

        if enter_result is False:
            continue

        descriptor = node.descriptor_
        if getattr(descriptor, "is_generic", False):
            continue

        stack.extend((child, False) for child in reversed(_children(node)))


def _children(node: ModdleElement) -> list[ModdleElement]:
    """Contained (non-attribute, non-reference, non-simple) children of ``node``."""
    children: list[ModdleElement] = []
    for prop in node.descriptor_.properties:
        if prop.is_attr or prop.is_reference or prop.type in _SIMPLE_TYPES:
            continue
        if prop.name not in vars(node):
            continue
        value = vars(node)[prop.name]
        if prop.is_many:
            children.extend(value)
        else:
            children.append(value)
    return children
