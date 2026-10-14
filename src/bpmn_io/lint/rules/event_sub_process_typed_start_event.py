# Transposed from bpmn-io/bpmnlint@de71146 rules/event-sub-process-typed-start-event.js (MIT).
"""Rule: start events inside an event sub-process must be typed."""

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
    """Create the ``event-sub-process-typed-start-event`` rule (upstream rule factory)."""

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if not is_(node, "bpmn:SubProcess") or not is_truthy(prop(node, "triggeredByEvent")):
            return

        for flow_element in prop_list(node, "flowElements"):
            if not is_(flow_element, "bpmn:StartEvent"):
                continue

            if len(prop_list(flow_element, "eventDefinitions")) == 0:
                reporter.report(
                    flow_element.get("id"),
                    "Start event is missing event definition",
                    ["eventDefinitions"],
                )

    return annotate_rule("event-sub-process-typed-start-event", {"check": check})
