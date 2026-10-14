# Transposed from bpmn-io/bpmnlint@de71146 rules/superfluous-label.js (MIT).
"""Rule: unconditional sequence flows must not have a label."""

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
    """Create the ``superfluous-label`` rule (upstream rule factory)."""

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if not is_(node, "bpmn:SequenceFlow"):
            return

        name = prop(node, "name") or ""

        if not name.strip():
            return

        if _has_condition(node) or _is_default_flow(node) or _is_gateway_fork(node):
            return

        reporter.report(node.get("id"), "Sequence flow has superfluous label", ["name"])

    return annotate_rule("superfluous-label", {"check": check})


def _has_condition(flow: ModdleElement) -> bool:
    return is_truthy(prop(flow, "conditionExpression"))


def _is_default_flow(flow: ModdleElement) -> bool:
    source = prop(flow, "sourceRef")

    return source is not None and prop(source, "default") is flow


def _is_gateway_fork(flow: ModdleElement) -> bool:
    source = prop(flow, "sourceRef")

    if not source:
        return False

    is_decision_gateway = is_(source, "bpmn:ExclusiveGateway") or is_(
        source, "bpmn:InclusiveGateway"
    )

    return is_decision_gateway and len(prop_list(source, "outgoing")) > 1
