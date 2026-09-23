"""Tests for the ported matchers (original tests for the Lot 0 transposition)."""

from __future__ import annotations

import math

import pytest

from bpmn_io._js import UNDEFINED, json_stringify
from tests._matchers import json_equal, to_canonical


class _FakeElement:
    """Stand-in for a Lot 4 moddle element behind the ``to_canonical_dict`` protocol."""

    def __init__(self, payload: object) -> None:
        self._payload = payload

    def to_canonical_dict(self) -> object:
        return self._payload


def test_equal_plain_values() -> None:
    assert json_equal({"b": 1, "a": [1, None, True]}, {"b": 1, "a": [1, None, True]})
    assert json_equal("x", "x")
    assert json_equal(100.0, 100)


def test_insertion_order_matters() -> None:
    assert not json_equal({"a": 1, "b": 2}, {"b": 2, "a": 1})


def test_type_mismatch_is_unequal() -> None:
    falsy = False
    assert not json_equal(1, "1")
    assert not json_equal([1], {"0": 1})
    assert not json_equal(None, falsy)


def test_undefined_matches_json_semantics() -> None:
    assert json_equal({"skip": UNDEFINED, "keep": 1}, {"keep": 1})
    assert json_equal([UNDEFINED], [None])
    assert json_equal(math.nan, None)


def test_protocol_objects_compare_by_projection() -> None:
    element = _FakeElement({"$type": "bpmn:Task", "name": "Review"})
    assert json_equal(element, {"$type": "bpmn:Task", "name": "Review"})
    assert not json_equal(element, {"$type": "bpmn:Task", "name": "Other"})
    nested = _FakeElement({"child": _FakeElement([1, 2])})
    assert json_equal(nested, {"child": [1, 2]})


def test_to_canonical_rejects_foreign_types() -> None:
    with pytest.raises(TypeError, match="JSON-like"):
        to_canonical(object())


def test_to_canonical_rejects_reference_cycle() -> None:
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    with pytest.raises(ValueError, match="reference cycle"):
        to_canonical(cyclic)


def test_to_canonical_deep_nesting_is_iterative() -> None:
    value: object = 1
    for _ in range(5000):
        value = [value]
    assert json_equal(value, to_canonical(value))
    assert json_stringify(to_canonical(value)) == json_stringify(value)
