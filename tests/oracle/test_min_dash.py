"""Differential min-dash tests: Python port vs the pinned Node package (Lot 2).

Each transposed helper runs against ``tests/oracle/run.mjs`` (``op=call``,
``package=min-dash``) over a table of inputs; callbacks cross the JSON boundary as
``{"$fn": "<source>"}`` and ``undefined`` as ``{"$undefined": true}`` (see run.mjs).
``UNDEFINED`` normalizes to ``None`` before comparison (``undefined`` → ``null``).

``bind`` is excluded: rebinding ``this`` has no Python equivalent; it is covered by
the ported ``fn.spec.js`` cases in ``tests/min_dash/test_fn.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

import bpmn_io._min_dash as min_dash
from bpmn_io._js import UNDEFINED

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.oracle


def _fn(source: str) -> dict[str, str]:
    """Encode a JS callback for the oracle runner."""
    return {"$fn": source}


UNDEF = {"$undefined": True}


def _norm(value: object) -> object:
    """Map UNDEFINED to None so JSON nulls compare equal (recursively)."""
    if value is UNDEFINED:
        return None
    if isinstance(value, (list, tuple)):
        return [_norm(item) for item in value]
    if isinstance(value, dict):
        return {key: _norm(item) for key, item in value.items()}
    return value


def _check(
    oracle_call: Callable[[dict[str, object]], object],
    path: str,
    call_py: Callable[..., object],
    py_args: tuple[Any, ...],
    js_args: list[Any],
) -> None:
    """Assert the Python helper and the oracle agree on one input row."""
    expected = oracle_call({"op": "call", "package": "min-dash", "path": path, "args": js_args})
    assert _norm(call_py(*py_args)) == expected


def test_find_table(oracle_call: Callable[[dict[str, object]], object]) -> None:
    rows: list[tuple[Any, Any, Any]] = [
        (["A", "B", "C"], lambda el: el == "B", _fn("(el) => el === 'B'")),
        (["A", "B", "C"], lambda _, idx: idx == 2, _fn("(el, idx) => idx === 2")),
        (
            {"foo": "FOO", "bar": "BAR"},
            lambda _, key: key == "foo",
            _fn("(el, key) => key === 'foo'"),
        ),
        (None, lambda _: True, _fn("() => true")),
        ([0, "", None], 0, 0),
        ([1, 2], 9, 9),
        ({"a": 0, "b": "", "c": None}, None, None),
    ]
    for collection, matcher, js_matcher in rows:
        _check(oracle_call, "find", min_dash.find, (collection, matcher), [collection, js_matcher])


def test_find_index_table(oracle_call: Callable[[dict[str, object]], object]) -> None:
    rows: list[tuple[Any, Any, Any]] = [
        (["A", "B", "C"], lambda el: el == "B", _fn("(el) => el === 'B'")),
        ({"foo": "FOO", "bar": "BAR"}, lambda el: el == "BAR", _fn("(el) => el === 'BAR'")),
        (None, lambda _: True, _fn("() => true")),
        ([1], lambda el: el == 9, _fn("(el) => el === 9")),
        ({"a": 1}, lambda el: el == 9, _fn("(el) => el === 9")),
        ({"a": 0, "b": "", "c": None}, None, None),
    ]
    for collection, matcher, js_matcher in rows:
        _check(
            oracle_call,
            "findIndex",
            min_dash.find_index,
            (collection, matcher),
            [collection, js_matcher],
        )


def test_filter_table(oracle_call: Callable[[dict[str, object]], object]) -> None:
    rows: list[tuple[Any, Any, Any]] = [
        ([50, 200, 500], lambda el: el > 100, _fn("(el) => el > 100")),
        ([50, 200, 500], lambda _, idx: idx < 2, _fn("(el, idx) => idx < 2")),
        ({"a": 1, "b": 2, "c": 3}, lambda el: el > 1, _fn("(el) => el > 1")),
        (None, lambda _: True, _fn("() => true")),
    ]
    for collection, matcher, js_matcher in rows:
        _check(
            oracle_call, "filter", min_dash.filter, (collection, matcher), [collection, js_matcher]
        )


def test_for_each_table(oracle_call: Callable[[dict[str, object]], object]) -> None:
    def stop_at_two(el: object, _idx: object) -> bool | None:
        return False if el == 2 else None

    rows: list[tuple[Any, Any, Any]] = [
        ([1, 2, 3], stop_at_two, _fn("(el) => (el === 2 ? false : undefined)")),
        ([1, 2, 3], lambda _: None, _fn("() => undefined")),
        (None, lambda _: False, _fn("() => false")),
    ]
    for collection, iterator, js_iterator in rows:
        _check(
            oracle_call,
            "forEach",
            min_dash.for_each,
            (collection, iterator),
            [collection, js_iterator],
        )


def test_map_table(oracle_call: Callable[[dict[str, object]], object]) -> None:
    rows: list[tuple[Any, Any, Any]] = [
        ([1, 2, 3], lambda val: val + 3, _fn("(val) => val + 3")),
        ({"a": 1}, lambda val: val + 3, _fn("(val) => val + 3")),
        (None, lambda _: False, _fn("() => false")),
    ]
    for collection, func, js_func in rows:
        _check(oracle_call, "map", min_dash.map, (collection, func), [collection, js_func])


def test_assign_table(oracle_call: Callable[[dict[str, object]], object]) -> None:
    # No `__proto__` row: JS parks it on the prototype (no own key) while the port
    # keeps a plain dict key; both no-pollution properties are unit-tested instead
    # (upstream object.spec.js, tests/min_dash/test_object.py).
    rows: list[tuple[dict[str, Any], list[Any]]] = [
        ({}, [{"a": 1}, {"b": 2}]),
        ({"bar": "Bar"}, [None, UNDEF, False, 0, {"foo": "Foo"}]),
    ]
    for target, sources in rows:
        py_sources = [UNDEFINED if src is UNDEF else src for src in sources]
        _check(
            oracle_call, "assign", min_dash.assign, (dict(target), *py_sources), [target, *sources]
        )


def test_pick_table(oracle_call: Callable[[dict[str, object]], object]) -> None:
    rows: list[tuple[dict[str, Any], list[str]]] = [
        ({"a": 1, "b": False, "c": None}, ["a", "c", "d"]),
        ({"a": 1}, ["a", "z"]),
    ]
    for target, properties in rows:
        _check(oracle_call, "pick", min_dash.pick, (target, properties), [target, properties])


def test_set_table(oracle_call: Callable[[dict[str, object]], object]) -> None:
    rows: list[tuple[Any, list[Any], Any]] = [
        ({}, ["a"], True),
        ({}, [0], "A"),
        ([0, 1, 2], [1], "A"),
        ([0, 1, 2], ["1"], "A"),
        ({"a": False}, ["a"], UNDEF),
        ({}, ["a", "b", "c"], "C"),
        ({"a": None}, ["a", "b", "c"], "C"),
        ({}, ["a", 1, 2], "C"),
        ({"a": [{"b": "FOO"}]}, ["a", 0, "b"], "BAR"),
    ]
    for target, path, value in rows:
        py_value = UNDEFINED if value is UNDEF else value
        _check(oracle_call, "set", min_dash.set, (target, path, py_value), [target, path, value])


def test_has_table(oracle_call: Callable[[dict[str, object]], object]) -> None:
    rows: list[tuple[Any, str]] = [
        ({"a": 1}, "a"),
        ({"a": 1}, "c"),
        ([1, 2, 3], "1"),
        ([1, 2, 3], "5"),
        ([1], "length"),
        ("", "length"),
        (None, "1"),
    ]
    for target, key in rows:
        _check(oracle_call, "has", min_dash.has, (target, key), [target, key])


def test_is_table(oracle_call: Callable[[dict[str, object]], object]) -> None:
    rows: list[tuple[str, Any, Any]] = [
        ("isString", "a", "a"),
        ("isString", 0, 0),
        ("isObject", {}, {}),
        ("isObject", [], []),
        ("isObject", None, None),
        ("isFunction", lambda: None, _fn("() => {}")),
        ("isFunction", {}, {}),
    ]
    funcs = {"isString": min_dash.is_string, "isObject": min_dash.is_object}
    for path, py_value, js_value in rows:
        _check(oracle_call, path, funcs.get(path, min_dash.is_function), (py_value,), [js_value])
