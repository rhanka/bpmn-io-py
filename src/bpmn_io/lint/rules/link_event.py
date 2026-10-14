# Transposed from bpmn-io/bpmnlint@de71146 rules/link-event.js (MIT).
"""Rule: link events must be paired (throw/catch) per scope, with unique names."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from bpmn_io._bpmnlint_utils import is_
from bpmn_io.lint.rules.helper import annotate_rule, prop, prop_list

if TYPE_CHECKING:
    from bpmn_io.lint.test_rule import Reporter
    from bpmn_io.moddle.base import ModdleElement

__all__ = ["factory"]


def factory(_config: object = None) -> dict[str, Any]:
    """Create the ``link-event`` rule (upstream rule factory)."""

    def check(node: ModdleElement, reporter: Reporter) -> None:
        if not is_(node, "bpmn:FlowElementsContainer"):
            return

        links = [element for element in prop_list(node, "flowElements") if _is_link_event(element)]

        for link in links:
            if not _get_link_name(link):
                reporter.report(link.get("id"), "Link event is missing link name")

        for name, events in _group_by(links, _get_link_name).items():
            _check_link_scope(name, events, reporter)

    return annotate_rule("link-event", {"check": check})


def _group_by(
    links: list[ModdleElement],
    key_fn: Callable[[ModdleElement], object],
) -> dict[str, list[ModdleElement]]:
    """Upstream ``groupBy`` (min-dash): a falsy discriminator becomes ``"_"``."""
    grouped: dict[str, list[ModdleElement]] = {}
    for link in links:
        key = key_fn(link)
        js_key = str(key) if key else "_"
        grouped.setdefault(js_key, []).append(link)
    return grouped


def _is_link_event(node: ModdleElement) -> bool:
    if not is_(node, "bpmn:Event"):
        return False

    return any(
        is_(definition, "bpmn:LinkEventDefinition")
        for definition in prop_list(node, "eventDefinitions")
    )


def _get_link_name(link_event: ModdleElement) -> object:
    for definition in prop_list(link_event, "eventDefinitions"):
        if is_(definition, "bpmn:LinkEventDefinition"):
            return prop(definition, "name")
    return None


def _is_throw_event(node: ModdleElement) -> bool:
    return is_(node, "bpmn:ThrowEvent")


def _is_catch_event(node: ModdleElement) -> bool:
    return is_(node, "bpmn:CatchEvent")


def _check_link_scope(
    name: str,
    events: list[ModdleElement],
    reporter: Reporter,
) -> None:
    """Report missing/duplicate pairings for one link name within a scope."""
    # ignore unnamed (validated earlier)
    if not name:
        return

    # missing catch or throw event
    if len(events) == 1:
        event = events[0]

        kind = "catch" if _is_throw_event(event) else "throw"
        reporter.report(
            event.get("id"),
            f"Link {kind} event with link name <{name}> missing in scope",
        )
        return

    catch_events = [event for event in events if _is_catch_event(event)]
    if len(catch_events) > 1:
        for event in catch_events:
            reporter.report(
                event.get("id"),
                f"Duplicate link catch event with link name <{name}> in scope",
            )
    elif len(catch_events) == 0:
        # all events in scope are throw events
        for event in events:
            reporter.report(
                event.get("id"),
                f"Link catch event with link name <{name}> missing in scope",
            )
