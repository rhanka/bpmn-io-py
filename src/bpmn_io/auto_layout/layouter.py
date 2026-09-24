# Transposed from bpmn-io/bpmn-auto-layout@1.3.0 lib/Layouter.js (MIT).
"""Process layout orchestration transposed from ``lib/Layouter.js`` (sync port).

``layout_process`` mirrors the ``async`` upstream method without ``asyncio``:
``BpmnModdle.from_xml`` is already sync, so the single ``await`` vanishes.
"""

from __future__ import annotations

from typing import Any, TypeAlias, cast

from bpmn_io._js import UNDEFINED, OrderedSet, UndefinedType, is_truthy
from bpmn_io._min_dash import is_function
from bpmn_io.auto_layout.di_factory import DiFactory
from bpmn_io.auto_layout.di_util import get_default_size, is_
from bpmn_io.auto_layout.element_utils import is_boundary_event, is_connection
from bpmn_io.auto_layout.grid import Grid
from bpmn_io.auto_layout.handlers import HANDLERS
from bpmn_io.auto_layout.layout_util import DEFAULT_CELL_HEIGHT, DEFAULT_CELL_WIDTH
from bpmn_io.bpmn_moddle import BpmnModdle

__all__ = [
    "Layouter",
    "bind_boundary_events_with_hosts",
    "expand_grid_horizontally",
    "expand_grid_vertically",
    "has_other_incoming",
]

#: A dynamic moddle element; the attribute shape varies by type.
Element: TypeAlias = Any


