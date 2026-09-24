# Transposed from bpmn-io/bpmn-auto-layout@1.3.0 lib/utils/layoutUtil.js (MIT).
"""Manhattan connection routing and cell geometry from ``lib/utils/layoutUtil.js``.

Number rules: the two ``math_round`` calls in ``get_bounds`` are the ONLY
rounding in 1.3.0; every other ``/2``-style intermediate stays a full double and
flows as ``int``-iff-computed-from-ints / ``float`` into the writer (serialization
only via ``BpmnModdle.to_xml``). ``get_max_expanded_between`` replicates the
``undefined``-poisoning reduce with the ``UNDEFINED`` sentinel.
"""

from __future__ import annotations

from typing import Any, TypeAlias, cast

from bpmn_io._js import UNDEFINED, UndefinedType, is_truthy, math_round
from bpmn_io.auto_layout.di_util import DEFAULT_TASK_HEIGHT, get_default_size
from bpmn_io.auto_layout.errors import LayoutError

__all__ = [
    "DEFAULT_CELL_HEIGHT",
    "DEFAULT_CELL_WIDTH",
    "connect_elements",
    "coordinates_to_position",
    "get_bounds",
    "get_docking_point",
    "get_mid",
]

#: A dynamic moddle element; the attribute shape varies by type.
Element: TypeAlias = Any

#: Default grid cell width (lives in ``layoutUtil.js``, not ``DiUtil.js``).
DEFAULT_CELL_WIDTH = 150
#: Default grid cell height (lives in ``layoutUtil.js``, not ``DiUtil.js``).
DEFAULT_CELL_HEIGHT = 140


def _math_sign(value: Element) -> int:
    """Return ``Math.sign(value)``: ``-1``, ``0`` or ``1`` (never ``NaN`` here)."""
    above = 1 if value > 0 else 0
    below = 1 if value < 0 else 0
    return above - below


def get_mid(bounds: Element) -> dict[str, Any]:
    """Return the center ``{x, y}`` of ``bounds``."""
    return {
        "x": bounds.get("x") + bounds.get("width") / 2,
        "y": bounds.get("y") + bounds.get("height") / 2,
    }


def get_docking_point(
    point: dict[str, Any],
    rectangle: Element,
    docking_direction: str = "r",
    target_orientation: str = "top-left",
) -> dict[str, Any]:
    """Return the docking point on ``rectangle`` for ``point`` (E3 on misuse)."""
    if docking_direction == "h":
        docking_direction = "l" if "left" in target_orientation else "r"

    if docking_direction == "v":
        docking_direction = "t" if "top" in target_orientation else "b"

    if docking_direction == "t":
        return {"original": point, "x": point["x"], "y": rectangle.get("y")}

    if docking_direction == "r":
        return {
            "original": point,
            "x": rectangle.get("x") + rectangle.get("width"),
            "y": point["y"],
        }

    if docking_direction == "b":
        return {
            "original": point,
            "x": point["x"],
            "y": rectangle.get("y") + rectangle.get("height"),
        }

    if docking_direction == "l":
        return {"original": point, "x": rectangle.get("x"), "y": point["y"]}

    msg = "unexpected dockingDirection: <" + docking_direction + ">"
    raise LayoutError(msg)


