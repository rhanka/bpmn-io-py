# Transposed from bpmn-io/bpmnlint@de71146 rules/label-required.js (MIT).
"""Rule: flow nodes, conditional flows, participants and lanes need a label/name."""

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
    """Create the ``label-required`` rule (upstream rule factory)."""

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if is_any(node, ["bpmn:ParallelGateway", "bpmn:EventBasedGateway"]):
            return

        # ignore joining gateways
        if is_(node, "bpmn:Gateway") and not _is_forking(node):
            return

        # ignore sub-processes
        if is_(node, "bpmn:SubProcess"):
            return

        # ignore sequence flow without condition
        if is_(node, "bpmn:SequenceFlow") and not _has_condition(node):
            return

        # ignore data objects and artifacts for now
        if is_any(
            node,
            ["bpmn:FlowNode", "bpmn:SequenceFlow", "bpmn:Participant", "bpmn:Lane"],
        ):
            name = prop(node, "name") or ""

            if len(name.strip()) == 0:
                reporter.report(node.get("id"), "Element is missing label/name", ["name"])

    return annotate_rule("label-required", {"check": check})


def _is_forking(node: ModdleElement) -> bool:
    return len(prop_list(node, "outgoing")) > 1


def _has_condition(node: ModdleElement) -> bool:
    return is_truthy(prop(node, "conditionExpression"))
