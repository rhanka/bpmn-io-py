"""Ported min-dash collection cases (Lot 2).

Claims every ``min-dash/test/collection.spec.js`` title for the transposed helpers
(``find``, ``find_index``, ``filter``, ``for_each``, ``map``); titles that only cover
helpers unused by the ported libraries are claimed N-A with a reason (see
``docs/naming.md`` § min-dash). Shared titles (``should work on Array`` and the like)
are claimed once, covering every helper the upstream case exercises.
"""

from __future__ import annotations

import pytest

import bpmn_io._min_dash as min_dash
from bpmn_io._js import UNDEFINED


@pytest.mark.upstream("min-dash/test/collection.spec.js", "should work on Array")
def test_array_cases() -> None:
    arr = ["A", "B", "C"]
    assert min_dash.find(arr, lambda el: el == "B") == "B"
    assert min_dash.find(arr, lambda _, idx: idx == 2) == "C"
    assert min_dash.find_index(arr, lambda el: el == "B") == 1
    assert min_dash.find_index(arr, lambda _, idx: idx == 2) == 2
    assert min_dash.filter([50, 200, 500], lambda el: el > 100) == [200, 500]
    assert min_dash.filter([50, 200, 500], lambda _, idx: idx < 2) == [50, 200]
    seen = []
    min_dash.for_each([{}, {}, {}], lambda el, idx: seen.append((el, idx)))
    assert [idx for _, idx in seen] == [0, 1, 2]
    assert min_dash.map([1, 2, 3], lambda val: val + 3) == [4, 5, 6]
    # N-A in this title: without/reduce/every/some/values/keys/groupBy (unused downstream).


@pytest.mark.upstream("min-dash/test/collection.spec.js", "should work on Object")
def test_object_cases() -> None:
    obj = {"foo": "FOO", "bar": "BAR"}
    assert min_dash.find(obj, lambda el: el == "BAR") == "BAR"
    assert min_dash.find(obj, lambda _, key: key == "foo") == "FOO"
    assert min_dash.find_index(obj, lambda el: el == "BAR") == "bar"
    assert min_dash.find_index(obj, lambda _, key: key == "foo") == "foo"
    assert min_dash.filter({"a": 1, "b": 2, "c": 3}, lambda el: el > 1) == [2, 3]
    assert min_dash.filter({"a": 1, "b": 2, "c": 3}, lambda _, key: key != "b") == [1, 3]
    seen = {}
    min_dash.for_each({"a": 1, "b": 2}, lambda el, key: seen.update({key: el}))
    assert seen == {"a": 1, "b": 2}
    assert min_dash.map({"a": 1, "b": 2, "c": 3}, lambda val: val + 3) == [4, 5, 6]
    # N-A in this title: without/reduce/every/some/values/keys/groupBy (unused downstream).


@pytest.mark.upstream("min-dash/test/collection.spec.js", "should be null-safe")
def test_null_safe_cases() -> None:
    assert min_dash.find(None, lambda el: el == "BAR") is UNDEFINED
    assert min_dash.find_index(None, lambda el: el == "BAR") is UNDEFINED
    assert min_dash.filter(None, lambda a: a) == []
    min_dash.for_each(None, lambda: None)  # must not throw
    assert min_dash.map(None, lambda: False) == []
    # N-A in this title: reduce/every/some/values/keys (unused downstream).


@pytest.mark.upstream("min-dash/test/collection.spec.js", "should strict equality check arg")
def test_strict_equality_check_arg() -> None:
    assert min_dash.find([0, "", None], 0) == 0
    assert min_dash.find_index({"a": 0, "b": "", "c": None}, None) == "c"


@pytest.mark.upstream("min-dash/test/collection.spec.js", "should break on returning <false>")
def test_break_on_false() -> None:
    called = []

    def visit(el: object, _: object) -> bool | None:
        called.append(el)
        if el == 2:
            return False
        return None

    min_dash.for_each([1, 2, 3], visit)
    assert called == [1, 2]


@pytest.mark.upstream(
    "min-dash/test/collection.spec.js", "should return the result that stopped the iteration"
)
def test_return_stopping_result() -> None:
    def visit(el: object) -> bool | None:
        return False if el == 2 else None

    assert min_dash.for_each([1, 2, 3], visit) == 2


@pytest.mark.upstream("min-dash/test/collection.spec.js", "should not work on Object")
def test_without_not_transposed() -> None:
    # N-A: `without` is unused by the ported libraries (see docs/naming.md § min-dash).
    assert not hasattr(min_dash, "without")
    assert "without" not in min_dash.__all__


@pytest.mark.upstream("min-dash/test/collection.spec.js", "should always return boolean")
def test_every_not_transposed() -> None:
    # N-A: `every` is unused by the ported libraries (see docs/naming.md § min-dash).
    assert not hasattr(min_dash, "every")
    assert "every" not in min_dash.__all__
    # N-A in this title: reduce/some (same reason).


@pytest.mark.upstream("min-dash/test/collection.spec.js", "should use supplied group")
def test_group_by_not_transposed() -> None:
    # N-A: `groupBy` is unused by the ported libraries (see docs/naming.md § min-dash).
    assert not hasattr(min_dash, "group_by")
    assert "group_by" not in min_dash.__all__


@pytest.mark.upstream("min-dash/test/collection.spec.js", "should process by attribute")
def test_unique_by_and_sort_by_not_transposed() -> None:
    # N-A: `uniqueBy`/`sortBy` are unused by the ported libraries (docs/naming.md § min-dash).
    assert not hasattr(min_dash, "unique_by")
    assert not hasattr(min_dash, "sort_by")


@pytest.mark.upstream("min-dash/test/collection.spec.js", "should === uniqueBy")
def test_union_by_not_transposed() -> None:
    # N-A: `unionBy` is unused by the ported libraries (see docs/naming.md § min-dash).
    assert not hasattr(min_dash, "union_by")
    assert "union_by" not in min_dash.__all__


@pytest.mark.upstream("min-dash/test/collection.spec.js", "should process by discriminator fn")
def test_sort_by_fn_not_transposed() -> None:
    # N-A: `sortBy` is unused by the ported libraries (see docs/naming.md § min-dash).
    assert not hasattr(min_dash, "sort_by")


@pytest.mark.upstream("min-dash/test/collection.spec.js", "should strictly equal { key: value }")
def test_match_pattern_not_transposed() -> None:
    # N-A: `matchPattern` is unused by the ported libraries (docs/naming.md § min-dash).
    assert not hasattr(min_dash, "match_pattern")
    assert "match_pattern" not in min_dash.__all__


@pytest.mark.upstream("min-dash/test/collection.spec.js", "should return # of keys for Array")
def test_size_array_not_transposed() -> None:
    # N-A: `size` is unused by the ported libraries (see docs/naming.md § min-dash).
    assert not hasattr(min_dash, "size")
    assert "size" not in min_dash.__all__
    # N-A in this title: values/keys (same reason).


@pytest.mark.upstream("min-dash/test/collection.spec.js", "should return # of keys for Object")
def test_size_object_not_transposed() -> None:
    # N-A: `size` is unused by the ported libraries (see docs/naming.md § min-dash).
    assert not hasattr(min_dash, "values")
    assert not hasattr(min_dash, "keys")
