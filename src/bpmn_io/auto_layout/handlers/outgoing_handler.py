# Transposed from bpmn-io/bpmn-auto-layout@1.3.0 lib/handler/outgoingHandler.js (MIT).
"""Outgoing traversal and connection DI from ``lib/handler/outgoingHandler.js``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias

from bpmn_io._js import is_truthy

if TYPE_CHECKING:
    from bpmn_io._js import OrderedSet
from bpmn_io.auto_layout.di_util import is_
from bpmn_io.auto_layout.element_utils import find_element_in_tree
from bpmn_io.auto_layout.layout_util import connect_elements

__all__ = ["HANDLER", "add_to_grid", "create_connection_di"]

#: A dynamic moddle element; the attribute shape varies by type.
Element: TypeAlias = Any


def add_to_grid(options: dict[str, Any]) -> list[Element]:
    """Place outgoing targets (LIFO ``unshift`` + stable gateway-first repartition)."""
    element = options["element"]
    grid = options["grid"]
    visited = options["visited"]
    stack = options["stack"]

    next_elements: list[Element] = []

    # Handle outgoing paths
    outgoing = [edge.get("targetRef") for edge in (element.get("outgoing") or [])]
    outgoing = [target for target in outgoing if is_truthy(target)]

    previous_element = None

    if len(outgoing) > 1 and _is_next_element_tasks(outgoing):
        grid.adjust_grid_position(element)

    for index, next_element in enumerate(outgoing):
        if next_element in visited:
            continue

        # Prevents revisiting future incoming elements and ensures proper traversal
        # without early exit.
        if (
            (previous_element is not None or len(stack) > 0)
            and _is_future_incoming(next_element, visited)
            and not _check_for_loop(next_element, visited)
        ):
            continue

        if previous_element is None:
            grid.add_after(element, next_element)

        elif is_(element, "bpmn:ExclusiveGateway") and is_(next_element, "bpmn:ExclusiveGateway"):
            grid.add_after(previous_element, next_element)

        else:
            grid.add_below(outgoing[index - 1], next_element)

        # Is self-looping
        if next_element is not element:
            previous_element = next_element

        next_elements.insert(0, next_element)
        visited.add(next_element)

    # Sort elements by priority to ensure proper stack placement
    return _sort_by_type(next_elements, "bpmn:ExclusiveGateway")


def create_connection_di(options: dict[str, Any]) -> list[Element]:
    """Create one edge DI per outgoing flow of ``element``."""
    element = options["element"]
    layout_grid = options["layoutGrid"]
    di_factory = options["diFactory"]

    outgoing = element.get("outgoing") or []

    return [
        di_factory.create_di_edge(
            edge,
            connect_elements(element, edge.get("targetRef"), layout_grid),
            {"id": edge.get("id") + "_di"},
        )
        for edge in outgoing
    ]


def _sort_by_type(elements: list[Element], type_name: str) -> list[Element]:
    """Stably partition ``elements`` (matching ``type_name`` first)."""
    non_matching = [item for item in elements if not is_(item, type_name)]
    matching = [item for item in elements if is_(item, type_name)]

    return [*matching, *non_matching]


def _check_for_loop(element: Element, visited: OrderedSet[Element]) -> bool | None:
    """Return whether an unvisited incoming source reaches back into ``element``."""
    for incoming_element in element.get("incoming"):
        if incoming_element.get("sourceRef") not in visited:
            return find_element_in_tree(element, incoming_element.get("sourceRef"))
    return None


def _is_future_incoming(element: Element, visited: OrderedSet[Element]) -> bool:
    """Return whether ``element`` has an unvisited incoming source."""
    incoming = element.get("incoming")
    if len(incoming) > 1:
        for incoming_element in incoming:
            if incoming_element.get("sourceRef") not in visited:
                return True
    return False


def _is_next_element_tasks(elements: list[Element]) -> bool:
    """Return whether every element is a ``bpmn:Task``."""
    return all(is_(element, "bpmn:Task") for element in elements)


#: Handler registry entry.
HANDLER: dict[str, Any] = {
    "add_to_grid": add_to_grid,
    "create_connection_di": create_connection_di,
}