def connect_elements(  # noqa: C901, PLR0911, PLR0912, PLR0915 - one upstream fn, kept whole
    source: Element, target: Element, layout_grid: Element
) -> list[dict[str, Any]]:
    """Route ``source`` to ``target`` (modified Manhattan layout, returns waypoints)."""
    source_di = source.di
    target_di = target.di

    source_bounds = source_di.get("bounds")
    target_bounds = target_di.get("bounds")

    source_mid = get_mid(source_bounds)
    target_mid = get_mid(target_bounds)

    source_position = source.grid_position
    target_position = target.grid_position

    d_x = target_position["col"] - source_position["col"]
    d_y = target_position["row"] - source_position["row"]

    docking_source = ("bottom" if d_y > 0 else "top") + "-" + ("right" if d_x > 0 else "left")
    docking_target = ("top" if d_y > 0 else "bottom") + "-" + ("left" if d_x > 0 else "right")

    attached_source = source.get("attachedToRef")
    base_source_grid: Element = getattr(source, "grid", None) or (
        getattr(attached_source, "grid", None) if is_truthy(attached_source) else None
    )
    base_target_grid: Element = getattr(target, "grid", None)

    # Source === Target ==> Build loop
    if d_x == 0 and d_y == 0:
        position = coordinates_to_position(source_position["row"], source_position["col"])
        x = position["x"]
        y = position["y"]
        if is_truthy(base_source_grid):
            bend_x: Any = x + (base_source_grid.get_grid_dimensions()[1] + 1) * DEFAULT_CELL_WIDTH
        else:
            bend_x = x + DEFAULT_CELL_WIDTH
        return [
            get_docking_point(source_mid, source_bounds, "r", docking_source),
            {"x": bend_x, "y": source_mid["y"]},
            {"x": bend_x, "y": y},
            {"x": target_mid["x"], "y": y},
            get_docking_point(target_mid, target_bounds, "t", docking_target),
        ]

    # negative dX indicates connection from future to past
    if d_x < 0:
        y = coordinates_to_position(source_position["row"], source_position["col"])["y"]

        offset_y = DEFAULT_CELL_HEIGHT / 2

        if source_mid["y"] >= target_mid["y"]:
            # edge goes below
            max_expanded = get_max_expanded_between(source, target, layout_grid)

            if is_truthy(max_expanded):
                expanded: int = cast("int", max_expanded)
                if not is_truthy(base_source_grid):
                    bend_y: Any = y + DEFAULT_CELL_HEIGHT + expanded * DEFAULT_CELL_HEIGHT
                else:
                    bend_y = (
                        y + (base_source_grid.get_grid_dimensions()[0] + 1) * DEFAULT_CELL_HEIGHT
                    )
                return [
                    get_docking_point(source_mid, source_bounds, "b"),
                    {"x": source_mid["x"], "y": bend_y},
                    {"x": target_mid["x"], "y": bend_y},
                    get_docking_point(target_mid, target_bounds, "b"),
                ]

            if not is_truthy(base_source_grid):
                plain_y: Any = y + DEFAULT_CELL_HEIGHT
            else:
                plain_y = y + (base_source_grid.get_grid_dimensions()[0] + 1) * DEFAULT_CELL_HEIGHT
            return [
                get_docking_point(source_mid, source_bounds, "b"),
                {"x": source_mid["x"], "y": plain_y},
                {"x": target_mid["x"], "y": plain_y},
                get_docking_point(target_mid, target_bounds, "b"),
            ]

        # edge goes above
        bend_above_y = source_mid["y"] - offset_y

        return [
            get_docking_point(source_mid, source_bounds, "t"),
            {"x": source_mid["x"], "y": bend_above_y},
            {"x": target_mid["x"], "y": bend_above_y},
            get_docking_point(target_mid, target_bounds, "t"),
        ]

    # connect horizontally
    if d_y == 0:
        if _is_direct_path_blocked(source, target, layout_grid):
            y = coordinates_to_position(source_position["row"], source_position["col"])["y"]

            # Route on bottom
            if not is_truthy(base_source_grid):
                route_y: Any = y + DEFAULT_CELL_HEIGHT
            else:
                route_y = y + (base_source_grid.get_grid_dimensions()[0] + 1) * DEFAULT_CELL_HEIGHT
            return [
                get_docking_point(source_mid, source_bounds, "b"),
                {"x": source_mid["x"], "y": route_y},
                {"x": target_mid["x"], "y": route_y},
                get_docking_point(target_mid, target_bounds, "b"),
            ]

        # if space is clear, connect directly
        first_point = get_docking_point(source_mid, source_bounds, "h", docking_source)
        last_point = get_docking_point(target_mid, target_bounds, "h", docking_target)
        if is_truthy(base_source_grid):
            first_point["y"] = source_bounds.get("y") + DEFAULT_TASK_HEIGHT / 2

        if is_truthy(base_target_grid):
            last_point["y"] = target_bounds.get("y") + DEFAULT_TASK_HEIGHT / 2

        return [first_point, last_point]

    # connect vertically
    if d_x == 0:
        if _is_direct_path_blocked(source, target, layout_grid):
            # Route parallel
            y_offset = -_math_sign(d_y) * DEFAULT_CELL_HEIGHT / 2
            return [
                get_docking_point(source_mid, source_bounds, "r"),
                {"x": source_mid["x"] + DEFAULT_CELL_WIDTH / 2, "y": source_mid["y"]},
                {
                    "x": target_mid["x"] + DEFAULT_CELL_WIDTH / 2,
                    "y": target_mid["y"] + y_offset,
                },
                {"x": target_mid["x"], "y": target_mid["y"] + y_offset},
                get_docking_point(
                    target_mid, target_bounds, "b" if _math_sign(y_offset) > 0 else "t"
                ),
            ]

        # if space is clear, connect directly
        return [
            get_docking_point(source_mid, source_bounds, "v", docking_source),
            get_docking_point(target_mid, target_bounds, "v", docking_target),
        ]

    direct_manhattan = _direct_manhattan_connect(source, target, layout_grid)

    if isinstance(direct_manhattan, tuple):
        start_point = get_docking_point(
            source_mid, source_bounds, direct_manhattan[0], docking_source
        )
        end_point = get_docking_point(
            target_mid, target_bounds, direct_manhattan[1], docking_target
        )

        if direct_manhattan[0] == "h":
            mid_point = {"x": end_point["x"], "y": start_point["y"]}
        else:
            mid_point = {"x": start_point["x"], "y": end_point["y"]}

        return [start_point, mid_point, end_point]

    y_fallback_offset = -_math_sign(d_y) * DEFAULT_CELL_HEIGHT / 2

    return [
        get_docking_point(source_mid, source_bounds, "r", docking_source),
        {"x": source_mid["x"] + DEFAULT_CELL_WIDTH / 2, "y": source_mid["y"]},
        {"x": source_mid["x"] + DEFAULT_CELL_WIDTH / 2, "y": target_mid["y"] + y_fallback_offset},
        {"x": target_mid["x"] - DEFAULT_CELL_WIDTH / 2, "y": target_mid["y"] + y_fallback_offset},
        {"x": target_mid["x"] - DEFAULT_CELL_WIDTH / 2, "y": target_mid["y"]},
        get_docking_point(target_mid, target_bounds, "l", docking_target),
    ]


