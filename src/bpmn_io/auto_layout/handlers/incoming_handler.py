# Transposed from bpmn-io/bpmn-auto-layout@1.3.0 lib/handler/incomingHandler.js (MIT).
"""Multiple-incoming grid adjustment from ``lib/handler/incomingHandler.js``."""

from __future__ import annotations

from typing import Any, TypeAlias

from bpmn_io._js import is_truthy

__all__ = ["HANDLER", "add_to_grid"]

#: A dynamic moddle element; the attribute shape varies by type.
Element: TypeAlias = Any


def add_to_grid(options: dict[str, Any]) -> list[Element]:
    """Adjust the grid for multiple incoming flows (always returns ``[]``)."""
    element = options["element"]
    grid = options["grid"]

    incoming = [edge.get("sourceRef") for edge in (element.get("incoming") or [])]
    incoming = [source for source in incoming if is_truthy(source)]

    # adjust the row if it is empty
    if len(incoming) > 1:
        grid.adjust_column_for_multiple_incoming(incoming, element)
        grid.adjust_row_for_multiple_incoming(incoming, element)
    return []


#: Handler registry entry (``add_to_grid`` only).
HANDLER: dict[str, Any] = {"add_to_grid": add_to_grid}
