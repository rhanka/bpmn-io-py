# Transposed from bpmn-io/bpmnlint@de71146 rules/no-gateway-join-fork.js (MIT).
"""Rule: a gateway must not fork and join at the same time."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bpmn_io._bpmnlint_utils import is_
from bpmn_io.lint.rules.helper import annotate_rule, prop_list

if TYPE_CHECKING:
    from bpmn_io.lint.test_rule import Reporter
    from bpmn_io.moddle.base import ModdleElement

__all__ = ["factory"]


def factory(_config: object = None) -> dict[str, Any]:
    """Create the ``no-gateway-join-fork`` rule (upstream rule factory)."""

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if not is_(node, "bpmn:Gateway"):
            return

        incoming = prop_list(node, "incoming")
        outgoing = prop_list(node, "outgoing")

        if len(incoming) > 1 and len(outgoing) > 1:
            reporter.report(node.get("id"), "Gateway forks and joins")

    return annotate_rule("no-gateway-join-fork", {"check": check})
