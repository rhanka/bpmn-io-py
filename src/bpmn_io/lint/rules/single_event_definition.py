# Transposed from bpmn-io/bpmnlint@de71146 rules/single-event-definition.js (MIT).
"""Rule: an event must contain at most one event definition."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bpmn_io._bpmnlint_utils import is_
from bpmn_io.lint.rules.helper import annotate_rule, prop_list

if TYPE_CHECKING:
    from bpmn_io.lint.test_rule import Reporter
    from bpmn_io.moddle.base import ModdleElement

__all__ = ["factory"]


def factory(_config: object = None) -> dict[str, Any]:
    """Create the ``single-event-definition`` rule (upstream rule factory)."""

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if not is_(node, "bpmn:Event"):
            return

        if len(prop_list(node, "eventDefinitions")) > 1:
            reporter.report(
                node.get("id"), "Event has multiple event definitions", ["eventDefinitions"]
            )

    return annotate_rule("single-event-definition", {"check": check})
