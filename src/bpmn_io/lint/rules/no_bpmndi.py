# Transposed from bpmn-io/bpmnlint@de71146 rules/no-bpmndi.js (MIT).
"""Rule: every visual BPMN element must have BPMNDI information."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bpmn_io._bpmnlint_utils import is_
from bpmn_io._js import is_truthy
from bpmn_io.lint.rules.helper import annotate_rule, prop, prop_list

if TYPE_CHECKING:
    from bpmn_io.lint.test_rule import Reporter
    from bpmn_io.moddle.base import ModdleElement

__all__ = ["factory"]


def factory(_config: object = None) -> dict[str, Any]:
    """Create the ``no-bpmndi`` rule (upstream rule factory)."""

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if not is_(node, "bpmn:Definitions"):
            return

        # (1) Construct array of all BPMN elements
        bpmn_elements = _get_all_bpmn_elements(prop_list(node, "rootElements"))

        # (2) Filter BPMN elements without visual representation
        visual_bpmn_elements = [e for e in bpmn_elements if _has_visual_representation(e)]

        # (3) Construct set of BPMNDI references
        referenced_ids = _get_referenced_bpmn_element_ids(node)

        # (4) Report elements without BPMNDI
        for element in visual_bpmn_elements:
            if element.get("id") not in referenced_ids:
                reporter.report(element.get("id"), "Element is missing bpmndi")

    return annotate_rule("no-bpmndi", {"check": check})


def _flatten(items: list[Any]) -> list[Any]:
    """Upstream ``flatten`` (min-dash): recursively flatten nested lists."""
    flattened: list[Any] = []
    for item in items:
        if isinstance(item, list):
            flattened.extend(_flatten(item))
        else:
            flattened.append(item)
    return flattened


def _get_all_bpmn_elements(root_elements: list[ModdleElement]) -> list[ModdleElement]:
    """Get all BPMN elements within a ``bpmn:Definitions`` node (upstream helper)."""

    def _collect(elements: list[ModdleElement]) -> list[ModdleElement]:
        collected: list[Any] = []

        for root_element in elements:
            lane_sets = prop_list(root_element, "laneSets")
            lane_set = (lane_sets[0] if lane_sets else None) or prop(root_element, "childLaneSet")

            flow_elements = prop_list(root_element, "flowElements")
            lanes = prop_list(lane_set, "lanes") if lane_set is not None else []

            nested = (
                _collect([e for e in flow_elements if _has_flow_elements(e)])
                if flow_elements
                else []
            )
            nested_lanes = (
                _collect([lane for lane in lanes if _has_child_lane_set(lane)]) if lanes else []
            )

            flat = _flatten(
                [
                    flow_elements,
                    nested,
                    prop_list(root_element, "participants"),
                    prop_list(root_element, "artifacts"),
                    lanes,
                    nested_lanes,
                    prop_list(root_element, "messageFlows"),
                ],
            )

            if len(flat) > 0:
                collected.extend(flat)
            else:
                # We are not interested in the rest here (DI)
                collected.append([])

        return _flatten(collected)

    return _collect(root_elements)


def _get_referenced_bpmn_element_ids(definitions_node: ModdleElement) -> set[Any]:
    """Get the ids of all BPMN elements referenced by BPMNDI elements."""
    referenced: list[Any] = []

    for diagram in prop_list(definitions_node, "diagrams"):
        plane = prop(diagram, "plane")
        di_elements = prop_list(plane, "planeElement") if plane is not None else []

        for element in di_elements:
            bpmn_element = prop(element, "bpmnElement")
            referenced.append(bpmn_element.get("id") if bpmn_element is not None else None)

    return set(_flatten(referenced))


def _has_visual_representation(element: ModdleElement) -> bool:
    no_vis_representation = ["bpmn:DataObject"]

    return element.type_ not in no_vis_representation


def _has_flow_elements(element: ModdleElement) -> bool:
    return is_truthy(prop(element, "flowElements"))


def _has_child_lane_set(element: ModdleElement) -> bool:
    return is_truthy(prop(element, "childLaneSet"))
