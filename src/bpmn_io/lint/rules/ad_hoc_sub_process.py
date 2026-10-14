# Transposed from bpmn-io/bpmnlint@de71146 rules/ad-hoc-sub-process.js (MIT).
"""Rule: an Ad Hoc Sub Process must not contain start or end events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bpmn_io._bpmnlint_utils import is_
from bpmn_io.lint.rules.helper import annotate_rule, prop_list

if TYPE_CHECKING:
    from bpmn_io.lint.test_rule import Reporter
    from bpmn_io.moddle.base import ModdleElement

__all__ = ["factory"]


def factory(_config: object = None) -> dict[str, Any]:
    """Create the ``ad-hoc-sub-process`` rule (upstream rule factory)."""

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if not is_(node, "bpmn:AdHocSubProcess"):
            return

        for flow_element in prop_list(node, "flowElements"):
            if is_(flow_element, "bpmn:StartEvent"):
                reporter.report(
                    flow_element.get("id"),
                    "A <Start Event> is not allowed in <Ad Hoc Sub Process>",
                )

            if is_(flow_element, "bpmn:EndEvent"):
                reporter.report(
                    flow_element.get("id"),
                    "An <End Event> is not allowed in <Ad Hoc Sub Process>",
                )

    return annotate_rule("ad-hoc-sub-process", {"check": check})
