# Transposed from bpmn-io/bpmnlint@de71146 rules/single-blank-start-event.js (MIT).
"""Rule: at most one blank start event per scope."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bpmn_io._bpmnlint_utils import is_
from bpmn_io.lint.rules.helper import annotate_rule, prop_list

if TYPE_CHECKING:
    from bpmn_io.lint.test_rule import Reporter
    from bpmn_io.moddle.base import ModdleElement

__all__ = ["factory"]


def factory(_config: object = None) -> dict[str, Any]:
    """Create the ``single-blank-start-event`` rule (upstream rule factory)."""

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if not is_(node, "bpmn:FlowElementsContainer"):
            return

        blank_start_events = [
            element
            for element in prop_list(node, "flowElements")
            if is_(element, "bpmn:StartEvent") and len(prop_list(element, "eventDefinitions")) == 0
        ]

        if len(blank_start_events) > 1:
            type_label = "Sub process" if is_(node, "bpmn:SubProcess") else "Process"

            reporter.report(node.get("id"), f"{type_label} has multiple blank start events")

    return annotate_rule("single-blank-start-event", {"check": check})
