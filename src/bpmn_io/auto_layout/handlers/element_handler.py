# Transposed from bpmn-io/bpmn-auto-layout@1.3.0 lib/handler/elementHandler.js (MIT).
"""Element DI creation transposed from ``lib/handler/elementHandler.js``."""

from __future__ import annotations

from typing import Any, TypeAlias

from bpmn_io.auto_layout.di_util import is_
from bpmn_io.auto_layout.layout_util import get_bounds

__all__ = ["HANDLER", "create_element_di"]

#: A dynamic moddle element; the attribute shape varies by type.
Element: TypeAlias = Any


def create_element_di(options: dict[str, Any]) -> Element:
    """Create the shape DI for one grid element (exclusive gateways get markers)."""
    element = options["element"]
    row = options["row"]
    col = options["col"]
    di_factory = options["diFactory"]
    shift = options["shift"]

    bounds = get_bounds(element, row, col, shift)

    shape_options: dict[str, Any] = {"id": element.get("id") + "_di"}

    if is_(element, "bpmn:ExclusiveGateway"):
        shape_options["isMarkerVisible"] = True

    if getattr(element, "isExpanded", None):
        shape_options["isExpanded"] = True

    shape_di = di_factory.create_di_shape(element, bounds, shape_options)
    element.di = shape_di
    element.grid_position = {"row": row, "col": col}

    return shape_di


#: Handler registry entry (``createElementDi`` only).
HANDLER: dict[str, Any] = {"create_element_di": create_element_di}
