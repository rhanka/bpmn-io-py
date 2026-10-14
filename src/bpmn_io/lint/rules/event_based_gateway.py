# Transposed from bpmn-io/bpmnlint@de71146 rules/event-based-gateway.js (MIT).
"""Rule: an event-based gateway needs at least two unconditional outgoing flows."""

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
    """Create the ``event-based-gateway`` rule (upstream rule factory)."""

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if not is_(node, "bpmn:EventBasedGateway"):
            return

        outgoing = prop_list(node, "outgoing")

        if len(outgoing) < 2:
            reporter.report(
                node.get("id"),
                "An <Event-based Gateway> must have at least 2 outgoing <Sequence Flows>",
            )

        for flow in outgoing:
            if _has_condition(flow):
                reporter.report(
                    flow.get("id"),
                    "A <Sequence Flow> outgoing from an <Event-based Gateway> "
                    "must not be conditional",
                )

    return annotate_rule("event-based-gateway", {"check": check})


def _has_condition(flow: ModdleElement) -> bool:
    return is_truthy(prop(flow, "conditionExpression"))
