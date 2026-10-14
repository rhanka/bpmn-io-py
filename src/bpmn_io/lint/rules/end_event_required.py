# Transposed from bpmn-io/bpmnlint@de71146 rules/end-event-required.js (MIT).
"""Rule: every process/scope must contain an end event."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bpmn_io._bpmnlint_utils import is_, is_any
from bpmn_io.lint.rules.helper import annotate_rule, prop_list

if TYPE_CHECKING:
    from bpmn_io.lint.test_rule import Reporter
    from bpmn_io.moddle.base import ModdleElement

__all__ = ["factory"]


def factory(_config: object = None) -> dict[str, Any]:
    """Create the ``end-event-required`` rule (upstream rule factory)."""

    def _has_end_event(node: ModdleElement) -> bool:
        return any(is_(element, "bpmn:EndEvent") for element in prop_list(node, "flowElements"))

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if not is_any(node, ["bpmn:Process", "bpmn:SubProcess"]) or is_(
            node, "bpmn:AdHocSubProcess"
        ):
            return

        if not _has_end_event(node):
            type_label = "Sub process" if is_(node, "bpmn:SubProcess") else "Process"

            reporter.report(node.get("id"), f"{type_label} is missing end event")

    return annotate_rule("end-event-required", {"check": check})
