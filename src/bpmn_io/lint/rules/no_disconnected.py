# Transposed from bpmn-io/bpmnlint@de71146 rules/no-disconnected.js (MIT).
"""Rule: flow elements must not be disconnected (no incoming and no outgoing)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bpmn_io._bpmnlint_utils import is_, is_any
from bpmn_io._js import is_truthy
from bpmn_io.lint.rules.helper import annotate_rule, prop, prop_list

if TYPE_CHECKING:
    from bpmn_io.lint.test_rule import Reporter
    from bpmn_io.moddle.base import ModdleElement

__all__ = ["factory"]


def factory(_config: object = None) -> dict[str, Any]:
    """Create the ``no-disconnected`` rule (upstream rule factory)."""

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if not is_any(
            node,
            ["bpmn:Task", "bpmn:Gateway", "bpmn:SubProcess", "bpmn:Event"],
        ) or is_truthy(prop(node, "triggeredByEvent")):
            return

        # compensation activity and boundary events are linked visually
        if _is_compensation_linked(node):
            return

        # adhoc subprocesses can have disconnected activities
        parent = node.parent_
        if parent is not None and is_(parent, "bpmn:AdHocSubProcess"):
            return

        incoming = prop_list(node, "incoming")
        outgoing = prop_list(node, "outgoing")

        if not incoming and not outgoing:
            reporter.report(node.get("id"), "Element is not connected")

    return annotate_rule("no-disconnected", {"check": check})


def _is_compensation_boundary(node: ModdleElement) -> bool:
    event_definitions = prop_list(node, "eventDefinitions")

    if not is_(node, "bpmn:BoundaryEvent"):
        return False

    if len(event_definitions) != 1:
        return False

    return is_(event_definitions[0], "bpmn:CompensateEventDefinition")


def _is_compensation_activity(node: ModdleElement) -> bool:
    return is_truthy(prop(node, "isForCompensation"))


def _is_compensation_linked(node: ModdleElement) -> bool:
    source = _is_compensation_boundary(node)
    target = _is_compensation_activity(node)

    return source or target
