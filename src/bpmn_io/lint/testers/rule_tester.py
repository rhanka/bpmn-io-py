# Transposed from bpmn-io/bpmnlint@de71146 lib/testers/rule-tester.js (MIT).
"""Rule tester, transposed from ``lib/testers/rule-tester.js``.

``verify`` is pytest-driven: it executes each case synchronously and raises
``AssertionError`` on the first mismatch, so a Python test function claiming
one upstream case simply calls it (or the per-case helper in the rules
test-suite) with that case. ``expect_equal`` compares through the same
JSON projection as upstream (moddle elements project to their id, or to
their ``$type`` when they have no id).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

from bpmn_io._js import UNDEFINED
from bpmn_io.lint.linter import Linter

if TYPE_CHECKING:
    from collections.abc import Callable

    from bpmn_io.moddle.base import ModdleElement

__all__ = ["expect_equal", "get_title", "replacer", "verify"]


class _RuleResolver:
    """Resolver returning the single rule under test (upstream ``createResolver``)."""

    def __init__(self, rule_factory: Callable[..., dict[str, Any]]) -> None:
        self._rule_factory = rule_factory

    def resolve_rule(self, pkg: str, rule_name: str) -> Callable[..., dict[str, Any]]:  # noqa: ARG002
        return self._rule_factory

    def resolve_config(self, pkg: str, config_name: str) -> dict[str, Any]:  # noqa: ARG002
        msg = "not implemented"
        raise ValueError(msg)


def _is_element(value: object) -> bool:
    """Whether ``value`` is a moddle element (carries ``$type``/``$descriptor``)."""
    return hasattr(value, "type_") and hasattr(value, "descriptor_")


def replacer(_key: str, value: object) -> object:
    """JSON replacer projecting moddle elements to id or ``$type`` (upstream ``replacer``)."""
    if not value:
        return value

    if _is_element(value):
        element = cast("ModdleElement", value)
        descriptor = element.descriptor_
        id_property = getattr(descriptor, "id_property", None)

        if id_property is not None:
            element_id = element.get(id_property.name)

            if element_id:
                return element_id
            return element.type_

        return element.type_

    return value


def _project(value: object) -> object:
    """Project ``value`` to JSON-comparable data through :func:`replacer`."""
    projected = replacer("", value)

    if projected is not value:
        return projected

    if isinstance(value, dict):
        return {key: _project(item) for key, item in value.items() if item is not UNDEFINED}

    if isinstance(value, (list, tuple)):
        return [_project(item) if item is not UNDEFINED else None for item in value]

    if value is UNDEFINED:
        return None

    return value


def expect_equal(a: object, b: object) -> None:
    """Raise ``AssertionError`` unless ``a`` and ``b`` project to equal JSON (upstream)."""
    a_json = json.dumps(_project(a), indent=2, ensure_ascii=False)
    b_json = json.dumps(_project(b), indent=2, ensure_ascii=False)

    if a_json != b_json:
        msg = f"expected {a_json} to equal {b_json}"
        raise AssertionError(msg)


def get_title(idx: int, name: str | None = None) -> str:
    """Return the RuleTester case title (upstream ``getTitle``)."""
    return f"test case #{idx + 1}" + (f" {name}" if name else "")


def _root_of(moddle_element: object) -> ModdleElement:
    """Unwrap a ``read_moddle`` result dict to its root element, when needed."""
    if isinstance(moddle_element, dict) and "root" in moddle_element:
        return cast("ModdleElement", moddle_element["root"])
    return cast("ModdleElement", moddle_element)


def verify(
    rule_name: str,
    rule_factory: Callable[..., dict[str, Any]],
    test_cases: dict[str, list[dict[str, Any]]],
) -> None:
    """Verify ``rule_factory`` against valid/invalid cases (upstream ``verify``)."""
    linter = Linter(resolver=_RuleResolver(rule_factory))

    def _create_linter_config(config: object = None) -> dict[str, Any]:
        return {
            "rules": {rule_name: [2, config if config is not None else {}]},
        }

    for case in test_cases.get("valid", []):
        config = case.get("config") or {}
        root = _root_of(
            case["moddleElement"] if "moddleElement" in case else case["moddle_element"]
        )

        lint_results = linter.lint(root, _create_linter_config(config))

        expect_equal(lint_results, {})

    for case in test_cases.get("invalid", []):
        config = case.get("config") or {}
        root = _root_of(
            case["moddleElement"] if "moddleElement" in case else case["moddle_element"]
        )
        report = case["report"]

        rule = linter.resolve_rule(rule_name, config)
        meta = rule.get("meta", UNDEFINED)

        reports = report if isinstance(report, list) else [report]

        expected_results = [
            {
                **single_report,
                "meta": meta,
                "category": "error",
            }
            for single_report in reports
        ]

        expected_lint_results = {
            rule_name: expected_results,
        }

        lint_results = linter.lint(root, _create_linter_config(config))

        expect_equal(lint_results, expected_lint_results)