def coordinates_to_position(row: int, col: int) -> dict[str, Any]:
    """Return the ``{width, height, x, y}`` cell origin for ``(row, col)``."""
    return {
        "width": DEFAULT_CELL_WIDTH,
        "height": DEFAULT_CELL_HEIGHT,
        "x": col * DEFAULT_CELL_WIDTH,
        "y": row * DEFAULT_CELL_HEIGHT,
    }


def get_bounds(
    element: Element,
    row: int,
    col: int,
    shift: dict[str, Any],
    attached_to: Element | None = None,
) -> dict[str, Any]:
    """Return centered ``{width, height, x, y}`` bounds for ``element`` in its cell."""
    default_size = get_default_size(element)
    width = default_size["width"]
    height = default_size["height"]
    x = shift["x"]
    y = shift["y"]

    # Center in cell
    if is_truthy(attached_to):
        host: Element = attached_to
        host_bounds = host.di.get("bounds")

        return {
            "width": width,
            "height": height,
            "x": math_round(host_bounds.get("x") + host_bounds.get("width") / 2 - width / 2),
            "y": math_round(host_bounds.get("y") + host_bounds.get("height") - height / 2),
        }

    if is_truthy(getattr(element, "isExpanded", None)):
        element_grid = element.grid
        grid_dimensions = element_grid.get_grid_dimensions()
        # Expanded dimensions go into the returned shape only; centering below
        # keeps the unexpanded locals, exactly as upstream.
        return {
            "width": grid_dimensions[1] * DEFAULT_CELL_WIDTH + width,
            "height": grid_dimensions[0] * DEFAULT_CELL_HEIGHT + height,
            "x": (col * DEFAULT_CELL_WIDTH) + (DEFAULT_CELL_WIDTH - width) / 2 + x,
            "y": row * DEFAULT_CELL_HEIGHT + (DEFAULT_CELL_HEIGHT - height) / 2 + y,
        }

    return {
        "width": width,
        "height": height,
        "x": (col * DEFAULT_CELL_WIDTH) + (DEFAULT_CELL_WIDTH - width) / 2 + x,
        "y": row * DEFAULT_CELL_HEIGHT + (DEFAULT_CELL_HEIGHT - height) / 2 + y,
    }


