# Transposed from bpmn-io/bpmnlint@de71146 rules/conditional-flows.js (MIT).
"""Rule: sequence flows out of a conditional fork need a condition or be default."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bpmn_io._js import is_truthy
from bpmn_io.lint.rules.helper import annotate_rule, prop, prop_list

if TYPE_CHECKING:
    from bpmn_io.lint.test_rule import Reporter
    from bpmn_io.moddle.base import ModdleElement

__all__ = ["factory"]


def factory(_config: object = None) -> dict[str, Any]:
    """Create the ``conditional-flows`` rule (upstream rule factory)."""

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if not _is_conditional_forking(node):
            return

        for flow in prop_list(node, "outgoing"):
            missing_condition = not _has_condition(flow) and not _is_default_flow(node, flow)

            if missing_condition:
                reporter.report(
                    flow.get("id"),
                    "Sequence flow is missing condition",
                    ["conditionExpression"],
                )

    return annotate_rule("conditional-flows", {"check": check})


def _is_conditional_forking(node: ModdleElement) -> bool:
    default_flow = prop(node, "default")
    outgoing = prop_list(node, "outgoing")

    return is_truthy(default_flow) or any(_has_condition(flow) for flow in outgoing)


def _has_condition(flow: ModdleElement) -> bool:
    return is_truthy(prop(flow, "conditionExpression"))


def _is_default_flow(node: ModdleElement, flow: ModdleElement) -> bool:
    return prop(node, "default") is flow
