# Transposed from bpmn-io/bpmnlint@de71146 rules/conditional-event.js (MIT).
"""Rule: a conditional event must specify a condition."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bpmn_io._bpmnlint_utils import is_
from bpmn_io._js import is_truthy
from bpmn_io.lint.rules.helper import annotate_rule, is_in_executable_process, prop, prop_list

if TYPE_CHECKING:
    from bpmn_io.lint.test_rule import Reporter
    from bpmn_io.moddle.base import ModdleElement

__all__ = ["factory"]


def factory(_config: object = None) -> dict[str, Any]:
    """Create the ``conditional-event`` rule (upstream rule factory)."""

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if not is_in_executable_process(node):
            return

        event_definition = _get_conditional_event_definition(node)

        if not event_definition:
            return

        if not _has_condition(event_definition):
            reporter.report(
                node.get("id"), "Conditional event is missing a condition", ["condition"]
            )

    return annotate_rule("conditional-event", {"check": check})


def _get_conditional_event_definition(node: ModdleElement) -> ModdleElement | None:
    if not is_(node, "bpmn:Event"):
        return None

    for definition in prop_list(node, "eventDefinitions"):
        if is_(definition, "bpmn:ConditionalEventDefinition"):
            return definition
    return None


def _has_condition(event_definition: ModdleElement) -> bool:
    condition = prop(event_definition, "condition")
    if condition is None:
        return False
    return bool(is_truthy(prop(condition, "body")))
