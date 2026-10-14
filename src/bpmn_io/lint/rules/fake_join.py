# Transposed from bpmn-io/bpmnlint@de71146 rules/fake-join.js (MIT).
"""Rule: activities and events must not have multiple incoming flows (fake join)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bpmn_io._bpmnlint_utils import is_any
from bpmn_io.lint.rules.helper import annotate_rule, prop_list

if TYPE_CHECKING:
    from bpmn_io.lint.test_rule import Reporter
    from bpmn_io.moddle.base import ModdleElement

__all__ = ["factory"]


def factory(_config: object = None) -> dict[str, Any]:
    """Create the ``fake-join`` rule (upstream rule factory)."""

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if not is_any(node, ["bpmn:Activity", "bpmn:Event"]):
            return

        if len(prop_list(node, "incoming")) > 1:
            reporter.report(node.get("id"), "Incoming flows do not join")

    return annotate_rule("fake-join", {"check": check})
