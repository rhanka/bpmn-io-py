# Transposed from bpmn-io/bpmnlint@de71146 rules/no-implicit-end.js (MIT).
"""Rule: an element must not be an implicit end (token sink)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bpmn_io._bpmnlint_utils import is_, is_any
from bpmn_io._js import is_truthy
from bpmn_io.lint.rules.helper import annotate_rule, find_parent, prop, prop_list

if TYPE_CHECKING:
    from bpmn_io.lint.test_rule import Reporter
    from bpmn_io.moddle.base import ModdleElement

__all__ = ["factory"]


def factory(_config: object = None) -> dict[str, Any]:
    """Create the ``no-implicit-end`` rule (upstream rule factory)."""

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if not is_any(node, ["bpmn:Event", "bpmn:Activity", "bpmn:Gateway"]):
            return

        if _is_implicit_end(node):
            reporter.report(node.get("id"), "Element is an implicit end")

    return annotate_rule("no-implicit-end", {"check": check})


def _is_link_event(node: ModdleElement) -> bool:
    event_definitions = prop_list(node, "eventDefinitions")

    return len(event_definitions) > 0 and all(
        is_(definition, "bpmn:LinkEventDefinition") for definition in event_definitions
    )


def _is_compensation_event(node: ModdleElement) -> bool:
    event_definitions = prop_list(node, "eventDefinitions")

    return len(event_definitions) > 0 and all(
        is_(definition, "bpmn:CompensateEventDefinition") for definition in event_definitions
    )


def _has_compensation_activity(node: ModdleElement) -> bool:
    parent = find_parent(node, "bpmn:Process")

    artifacts = prop_list(parent, "artifacts") if parent is not None else []

    for element in artifacts:
        if not is_(element, "bpmn:Association"):
            continue

        source = prop(element, "sourceRef")

        if source is not None and source.get("id") == node.get("id"):
            return True

    return False


def _is_for_compensation(node: ModdleElement) -> bool:
    return is_truthy(prop(node, "isForCompensation"))


def _is_implicit_end(node: ModdleElement) -> bool:
    outgoing = prop_list(node, "outgoing")

    exempt = (
        (is_(node, "bpmn:SubProcess") and is_truthy(prop(node, "triggeredByEvent")))
        or (is_(node, "bpmn:IntermediateThrowEvent") and _is_link_event(node))
        or _is_in_ad_hoc(node)
        or is_(node, "bpmn:EndEvent")
        or (
            is_(node, "bpmn:BoundaryEvent")
            and _is_compensation_event(node)
            and _has_compensation_activity(node)
        )
        or (is_(node, "bpmn:Activity") and _is_for_compensation(node))
    )

    if exempt:
        return False

    return len(outgoing) == 0


def _is_in_ad_hoc(node: ModdleElement) -> bool:
    parent = node.parent_
    return parent is not None and is_(parent, "bpmn:AdHocSubProcess")
