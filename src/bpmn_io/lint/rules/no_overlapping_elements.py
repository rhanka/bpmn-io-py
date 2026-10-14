# Transposed from bpmn-io/bpmnlint@de71146 rules/no-overlapping-elements.js (MIT).
"""Rule: elements must not overlap, nor lie outside their parent boundary."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, cast

from bpmn_io._bpmnlint_utils import is_
from bpmn_io._js import UNDEFINED
from bpmn_io.lint.rules.helper import annotate_rule, prop, prop_list

if TYPE_CHECKING:
    from collections.abc import Iterator

    from bpmn_io.lint.test_rule import Reporter
    from bpmn_io.moddle.base import ModdleElement

__all__ = ["factory"]


class _OrderedSet:
    """Insertion-ordered set of elements (JS ``Set`` semantics)."""

    def __init__(self) -> None:
        self._items: dict[int, ModdleElement] = {}

    def add(self, element: ModdleElement) -> None:
        self._items[id(element)] = element

    def __contains__(self, element: ModdleElement) -> bool:
        return id(element) in self._items

    def __iter__(self) -> Iterator[ModdleElement]:
        return iter(self._items.values())


def factory(_config: object = None) -> dict[str, Any]:
    """Create the ``no-overlapping-elements`` rule (upstream rule factory)."""

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if not is_(node, "bpmn:Definitions"):
            return

        root_elements = prop_list(node, "rootElements")
        elements_to_report = _OrderedSet()
        elements_outside_to_report = _OrderedSet()
        di_objects = _get_all_di_objects(node)

        _check_roots(
            root_elements,
            elements_to_report,
            elements_outside_to_report,
            di_objects,
        )

        # report elements
        for element in elements_to_report:
            reporter.report(element.get("id"), "Element overlaps with other element")
        for element in elements_outside_to_report:
            reporter.report(element.get("id"), "Element is outside of parent boundary")

    return annotate_rule("no-overlapping-elements", {"check": check})


def _check_process(
    node: ModdleElement,
    elements_to_report: _OrderedSet,
    elements_outside_to_report: _OrderedSet,
    di_objects: dict[int, Any],
    parent_di: object,
) -> None:
    flow_elements = prop_list(node, "flowElements")

    flow_elements_with_di = [e for e in flow_elements if id(e) in di_objects]

    # check child elements for overlap
    _check_elements_array(flow_elements_with_di, elements_to_report, di_objects)

    # check child elements outside parent boundary
    parent_bounds = (
        parent_di.get("bounds")
        if isinstance(parent_di, dict)
        else prop(cast("ModdleElement", parent_di), "bounds")
        if parent_di
        else None
    )
    for element in flow_elements_with_di:
        di = di_objects.get(id(element))
        bounds = prop(di, "bounds") if di is not None else None
        if not is_(element, "bpmn:DataStoreReference") and _is_outside_parent_boundary(
            bounds,
            parent_bounds,
        ):
            elements_outside_to_report.add(element)

    # recurse into subprocesses
    for sub_process in flow_elements:
        if not is_(sub_process, "bpmn:SubProcess"):
            continue
        sub_di = di_objects.get(id(sub_process)) or {}
        is_expanded = (
            prop(sub_di, "isExpanded") if not isinstance(sub_di, dict) else sub_di.get("isExpanded")
        )
        sub_parent_boundary = sub_di if is_expanded else {}
        _check_process(
            sub_process,
            elements_to_report,
            elements_outside_to_report,
            di_objects,
            sub_parent_boundary,
        )


def _check_elements_array(
    elements: list[ModdleElement],
    elements_to_report: _OrderedSet,
    di_objects: dict[int, Any],
) -> None:
    shapes = _get_shapes(elements, di_objects)
    shapes.sort(key=lambda shape: shape["left"])

    overlapping = _OrderedSet()

    for i, shape in enumerate(shapes):
        # shapes starting right of this one cannot overlap it
        j = i + 1
        while j < len(shapes) and shapes[j]["left"] <= shape["right"]:
            other_shape = shapes[j]

            if _is_collision(shape, other_shape):
                # ignore if Boundary events overlap their host
                shape_element = shape["element"]
                other_element = other_shape["element"]
                attached_shape = prop(shape_element, "attachedToRef")
                attached_other = prop(other_element, "attachedToRef")
                if attached_shape is not other_element and attached_other is not shape_element:
                    overlapping.add(shape_element)
                    overlapping.add(other_element)

            j += 1

    # report in element order, independent of the order overlaps are detected
    for element in elements:
        if element in overlapping:
            elements_to_report.add(element)


def _get_shapes(elements: list[ModdleElement], di_objects: dict[int, Any]) -> list[dict[str, Any]]:
    shapes: list[dict[str, Any]] = []

    for element in elements:
        di = di_objects.get(id(element))
        bounds = prop(di, "bounds") if di is not None else None

        if not _is_valid_shape_element(bounds):
            continue

        bounds_element = cast("ModdleElement", bounds)
        left = cast("float", bounds_element.get("x"))
        right = left + cast("float", bounds_element.get("width"))

        # shapes with a NaN left or right edge never collide
        if isinstance(left, float) and math.isnan(left):
            continue
        if isinstance(right, float) and math.isnan(right):
            continue

        shapes.append(
            {
                "element": element,
                "left": left,
                "right": right,
                "top": cast("float", bounds_element.get("y")),
                "bottom": cast("float", bounds_element.get("y"))
                + cast("float", bounds_element.get("height")),
            },
        )

    return shapes


def _is_outside_parent_boundary(child_bounds: object, parent_bounds: object) -> bool:
    if not _is_valid_shape_element(child_bounds) or not _is_valid_shape_element(parent_bounds):
        return False

    child = cast("ModdleElement", child_bounds)
    parent = cast("ModdleElement", parent_bounds)
    is_top_left_inside = cast("float", child.get("x")) >= cast("float", parent.get("x")) and cast(
        "float", child.get("y")
    ) >= cast("float", parent.get("y"))
    is_bottom_right_inside = cast("float", child.get("x")) + cast(
        "float", child.get("width")
    ) <= cast("float", parent.get("x")) + cast("float", parent.get("width")) and cast(
        "float", child.get("y")
    ) + cast("float", child.get("height")) <= cast("float", parent.get("y")) + cast(
        "float", parent.get("height")
    )
    is_inside = is_top_left_inside and is_bottom_right_inside

    return not is_inside


def _is_collision(first_shape: dict[str, Any], second_shape: dict[str, Any]) -> bool:
    collision_x = (
        first_shape["right"] >= second_shape["left"]
        and second_shape["right"] >= first_shape["left"]
    )
    collision_y = (
        first_shape["bottom"] >= second_shape["top"]
        and second_shape["bottom"] >= first_shape["top"]
    )

    # collision on both axis
    return bool(collision_x and collision_y)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_valid_shape_element(bounds: object) -> bool:
    if bounds is None or bounds is UNDEFINED:
        return False
    if not is_(bounds, "dc:Bounds"):
        return False
    bounds_element = cast("ModdleElement", bounds)
    return all(_is_number(bounds_element.get(key)) for key in ("x", "y", "width", "height"))


def _get_all_di_objects(node: ModdleElement) -> dict[int, Any]:
    di_objects: dict[int, Any] = {}

    for diagram in prop_list(node, "diagrams"):
        plane = prop(diagram, "plane")
        if not plane:
            continue
        for plane_element in prop_list(plane, "planeElement"):
            bpmn_element = prop(plane_element, "bpmnElement")
            if bpmn_element:
                di_objects[id(bpmn_element)] = plane_element

    return di_objects


def _check_roots(
    root_elements: list[ModdleElement],
    elements_to_report: _OrderedSet,
    elements_outside_to_report: _OrderedSet,
    di_objects: dict[int, Any],
) -> None:
    """Check collaborations/participants and processes of one definitions root."""
    process_elements_parent_di_map: dict[int, Any] = {}

    for collaboration in root_elements:
        if not is_(collaboration, "bpmn:Collaboration"):
            continue
        participants = prop_list(collaboration, "participants")
        _check_elements_array(participants, elements_to_report, di_objects)

        for participant in participants:
            process_ref = prop(participant, "processRef")
            if process_ref is not None:
                process_elements_parent_di_map[id(process_ref)] = di_objects.get(id(participant))

    for process in root_elements:
        if not is_(process, "bpmn:Process"):
            continue
        parent_di = process_elements_parent_di_map.get(id(process)) or {}
        _check_process(
            process,
            elements_to_report,
            elements_outside_to_report,
            di_objects,
            parent_di,
        )
