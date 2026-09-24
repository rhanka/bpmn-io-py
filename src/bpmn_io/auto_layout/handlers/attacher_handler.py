# Transposed from bpmn-io/bpmn-auto-layout@1.3.0 lib/handler/attachersHandler.js (MIT).
"""Boundary-event handling transposed from ``lib/handler/attachersHandler.js``.

The ``(attacher.outgoing || []).reverse()`` call mutates the LIVE outgoing list
in place, exactly as upstream; it is never copied first.
"""

from __future__ import annotations

from typing import Any, TypeAlias

from bpmn_io._js import is_truthy
from bpmn_io.auto_layout.layout_util import (
    DEFAULT_CELL_HEIGHT,
    DEFAULT_CELL_WIDTH,
    connect_elements,
    get_bounds,
    get_docking_point,
    get_mid,
)

__all__ = ["HANDLER", "add_to_grid", "create_connection_di", "create_element_di"]

#: A dynamic moddle element; the attribute shape varies by type.
Element: TypeAlias = Any


def add_to_grid(options: dict[str, Any]) -> list[Element]:
    """Place boundary-event outgoing targets below-right of their host."""
    element = options["element"]
    grid = options["grid"]
    visited = options["visited"]

    next_elements: list[Element] = []

    attached_outgoing: list[Element] = []
    for attacher in getattr(element, "attachers", None) or []:
        outgoing = getattr(attacher, "outgoing", None) or []
        outgoing.reverse()
        attached_outgoing.extend(outgoing)
    targets = [edge.get("targetRef") for edge in attached_outgoing]

    # handle boundary events
    for next_element in targets:
        if next_element in visited:
            continue

        # Add below and to the right of the element
        _insert_into_grid(next_element, element, grid)
        next_elements.append(next_element)
        visited.add(next_element)

    return next_elements


def create_element_di(options: dict[str, Any]) -> list[Element]:
    """Create the host shape DI plus one DI per boundary attacher along its edge."""
    element = options["element"]
    row = options["row"]
    col = options["col"]
    di_factory = options["diFactory"]
    shift = options["shift"]

    host_bounds = get_bounds(element, row, col, shift)

    attachers = getattr(element, "attachers", None) or []

    dis = []
    for index, attacher in enumerate(attachers):
        attacher.grid_position = {"row": row, "col": col}
        bounds = get_bounds(attacher, row, col, shift, element)

        # distribute along lower edge
        bounds["x"] = (
            host_bounds["x"]
            + (index + 1) * (host_bounds["width"] / (len(attachers) + 1))
            - bounds["width"] / 2
        )

        attacher_di = di_factory.create_di_shape(
            attacher, bounds, {"id": attacher.get("id") + "_di"}
        )
        attacher.di = attacher_di
        attacher.grid_position = {"row": row, "col": col}

        dis.append(attacher_di)

    return dis


def create_connection_di(options: dict[str, Any]) -> list[Element]:
    """Create one edge DI per boundary-attacher outgoing flow (bottom-exiting)."""
    element = options["element"]
    row = options["row"]
    col = options["col"]
    layout_grid = options["layoutGrid"]
    di_factory = options["diFactory"]

    attachers = getattr(element, "attachers", None) or []

    dis = []
    for attacher in attachers:
        for edge in attacher.get("outgoing") or []:
            target = edge.get("targetRef")
            waypoints = connect_elements(attacher, target, layout_grid)

            # Correct waypoints if they don't automatically attach to the bottom
            ensure_exit_bottom(attacher, waypoints, (row, col))

            dis.append(di_factory.create_di_edge(edge, waypoints, {"id": edge.get("id") + "_di"}))
    return dis


def _insert_into_grid(new_element: Element, host: Element, grid: Element) -> None:
    """Insert ``new_element`` one row below and one column right of ``host``."""
    row, col = grid.find(host)

    # Grid is occupied
    if is_truthy(grid.get(row + 1, col)) or is_truthy(grid.get(row + 1, col + 1)):
        grid.create_row(row)

    grid.add(new_element, [row + 1, col + 1])


def ensure_exit_bottom(
    source: Element, waypoints: list[dict[str, Any]], position: tuple[int, int]
) -> None:
    """Splice bottom-exiting waypoints in place when the route starts elsewhere."""
    row, col = position

    source_di = source.di
    source_bounds = source_di.get("bounds")
    source_mid = get_mid(source_bounds)

    docking_point = get_docking_point(source_mid, source_bounds, "b")
    if waypoints[0]["x"] == docking_point["x"] and waypoints[0]["y"] == docking_point["y"]:
        return

    attached_source = source.get("attachedToRef")
    base_source_grid: Element = getattr(source, "grid", None) or (
        getattr(attached_source, "grid", None) if is_truthy(attached_source) else None
    )

    if len(waypoints) == 2:
        if not is_truthy(base_source_grid):
            new_start = [
                docking_point,
                {"x": docking_point["x"], "y": (row + 1) * DEFAULT_CELL_HEIGHT},
                {
                    "x": (col + 1) * DEFAULT_CELL_WIDTH,
                    "y": (row + 1) * DEFAULT_CELL_HEIGHT,
                },
                {
                    "x": (col + 1) * DEFAULT_CELL_WIDTH,
                    "y": (row + 0.5) * DEFAULT_CELL_HEIGHT,
                },
            ]
        else:
            grid_dimensions = base_source_grid.get_grid_dimensions()
            new_start = [
                docking_point,
                {
                    "x": docking_point["x"],
                    "y": (row + grid_dimensions[0] + 1) * DEFAULT_CELL_HEIGHT,
                },
                {
                    "x": (col + grid_dimensions[1] + 1) * DEFAULT_CELL_WIDTH,
                    "y": (row + grid_dimensions[0] + 1) * DEFAULT_CELL_HEIGHT,
                },
                {
                    "x": (col + grid_dimensions[1] + 1) * DEFAULT_CELL_WIDTH,
                    "y": row * DEFAULT_CELL_HEIGHT + DEFAULT_CELL_HEIGHT / 2,
                },
            ]

        waypoints[0:1] = new_start
        return

    # add waypoints to exit bottom and connect to existing path
    if not is_truthy(base_source_grid):
        new_start = [
            docking_point,
            {"x": docking_point["x"], "y": (row + 1) * DEFAULT_CELL_HEIGHT},
            {"x": waypoints[1]["x"], "y": (row + 1) * DEFAULT_CELL_HEIGHT},
        ]
    else:
        grid_dimensions = base_source_grid.get_grid_dimensions()
        new_start = [
            docking_point,
            {
                "x": docking_point["x"],
                "y": (row + grid_dimensions[0] + 1) * DEFAULT_CELL_HEIGHT,
            },
            {
                "x": waypoints[1]["x"],
                "y": (row + grid_dimensions[0] + 1) * DEFAULT_CELL_HEIGHT,
            },
        ]

    waypoints[0:1] = new_start


#: Handler registry entry.
HANDLER: dict[str, Any] = {
    "add_to_grid": add_to_grid,
    "create_connection_di": create_connection_di,
    "create_element_di": create_element_di,
}
