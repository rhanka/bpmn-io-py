# Transposed from bpmn-io/bpmnlint@de71146 rules/global.js (MIT).
"""Rule: global elements (Error, Escalation, Message, Signal) must be named, used, unique."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from bpmn_io._bpmnlint_utils import is_, is_any
from bpmn_io._js import UNDEFINED, js_filter, strict_get
from bpmn_io.lint.rules.helper import annotate_rule, prop, prop_list

if TYPE_CHECKING:
    from bpmn_io.lint.test_rule import Reporter
    from bpmn_io.moddle.base import ModdleElement

__all__ = ["factory"]


def factory(_config: object = None) -> dict[str, Any]:
    """Create the ``global`` rule (upstream rule factory)."""

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if not is_(node, "bpmn:Definitions"):
            return

        root_elements = _get_root_elements(node)
        referencing_elements = _get_referencing_elements(node)

        for root_element in root_elements:
            if not _has_name(root_element):
                reporter.report(root_element.get("id"), "Element is missing name")

            if not _is_referenced(root_element, referencing_elements):
                reporter.report(root_element.get("id"), "Element is unused")

            if not _is_unique(root_element, root_elements):
                reporter.report(root_element.get("id"), "Element name is not unique")

    return annotate_rule("global", {"check": check})


def _get_root_elements(definitions: ModdleElement) -> list[ModdleElement]:
    # Upstream `definitions.rootElements.filter(...)`: no `|| []` fallback,
    # so an unset collection raises the JS TypeError (reported as rule-error).
    return js_filter(
        strict_get(definitions, "rootElements"),
        lambda element: is_any(
            element, ["bpmn:Error", "bpmn:Escalation", "bpmn:Message", "bpmn:Signal"]
        ),
    )


def _get_referencing_elements(definitions: ModdleElement) -> list[ModdleElement]:
    referencing_elements: list[ModdleElement] = []

    # Iterative depth-first walk in upstream (recursive) order.
    def _children(element: ModdleElement) -> list[ModdleElement]:
        children: list[ModdleElement] = []
        if is_(element, "bpmn:Definitions"):
            children.extend(prop_list(element, "rootElements"))
        if is_(element, "bpmn:FlowElementsContainer"):
            children.extend(prop_list(element, "flowElements"))
        if is_(element, "bpmn:Collaboration"):
            children.extend(prop_list(element, "messageFlows"))
        return children

    walk_stack: list[ModdleElement] = [definitions]
    visited: list[ModdleElement] = []
    while walk_stack:
        element = walk_stack.pop()
        visited.append(element)
        for child in reversed(_children(element)):
            walk_stack.append(child)  # noqa: PERF402 - explicit-stack DFS walk

    for element in visited:
        if is_(element, "bpmn:Event"):
            referencing_elements.extend(prop_list(element, "eventDefinitions"))
        if is_any(element, ["bpmn:MessageFlow", "bpmn:ReceiveTask", "bpmn:SendTask"]):
            referencing_elements.append(element)

    return referencing_elements


def _has_name(element: ModdleElement) -> bool:
    name = prop(element, "name")
    if name is None:
        return True
    return cast("str", name).strip() != ""


def _referenced_id(element: ModdleElement, reference_name: str) -> object:
    reference = prop(element, reference_name)
    if reference is None:
        return UNDEFINED
    return cast("object", reference.get("id"))


def _is_referenced(root_element: ModdleElement, referencing_elements: list[ModdleElement]) -> bool:
    root_id = root_element.get("id")

    if is_(root_element, "bpmn:Error"):
        return any(
            is_(element, "bpmn:ErrorEventDefinition")
            and root_id == _referenced_id(element, "errorRef")
            for element in referencing_elements
        )

    if is_(root_element, "bpmn:Escalation"):
        return any(
            is_(element, "bpmn:EscalationEventDefinition")
            and root_id == _referenced_id(element, "escalationRef")
            for element in referencing_elements
        )

    if is_(root_element, "bpmn:Message"):
        return any(
            is_any(
                element,
                [
                    "bpmn:MessageEventDefinition",
                    "bpmn:MessageFlow",
                    "bpmn:ReceiveTask",
                    "bpmn:SendTask",
                ],
            )
            and root_id == _referenced_id(element, "messageRef")
            for element in referencing_elements
        )

    if is_(root_element, "bpmn:Signal"):
        return any(
            is_(element, "bpmn:SignalEventDefinition")
            and root_id == _referenced_id(element, "signalRef")
            for element in referencing_elements
        )

    return False


def _is_unique(root_element: ModdleElement, root_elements: list[ModdleElement]) -> bool:
    name = prop(root_element, "name")
    return (
        len(
            [
                other
                for other in root_elements
                if is_(other, root_element.type_) and name == prop(other, "name")
            ],
        )
        == 1
    )
