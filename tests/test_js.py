"""Tests for the JS-semantics helpers (original tests for EVOL D5, not upstream cases)."""

from __future__ import annotations

import copy
import math

import pytest

from bpmn_io._js import (
    UNDEFINED,
    OrderedSet,
    UndefinedType,
    is_truthy,
    json_stringify,
    math_round,
    number_to_string,
    parse_float,
    parse_int,
)


def test_undefined_is_singleton_falsy_and_copy_stable() -> None:
    assert isinstance(UNDEFINED, UndefinedType)
    assert repr(UNDEFINED) == "undefined"
    assert not UNDEFINED
    assert copy.copy(UNDEFINED) is UNDEFINED
    assert copy.deepcopy(UNDEFINED, {}) is UNDEFINED


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (False, False),
        (True, True),
        (0, False),
        (1, True),
        (0.0, False),
        (-0.0, False),
        (2.5, True),
        ("", False),
        ("x", True),
        (None, False),
        (UNDEFINED, False),
        (math.nan, False),
        (math.inf, True),
        ([], True),  # JS: empty containers are truthy
        ({}, True),
        ({"a": 1}, True),
        (object(), True),
    ],
)
def test_is_truthy(value: object, expected: object) -> None:
    assert is_truthy(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(2.4, 2), (2.5, 3), (2.6, 3), (-2.4, -2), (-2.5, -2), (-2.6, -3), (0.0, 0)],
)
def test_math_round_half_up(value: float, expected: int) -> None:
    assert math_round(value) == expected


def test_math_round_non_finite_passes_through() -> None:
    assert math.isnan(math_round(math.nan))
    assert math_round(math.inf) == math.inf
    assert math_round(-math.inf) == -math.inf


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (100, "100"),
        (-7, "-7"),
        (100.0, "100"),
        (-0.0, "0"),
        (0.5, "0.5"),
        (1e21, "1e+21"),
        (1e-7, "1e-7"),
        (math.nan, "NaN"),
        (math.inf, "Infinity"),
        (-math.inf, "-Infinity"),
    ],
)
def test_number_to_string(value: float, expected: str) -> None:
    assert number_to_string(value) == expected


def test_number_to_string_rejects_bool() -> None:
    flag = True
    with pytest.raises(TypeError):
        number_to_string(flag)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("123", 123),
        ("  12  ", 12),
        ("123abc", 123),
        ("+7", 7),
        ("-7", -7),
        ("0x10", 16),
        ("0Xff", 255),
        ("08", 8),
        ("", math.nan),
        ("abc", math.nan),
        ("0x", math.nan),
    ],
)
def test_parse_int(text: str, expected: float) -> None:
    actual = parse_int(text)
    if isinstance(expected, float) and math.isnan(expected):
        assert isinstance(actual, float)
        assert math.isnan(actual)
    else:
        assert actual == expected


@pytest.mark.parametrize(
    ("text", "radix", "expected"),
    [("10", 16, 16), ("0x10", 16, 16), ("0x10", 10, 0), ("11", 2, 3), ("ff", 16, 255)],
)
def test_parse_int_explicit_radix(text: str, radix: int, expected: int) -> None:
    assert parse_int(text, radix) == expected


@pytest.mark.parametrize("radix", [1, 37])
def test_parse_int_bad_radix_is_nan(radix: int) -> None:
    actual = parse_int("10", radix)
    assert isinstance(actual, float)
    assert math.isnan(actual)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3.14", 3.14),
        ("  3.14abc", 3.14),
        ("-0.5", -0.5),
        (".5", 0.5),
        ("5.", 5.0),
        ("1e3", 1000.0),
        ("Infinity", math.inf),
        ("-Infinity", -math.inf),
        ("infinity", math.nan),
        ("", math.nan),
        ("abc", math.nan),
    ],
)
def test_parse_float(text: str, expected: float) -> None:
    actual = parse_float(text)
    if math.isnan(expected):
        assert math.isnan(actual)
    else:
        assert actual == expected


def test_ordered_set_keeps_insertion_order() -> None:
    seen: OrderedSet[str] = OrderedSet(["b", "a", "b", "c"])
    assert list(seen) == ["b", "a", "c"]
    assert len(seen) == 3
    assert "a" in seen
    assert "z" not in seen
    seen.discard("a")
    assert list(seen) == ["b", "c"]
    seen.discard("missing")
    seen.add("a")
    assert list(seen) == ["b", "c", "a"]
    assert repr(seen) == "OrderedSet(['b', 'c', 'a'])"


def test_json_stringify_plain_values() -> None:
    assert json_stringify(None) == "null"
    truthy = True
    falsy = False
    assert json_stringify(truthy) == "true"
    assert json_stringify(falsy) == "false"
    assert json_stringify(100) == "100"
    assert json_stringify(100.0) == "100"
    assert json_stringify(-0.0) == "0"
    assert json_stringify(math.nan) == "null"
    assert json_stringify('héllo "x"') == '"héllo \\"x\\""'
    assert json_stringify({"b": 1, "a": [1, UNDEFINED, None]}) == '{"b":1,"a":[1,null,null]}'
    assert json_stringify({"skip": UNDEFINED, "keep": 1}) == '{"keep":1}'


def test_json_stringify_deep_nesting_is_iterative() -> None:
    value: object = 1
    for _ in range(5000):
        value = [value]
    text = json_stringify(value)
    assert text == "[" * 5000 + "1" + "]" * 5000


def test_json_stringify_rejects_bare_undefined_and_foreign_types() -> None:
    with pytest.raises(ValueError, match="undefined"):
        json_stringify(UNDEFINED)
    with pytest.raises(TypeError, match="JSON-like"):
        json_stringify(object())
