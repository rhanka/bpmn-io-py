# Transposed from bpmn-io/bpmnlint@de71146 rules/helper.js (MIT).
"""Shared rule helpers, transposed from ``rules/helper.js``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from bpmn_io._bpmnlint_utils import is_
from bpmn_io._js import UNDEFINED, is_truthy

if TYPE_CHECKING:
    from collections.abc import Callable

    from bpmn_io.lint.test_rule import Reporter
    from bpmn_io.moddle.base import ModdleElement

__all__ = [
    "annotate_rule",
    "check_discouraged_node_type",
    "find_parent",
    "is_in_executable_process",
]

DOCUMENTATION_BASE_URL = "https://github.com/bpmn-io/bpmnlint/blob/main/docs/rules"


def check_discouraged_node_type(
    type: str,  # noqa: A002 - upstream parameter name
    rule_name: str,
) -> Callable[..., dict[str, Any]]:
    """Create a checker that disallows the given element type (upstream factory)."""

    def factory(_config: object = None) -> dict[str, Any]:
        def check(node: ModdleElement, reporter: Reporter) -> None:
            if is_(node, type):
                reporter.report(node.get("id"), f"Element type <{type}> is discouraged")

        return annotate_rule(rule_name, {"check": check})

    return factory


def find_parent(node: ModdleElement | None, type: str) -> ModdleElement | None:  # noqa: A002
    """Find a parent of ``node`` of the given ``type`` (upstream ``findParent``)."""
    if node is None:
        return None

    current: ModdleElement = node
    while True:
        parent = current.parent_

        if not is_truthy(parent):
            return current

        if is_(parent, type):
            return parent  # type: ignore[return-value]

        current = parent  # type: ignore[assignment]


def is_in_executable_process(node: ModdleElement) -> bool:
    """Whether ``node`` is inside an executable process (upstream helper)."""
    process = find_parent(node, "bpmn:Process")

    if process is None:
        return False

    return is_truthy(process.get("isExecutable"))


def annotate_rule(rule_name: str, options: dict[str, Any]) -> dict[str, Any]:
    """Annotate a rule with core information such as the documentation URL."""
    meta: dict[str, Any] = dict(options.get("meta") or {})
    documentation: dict[str, Any] = dict(meta.pop("documentation", {}) or {})
    rest_options = {key: value for key, value in options.items() if key != "meta"}

    documentation_url = f"{DOCUMENTATION_BASE_URL}/{rule_name}.md"

    return {
        "meta": {
            "documentation": {
                "url": documentation_url,
                **documentation,
            },
            **meta,
        },
        **rest_options,
    }


def prop(node: ModdleElement, name: str) -> Any:  # noqa: ANN401 - JS-dynamic property access
    """JS property access: the named property, with ``undefined`` mapped to ``None``."""
    value = node.get(name)
    return None if value is UNDEFINED else value


def prop_list(node: ModdleElement, name: str) -> list[ModdleElement]:
    """JS ``node.<name> || []`` for collection properties."""
    value = node.get(name)
    if value is UNDEFINED or value is None:
        return []
    return cast("list[ModdleElement]", value)
