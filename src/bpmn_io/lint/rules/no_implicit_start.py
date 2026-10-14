# Transposed from bpmn-io/bpmnlint@de71146 rules/no-implicit-start.js (MIT).
"""Rule: an element must not be an implicit start (token spawn)."""

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
    """Create the ``no-implicit-start`` rule (upstream rule factory)."""

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if not is_any(node, ["bpmn:Event", "bpmn:Activity", "bpmn:Gateway"]):
            return

        if _is_implicit_start(node):
            reporter.report(node.get("id"), "Element is an implicit start")

    return annotate_rule("no-implicit-start", {"check": check})


def _is_link_event(node: ModdleElement) -> bool:
    event_definitions = prop_list(node, "eventDefinitions")

    return len(event_definitions) > 0 and all(
        is_(definition, "bpmn:LinkEventDefinition") for definition in event_definitions
    )


def _is_for_compensation(node: ModdleElement) -> bool:
    return is_truthy(prop(node, "isForCompensation"))


def _is_implicit_start(node: ModdleElement) -> bool:
    incoming = prop_list(node, "incoming")

    if is_(node, "bpmn:Activity") and _is_for_compensation(node):
        return False

    parent = node.parent_
    if parent is not None and is_(parent, "bpmn:AdHocSubProcess"):
        return False

    if is_(node, "bpmn:SubProcess") and is_truthy(prop(node, "triggeredByEvent")):
        return False

    if is_(node, "bpmn:IntermediateCatchEvent") and _is_link_event(node):
        return False

    if is_any(node, ["bpmn:StartEvent", "bpmn:BoundaryEvent"]):
        return False

    return len(incoming) == 0