class Layouter:
    """Lay out BPMN processes (owns its ``BpmnModdle`` and ``DiFactory``)."""

    def __init__(self) -> None:
        """Create a layouter with a fresh moddle instance and handler list."""
        self.moddle = BpmnModdle()
        self.di_factory = DiFactory(self.moddle)
        self._handlers = HANDLERS
        self.diagram: Element = UNDEFINED
        self.layouted_processes: list[Element] = []

    def handle(self, operation: str, options: dict[str, Any]) -> list[Element]:
        """Run ``operation`` on every handler exposing it (upstream import order)."""
        results = []
        for handler in self._handlers:
            operation_fn = handler.get(operation)
            if operation_fn is not None and is_function(operation_fn):
                results.append(operation_fn(options))
        return results

    def layout_process(self, xml: str) -> str:
        """Lay out the first root process of ``xml`` and return the DI XML."""
        moddle_obj = self.moddle.from_xml(xml)
        root_element = moddle_obj.root_element

        self.diagram = root_element

        first_root_process = self.get_process()

        if first_root_process is not None:
            self.set_expanded_property_to_moddle_elements(moddle_obj)

            self.set_executed_processes(first_root_process)

            self.create_grids_for_processes()

            self.clean_di()

            self.create_root_di(first_root_process)

            self.draw_processes()

        return self.moddle.to_xml(self.diagram, {"format": True}).xml

    def create_grids_for_processes(self) -> None:
        """Build one expanded grid per executed process, deepest level first."""
        processes = self.layouted_processes
        processes.sort(key=lambda proc: getattr(proc, "level", 0), reverse=True)

        # create and add grids for each process
        # root processes should be processed last for element expanding
        for process in processes:
            # add base grid with collapsed elements
            grid = self.create_grid_layout(process)
            process.grid = grid

            expand_grid_horizontally(grid)
            expand_grid_vertically(grid)

            if is_truthy(getattr(process, "isExpanded", None)):
                row_count, col_count = grid.get_grid_dimensions()
                if row_count == 0:
                    grid.create_row()
                if col_count == 0:
                    grid.create_col()

    def set_expanded_property_to_moddle_elements(self, bpmn_model: Element) -> None:
        """Propagate ``isExpanded`` from DI shapes onto their semantic elements."""
        all_elements = bpmn_model.elements_by_id
        if all_elements is not None and all_elements is not UNDEFINED:
            for element in list(all_elements.values()):
                if (
                    element.type_ == "bpmndi:BPMNShape"
                    and getattr(element, "isExpanded", None) is True
                ):
                    element.get("bpmnElement").isExpanded = True

    def set_executed_processes(self, first_root_process: Element) -> None:
        """Discover layouted processes DFS (LIFO stack), tagging each level."""
        self.layouted_processes = []

        execution_stack = [first_root_process]

        while len(execution_stack) > 0:
            executed_process = execution_stack.pop()
            self.layouted_processes.append(executed_process)
            parent = executed_process.parent_
            if parent is self.diagram:
                executed_process.level = 0
            else:
                executed_process.level = parent.level + 1

            next_processes = [
                flow_element
                for flow_element in executed_process.get("flowElements")
                if is_(flow_element, "bpmn:SubProcess")
            ]

            execution_stack.extend(next_processes)

    def clean_di(self) -> None:
        """Discard any pre-existing hand-made DI."""
        self.diagram.diagrams = []

    def create_grid_layout(self, root: Element) -> Grid:
        """Run the depth-first grid walk over one process container."""
        grid = Grid()

        flow_elements = root.get("flowElements") or []
        elements = [element for element in flow_elements if not is_(element, "bpmn:SequenceFlow")]

        # check for empty process/subprocess
        if not is_truthy(flow_elements):
            return grid

        bind_boundary_events_with_hosts(flow_elements)

        # Depth-first-search
        visited: OrderedSet[Element] = OrderedSet()
        non_attached_count = len(
            [element for element in elements if not is_truthy(element.get("attachedToRef"))]
        )
        while len(visited) < non_attached_count:
            starting_elements = [
                element
                for element in flow_elements
                if not is_connection(element)
                and not is_boundary_event(element)
                and (not is_truthy(element.get("incoming")) or not has_other_incoming(element))
                and element not in visited
            ]

            stack = list(starting_elements)

            for start_element in starting_elements:
                grid.add(start_element)
                visited.add(start_element)

            self.handle_grid(grid, visited, stack)

            if grid.get_elements_total() != len(elements):
                grid_elements = grid.get_all_elements()
                missing_elements = [
                    element
                    for element in elements
                    if not any(other is element for other in grid_elements)
                    and not is_boundary_event(element)
                ]
                if len(missing_elements) > 0:
                    stack.append(missing_elements[0])
                    grid.add(missing_elements[0])
                    visited.add(missing_elements[0])
                    self.handle_grid(grid, visited, stack)
        return grid

    def generate_di(
        self, layout_grid: Grid, shift: dict[str, Any], proc_di: Element | None = None
    ) -> None:
        """Emit shape then connection DI for every grid position."""
        di_factory = self.di_factory

        if is_truthy(proc_di):
            pre_plane_element: Element = proc_di
        else:
            pre_plane_element = self.diagram.get("diagrams")[0]

        plane_element = pre_plane_element.get("plane").get("planeElement")

        # Step 1: Create DI for all elements
        for element, row, col in layout_grid.elements_by_position():
            dis = self.handle(
                "create_element_di",
                {
                    "element": element,
                    "row": row,
                    "col": col,
                    "layoutGrid": layout_grid,
                    "diFactory": di_factory,
                    "shift": shift,
                },
            )

            plane_element.extend(_flatten_one(dis))

        # Step 2: Create DI for all connections
        for element, row, col in layout_grid.elements_by_position():
            dis = self.handle(
                "create_connection_di",
                {
                    "element": element,
                    "row": row,
                    "col": col,
                    "layoutGrid": layout_grid,
                    "diFactory": di_factory,
                    "shift": shift,
                },
            )

            plane_element.extend(_flatten_one(dis))

    def handle_grid(self, grid: Grid, visited: OrderedSet[Element], stack: list[Element]) -> None:
        """Drain the DFS ``stack`` through every ``add_to_grid`` handler."""
        while len(stack) > 0:
            current_element = stack.pop()

            next_elements = self.handle(
                "add_to_grid",
                {
                    "element": current_element,
                    "grid": grid,
                    "visited": visited,
                    "stack": stack,
                },
            )

            for next_element in _flatten_one(next_elements):
                stack.append(next_element)
                visited.add(next_element)

    def get_process(self) -> Element | None:
        """Return the first ``bpmn:Process`` root element (``None`` when absent)."""
        for element in self.diagram.get("rootElements") or []:
            if element.type_ == "bpmn:Process":
                return element
        return None

    def create_root_di(self, process: Element) -> None:
        """Create the root plane and diagram for ``process``."""
        self.create_process_di(process)

    def create_process_di(self, element: Element) -> Element:
        """Create one plane plus diagram pair for ``element``."""
        di_factory = self.di_factory

        plane_di = di_factory.create_di_plane(
            {"id": "BPMNPlane_" + element.get("id"), "bpmnElement": element}
        )
        diagram_di = di_factory.create_di_diagram(
            {"id": "BPMNDiagram_" + element.get("id"), "plane": plane_di}
        )

        diagram = self.diagram

        diagram.get("diagrams").append(diagram_di)

        return diagram_di

    def draw_processes(self) -> None:
        """Draw every process, shallowest level first (expanded ones in place)."""
        sorted_processes = self.layouted_processes
        sorted_processes.sort(key=lambda proc: getattr(proc, "level", 0))

        for process in sorted_processes:
            # draw processes in expanded elements
            if is_truthy(getattr(process, "isExpanded", None)):
                base_proc_di: Element = self.get_element_di(process)
                diagram = self.get_proc_di(base_proc_di)
                bounds = base_proc_di.get("bounds")
                x = bounds.get("x")
                y = bounds.get("y")
                default_size = get_default_size(process)
                width = default_size["width"]
                height = default_size["height"]
                x += DEFAULT_CELL_WIDTH / 2 - width / 4
                y += DEFAULT_CELL_HEIGHT - height - height / 4
                self.generate_di(process.grid, {"x": x, "y": y}, diagram)
                continue

            # draw other processes (missing diagrams fall back to the root
            # plane inside `generate_di`, as upstream `.find` yields undefined)
            diagram = next(
                (
                    candidate
                    for candidate in self.diagram.get("diagrams")
                    if candidate.get("plane").get("bpmnElement") is process
                ),
                None,
            )
            self.generate_di(process.grid, {"x": 0, "y": 0}, diagram)

    def get_element_di(self, element: Element) -> Element | None:
        """Return the plane element drawn for ``element`` (identity match)."""
        for diagram in self.diagram.get("diagrams"):
            for item in diagram.get("plane").get("planeElement"):
                if item.get("bpmnElement") is element:
                    return item
        return None

    def get_proc_di(self, element: Element) -> Element | None:
        """Return the diagram whose plane contains ``element``."""
        for diagram in self.diagram.get("diagrams"):
            if any(item is element for item in diagram.get("plane").get("planeElement")):
                return diagram
        return None


