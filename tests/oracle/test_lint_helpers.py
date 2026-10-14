"""Oracle differentials for the Lot 12 lint helpers (moddle-utils, bpmnlint-utils)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from bpmn_io._bpmnlint_utils import is_, is_any
from bpmn_io._moddle_utils import path_concat, path_equals, path_parse, path_stringify

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.oracle


class _Node:
    def instance_of(self, type: str) -> bool:  # noqa: A002 - upstream property name
        return type == "bpmn:Foo"


_NODE_JSON: dict[str, Any] = {"$instanceOf": {"$fn": "(type) => type === 'bpmn:Foo'"}}


def test_bpmnlint_utils_differential(oracle_call: Callable[[dict[str, object]], object]) -> None:
    node = _Node()
    for type_name in ["Foo", "bpmn:Foo", "Baz"]:
        expected = oracle_call(
            {
                "op": "call",
                "package": "bpmnlint-utils",
                "path": "is",
                "args": [_NODE_JSON, type_name],
            },
        )
        assert is_(node, type_name) == expected
    for types in [["Foo", "bpmn:Bar"], ["bpmn:Foo"], ["Baz", "bpmn:Blub"]]:
        expected = oracle_call(
            {
                "op": "call",
                "package": "bpmnlint-utils",
                "path": "isAny",
                "args": [_NODE_JSON, types],
            },
        )
        assert is_any(node, types) == expected


def test_moddle_utils_path_concat_differential(
    oracle_call: Callable[[dict[str, object]], object],
) -> None:
    cases: list[list[Any]] = [
        [["foo"], ["bar", "baz"]],
        [["foo"], [0, "bar"], [1, "baz"]],
        [["foo"], 0, "bar"],
        [None, ["bar"]],
    ]
    for args in cases:
        expected = oracle_call(
            {"op": "call", "package": "@bpmn-io/moddle-utils", "path": "pathConcat", "args": args},
        )
        assert path_concat(*args) == expected


def test_moddle_utils_path_equals_differential(
    oracle_call: Callable[[dict[str, object]], object],
) -> None:
    cases: list[list[Any]] = [
        ["foo.bar.0.baz", "foo.bar.0.baz"],
        ["foo.bar.0.baz", "foo.bar.baz"],
        ["foo.bar.0.baz", ["foo", "bar", 0, "baz"]],
        [["foo", "bar", 0, "baz"], ["foo", "bar", "baz"]],
        [None, ["foo"]],
    ]
    for args in cases:
        expected = oracle_call(
            {"op": "call", "package": "@bpmn-io/moddle-utils", "path": "pathEquals", "args": args},
        )
        assert path_equals(args[0], args[1]) == expected


def test_moddle_utils_path_parse_stringify_differential(
    oracle_call: Callable[[dict[str, object]], object],
) -> None:
    for text in ["rootElements.0.flowElements.0.extensionElements.values.0.type", "a.b", "x.10.y"]:
        expected = oracle_call(
            {"op": "call", "package": "@bpmn-io/moddle-utils", "path": "pathParse", "args": [text]},
        )
        assert path_parse(text) == expected
        parsed = path_parse(text)
        assert parsed is not None
        expected_str = oracle_call(
            {
                "op": "call",
                "package": "@bpmn-io/moddle-utils",
                "path": "pathStringify",
                "args": [parsed],
            },
        )
        assert path_stringify(parsed) == expected_str