def get_max_expanded_between(
    source: Element, target: Element, layout_grid: Element
) -> int | UndefinedType:
    """Return the tallest expanded grid between the hosts (``UNDEFINED``-poisoning)."""
    host_source = source.get("attachedToRef")
    host_source = host_source if is_truthy(host_source) else source
    host_target = target.get("attachedToRef")
    host_target = host_target if is_truthy(host_target) else target

    source_row, source_col = layout_grid.find(host_source)
    _target_row, target_col = layout_grid.find(host_target)

    first_col = min(target_col, source_col)
    last_col = max(source_col, target_col)

    elements_in_range = [
        element
        for element in layout_grid.get_all_elements()
        if element.grid_position["row"] == source_row
        and element.grid_position["col"] > first_col
        and element.grid_position["col"] < last_col
    ]

    # Literal reduce: the callback returns ``undefined`` (poisoning ``acc``) whenever
    # the current element does not strictly improve on the accumulator.
    acc: int | UndefinedType = 0
    for current in elements_in_range:
        current_grid = getattr(current, "grid", None)
        if current_grid is None:
            acc = UNDEFINED
            continue
        current_rows: int | UndefinedType = current_grid.get_grid_dimensions()[0]
        if isinstance(current_rows, int) and isinstance(acc, int) and current_rows > acc:
            acc = current_rows
        else:
            acc = UNDEFINED
    return acc


def _is_direct_path_blocked(source: Element, target: Element, layout_grid: Element) -> bool:
    """Return whether the straight L-path between the grid positions is occupied."""
    source_position = source.grid_position
    target_position = target.grid_position

    source_row = source_position["row"]
    source_col = source_position["col"]
    target_row = target_position["row"]
    target_col = target_position["col"]

    d_x = target_col - source_col
    d_y = target_row - source_row

    total_elements = 0

    if d_x:
        total_elements += len(
            layout_grid.get_elements_in_range(
                {"row": source_row, "col": source_col},
                {"row": source_row, "col": target_col},
            )
        )

    if d_y:
        total_elements += len(
            layout_grid.get_elements_in_range(
                {"row": source_row, "col": target_col},
                {"row": target_row, "col": target_col},
            )
        )

    return total_elements > 2


def _direct_manhattan_connect(
    source: Element, target: Element, layout_grid: Element
) -> tuple[str, str] | bool | None:
    """Return the viable ``(dir_a, dir_b)`` bend, ``False`` or ``None``."""
    source_position = source.grid_position
    target_position = target.grid_position

    source_row = source_position["row"]
    source_col = source_position["col"]
    target_row = target_position["row"]
    target_col = target_position["col"]

    d_x = target_col - source_col
    d_y = target_row - source_row

    # Only directly connect left-to-right flow
    if not (d_x > 0 and d_y != 0):
        return None

    # If below, go down then horizontal
    if d_y > 0:
        total_elements = 0
        bend_point = {"row": target_row, "col": source_col}
        total_elements += len(
            layout_grid.get_elements_in_range({"row": source_row, "col": source_col}, bend_point)
        )
        total_elements += len(
            layout_grid.get_elements_in_range(bend_point, {"row": target_row, "col": target_col})
        )

        return False if total_elements > 2 else ("v", "h")

    # If above, go horizontal than vertical
    total_elements = 0
    bend_point = {"row": source_row, "col": target_col}

    total_elements += len(
        layout_grid.get_elements_in_range({"row": source_row, "col": source_col}, bend_point)
    )
    total_elements += len(
        layout_grid.get_elements_in_range(bend_point, {"row": target_row, "col": target_col})
    )

    return False if total_elements > 2 else ("h", "v")