def _flatten_one(nested: list[Element]) -> list[Element]:
    """Flatten one level (``Array.prototype.flat()`` depth 1)."""
    flat: list[Element] = []
    for item in nested:
        if isinstance(item, list):
            flat.extend(item)
        else:
            flat.append(item)
    return flat


def bind_boundary_events_with_hosts(elements: list[Element]) -> None:
    """Attach each boundary event to its host's ``attachers`` list."""
    boundary_events = [element for element in elements if is_boundary_event(element)]
    for boundary_event in boundary_events:
        attached_task = boundary_event.get("attachedToRef")
        attachers = getattr(attached_task, "attachers", None) or []
        attachers.append(boundary_event)
        attached_task.attachers = attachers


def expand_grid_horizontally(grid: Grid) -> None:
    """Widen parent columns holding expanded elements to fit their sub-grids."""
    num_rows, max_cols = grid.get_grid_dimensions()
    for index in range(max_cols - 1, -1, -1):
        elements_in_col = []
        for row_index in range(num_rows):
            candidate = grid.get(row_index, index)
            if is_truthy(candidate) and is_truthy(getattr(candidate, "isExpanded", None)):
                elements_in_col.append(candidate)

        if len(elements_in_col) == 0:
            continue

        max_col_count: int | UndefinedType = UNDEFINED
        for current in elements_in_col:
            _rows, current_cols = current.grid.get_grid_dimensions()
            if max_col_count is UNDEFINED or current_cols > max_col_count:
                max_col_count = current_cols

        shift: int = 2 if not is_truthy(max_col_count) else cast("int", max_col_count)
        grid.create_col(index, shift)


def expand_grid_vertically(grid: Grid) -> None:
    """Deepen parent rows holding expanded elements to fit their sub-grids."""
    num_rows, max_cols = grid.get_grid_dimensions()

    for index in range(num_rows - 1, -1, -1):
        elements_in_row = []
        for col_index in range(max_cols):
            candidate = grid.get(index, col_index)
            if is_truthy(candidate) and is_truthy(getattr(candidate, "isExpanded", None)):
                elements_in_row.append(candidate)

        if len(elements_in_row) == 0:
            continue

        max_row_count: int | UndefinedType = UNDEFINED
        for current in elements_in_row:
            current_rows, _cols = current.grid.get_grid_dimensions()
            if max_row_count is UNDEFINED or current_rows > max_row_count:
                max_row_count = current_rows

        shift = 1 if not is_truthy(max_row_count) else cast("int", max_row_count)

        # expand the parent grid vertically
        for _ in range(shift):
            grid.create_row(index)


def has_other_incoming(element: Element) -> bool:
    """Return whether ``element`` has a non-self incoming edge worth waiting for."""
    incoming = element.get("incoming") or []

    from_host = [
        edge
        for edge in incoming
        if edge.get("sourceRef") is not element
        and edge.get("sourceRef").get("attachedToRef") is UNDEFINED
    ]

    from_attached = [
        edge
        for edge in incoming
        if edge.get("sourceRef") is not element
        and edge.get("sourceRef").get("attachedToRef") is not element
    ]

    return len(from_host) > 0 or len(from_attached) > 0
