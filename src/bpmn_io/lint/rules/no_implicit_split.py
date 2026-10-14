# Transposed from bpmn-io/bpmnlint@de71146 rules/no-implicit-split.js (MIT).
"""Rule: no implicit split starting from a task or event."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bpmn_io._bpmnlint_utils import is_any
from bpmn_io._js import is_truthy
from bpmn_io.lint.rules.helper import annotate_rule, prop, prop_list

if TYPE_CHECKING:
    from bpmn_io.lint.test_rule import Reporter
    from bpmn_io.moddle.base import ModdleElement

__all__ = ["factory"]


def factory(_config: object = None) -> dict[str, Any]:
    """Create the ``no-implicit-split`` rule (upstream rule factory)."""

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if not is_any(node, ["bpmn:Activity", "bpmn:Event"]):
            return

        outgoing = prop_list(node, "outgoing")

        outgoing_without_condition = [
            flow
            for flow in outgoing
            if not _has_condition(flow) and not _is_default_flow(node, flow)
        ]

        if len(outgoing_without_condition) > 1:
            reporter.report(node.get("id"), "Flow splits implicitly")

    return annotate_rule("no-implicit-split", {"check": check})


def _has_condition(flow: ModdleElement) -> bool:
    return is_truthy(prop(flow, "conditionExpression"))


def _is_default_flow(node: ModdleElement, flow: ModdleElement) -> bool:
    return prop(node, "default") is flow
