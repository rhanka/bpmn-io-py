# Transposed from bpmn-io/bpmnlint@de71146 rules/no-duplicate-sequence-flows.js (MIT).
"""Rule: no duplicate sequence flows between the same source and target."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bpmn_io._bpmnlint_utils import is_
from bpmn_io.lint.rules.helper import annotate_rule, prop

if TYPE_CHECKING:
    from bpmn_io.lint.test_rule import Reporter
    from bpmn_io.moddle.base import ModdleElement

__all__ = ["factory"]


def factory(_config: object = None) -> dict[str, Any]:
    """Create the ``no-duplicate-sequence-flows`` rule (upstream rule factory)."""
    keyed: dict[str, ModdleElement] = {}
    outgoing_reported: dict[Any, bool] = {}
    incoming_reported: dict[Any, bool] = {}

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if not is_(node, "bpmn:SequenceFlow"):
            return

        key = _flow_key(node)

        if key in keyed:
            reporter.report(node.get("id"), "SequenceFlow is a duplicate")

            source_ref = prop(node, "sourceRef")
            target_ref = prop(node, "targetRef")
            source_id = source_ref.get("id") if source_ref is not None else None
            target_id = target_ref.get("id") if target_ref is not None else None

            if not outgoing_reported.get(source_id):
                reporter.report(source_id, "Duplicate outgoing sequence flows")

                outgoing_reported[source_id] = True

            if not incoming_reported.get(target_id):
                reporter.report(target_id, "Duplicate incoming sequence flows")

                incoming_reported[target_id] = True
        else:
            keyed[key] = node

    return annotate_rule("no-duplicate-sequence-flows", {"check": check})


def _flow_key(flow: ModdleElement) -> str:
    condition_expression = prop(flow, "conditionExpression")

    condition = ""
    if condition_expression is not None:
        body = prop(condition_expression, "body")
        condition = body if body is not None else ""

    source_ref = prop(flow, "sourceRef")
    target_ref = prop(flow, "targetRef")
    source = source_ref.get("id") if source_ref is not None else flow.get("id")
    target = target_ref.get("id") if target_ref is not None else flow.get("id")

    return f"{source}#{target}#{condition}"
