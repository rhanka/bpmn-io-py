# Transposed from bpmn-io/bpmnlint@de71146 rules/superfluous-termination.js (MIT).
"""Rule: a termination end event is superfluous when every end is interrupting/terminating."""

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
    """Create the ``superfluous-termination`` rule (upstream rule factory)."""

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if not is_any(node, ["bpmn:Process", "bpmn:SubProcess"]):
            return

        flow_elements = prop_list(node, "flowElements")

        ends = [
            element
            for element in flow_elements
            if is_(element, "bpmn:FlowNode") and len(prop_list(element, "outgoing")) == 0
        ]

        terminate_ends = [end for end in ends if _is_terminate_end(end)]

        if len(terminate_ends) != 1:
            # only detect basic cases
            return

        superfluous = all(_is_interrupting_event_sub(end) or _is_terminate_end(end) for end in ends)

        if superfluous:
            for terminate_end in terminate_ends:
                reporter.report(terminate_end.get("id"), "Termination is superfluous.")

    return annotate_rule("superfluous-termination", {"check": check})


def _is_terminate_end(element: ModdleElement) -> bool:
    return is_(element, "bpmn:EndEvent") and any(
        is_(definition, "bpmn:TerminateEventDefinition")
        for definition in prop_list(element, "eventDefinitions")
    )


def _is_interrupting_event_sub(element: ModdleElement) -> bool:
    is_event_sub = is_(element, "bpmn:SubProcess") and is_truthy(prop(element, "triggeredByEvent"))

    return bool(is_event_sub) and any(
        is_(child, "bpmn:StartEvent") and is_truthy(prop(child, "isInterrupting"))
        for child in prop_list(element, "flowElements")
    )
