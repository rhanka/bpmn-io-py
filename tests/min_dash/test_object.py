"""Ported min-dash object cases (Lot 2).

Claims every ``min-dash/test/object.spec.js`` title for the transposed helpers
(``assign``, ``pick``, ``set``); titles covering ``get``/``omit``/``merge`` are
claimed N-A with a reason (see ``docs/naming.md`` § min-dash).
"""

from __future__ import annotations

import pytest

import bpmn_io._min_dash as min_dash
from bpmn_io._js import UNDEFINED


@pytest.mark.upstream("min-dash/test/object.spec.js", "should take selected attributes")
def test_pick_selected_attributes() -> None:
    obj = {"a": 1, "b": False, "c": None, "e": UNDEFINED}
    assert min_dash.pick(obj, ["a", "c", "d", "e"]) == {"a": 1, "c": None, "e": UNDEFINED}
    assert min_dash.pick(obj, ["a", "b"])["a"] == 1


@pytest.mark.upstream(
    "min-dash/test/object.spec.js", "should handle computed and non-enumerable properties"
)
def test_pick_undefined_valued_property() -> None:
    # Adapted: plain dicts have no getters or non-enumerable properties; the
    # UNDEFINED-valued case ports literally, the rest is N-A with this reason.
    assert min_dash.pick({"a": 1, "e": UNDEFINED}, ["a", "c", "d", "e"]) == {
        "a": 1,
        "e": UNDEFINED,
    }


@pytest.mark.upstream("min-dash/test/object.spec.js", "should pick inherited properties")
def test_pick_inherited_properties() -> None:
    class Proto:
        a = 1

    assert min_dash.pick(Proto(), ["a"]) == {"a": 1}


@pytest.mark.upstream("min-dash/test/object.spec.js", "should omit selected attributes")
def test_omit_not_transposed() -> None:
    # N-A: `omit` is unused by the ported libraries (see docs/naming.md § min-dash).
    assert not hasattr(min_dash, "omit")
    assert "omit" not in min_dash.__all__


@pytest.mark.upstream("min-dash/test/object.spec.js", "should ignore non-enumerable properties")
def test_omit_non_enumerable_not_transposed() -> None:
    # N-A: `omit` is unused by the ported libraries (see docs/naming.md § min-dash).
    assert not hasattr(min_dash, "omit")


@pytest.mark.upstream("min-dash/test/object.spec.js", "should merge objects")
def test_assign_merges_objects() -> None:
    obj1 = {"a": 1, "b": False, "c": None}
    obj2 = {"a": False, "d": UNDEFINED}
    assert min_dash.assign({}, obj1, obj2) == {"a": False, "b": False, "c": None, "d": UNDEFINED}


@pytest.mark.upstream("min-dash/test/object.spec.js", "should handle null objects")
def test_assign_handles_null_objects() -> None:
    result = min_dash.assign(
        {"bar": "Bar"},
        None,
        UNDEFINED,
        False,  # noqa: FBT003
        0,
        {"foo": "Foo"},
    )
    assert result == {"bar": "Bar", "foo": "Foo"}


@pytest.mark.upstream("min-dash/test/object.spec.js", "should not override prototype")
def test_assign_keeps_type() -> None:
    class Foo:
        pass

    class Bar:
        pass

    obj1: Foo = Foo()
    result = min_dash.assign(obj1, Bar())
    assert result is obj1
    assert type(result) is Foo
    # N-A in this title: the `merge` case (unused downstream).


@pytest.mark.upstream("min-dash/test/object.spec.js", "should not allow prototype pollution")
def test_assign_no_prototype_pollution() -> None:
    target = {"merge": {"me": "nested"}}
    min_dash.assign(target, {"__proto__": {"alert": 1}})
    assert target == {"merge": {"me": "nested"}, "__proto__": {"alert": 1}}
    assert not hasattr({}, "alert")
    # N-A in this title: the `merge` case (unused downstream).


@pytest.mark.upstream("min-dash/test/object.spec.js", "should merge recursively")
def test_merge_not_transposed() -> None:
    # N-A: `merge` is unused by the ported libraries (see docs/naming.md § min-dash).
    assert not hasattr(min_dash, "merge")
    assert "merge" not in min_dash.__all__


@pytest.mark.upstream("min-dash/test/object.spec.js", "should return modified object")
def test_set_returns_modified_object() -> None:
    target: dict[str, bool] = {}
    assert min_dash.set(target, ["a"], True) is target  # noqa: FBT003 - upstream value


@pytest.mark.upstream("min-dash/test/object.spec.js", "should set property value")
def test_set_property_value() -> None:
    assert min_dash.set({}, ["a"], True) == {"a": True}  # noqa: FBT003 - upstream value
    assert min_dash.set({}, [""], "A") == {"": "A"}
    assert min_dash.set({}, [0], "A") == {"0": "A"}


@pytest.mark.upstream("min-dash/test/object.spec.js", "should set array value")
def test_set_array_value() -> None:
    assert min_dash.set([0, 1, 2], [1], "A") == [0, "A", 2]
    assert min_dash.set([0, 1, 2], [1], 0) == [0, 0, 2]
    assert min_dash.set({"a": [0, 0]}, ["a", 1], 1) == {"a": [0, 1]}
    assert min_dash.set({"a": [{"b": "FOO"}]}, ["a", 0, "b"], "BAR") == {"a": [{"b": "BAR"}]}


@pytest.mark.upstream("min-dash/test/object.spec.js", "should set array with string keys")
def test_set_array_with_string_keys() -> None:
    assert min_dash.set([0, 1, 2], ["1"], "A") == [0, "A", 2]
    assert min_dash.set({"a": [0, 0]}, ["a", "1"], 1) == {"a": [0, 1]}


@pytest.mark.upstream("min-dash/test/object.spec.js", "should delete value")
def test_set_deletes_value() -> None:
    assert min_dash.set({"a": False}, ["a"], UNDEFINED) == {}
    assert min_dash.set({"": False}, [""], UNDEFINED) == {}


@pytest.mark.upstream("min-dash/test/object.spec.js", "should set nested value")
def test_set_nested_value() -> None:
    assert min_dash.set(
        {"a": {"b": {}}},
        ["a", "b"],
        False,  # noqa: FBT003
    ) == {"a": {"b": False}}
    assert min_dash.set({"a": {"b": {}}}, ["a", "b", "c"], "C") == {"a": {"b": {"c": "C"}}}


@pytest.mark.upstream("min-dash/test/object.spec.js", "should scaffold object hierarchy")
def test_set_scaffolds_objects() -> None:
    assert min_dash.set({}, ["a", "b", "c"], "C") == {"a": {"b": {"c": "C"}}}
    assert min_dash.set({"a": None}, ["a", "b", "c"], "C") == {"a": {"b": {"c": "C"}}}


@pytest.mark.upstream("min-dash/test/object.spec.js", "should scaffold array hierarchy")
def test_set_scaffolds_arrays() -> None:
    assert min_dash.set({}, ["a", 1, 2], "C") == {"a": [UNDEFINED, [UNDEFINED, UNDEFINED, "C"]]}
    assert min_dash.set({}, ["a", "1", "2"], "C") == {"a": [UNDEFINED, [UNDEFINED, UNDEFINED, "C"]]}


@pytest.mark.upstream("min-dash/test/object.spec.js", "should not allow prototype polution")
def test_set_rejects_proto_key() -> None:
    with pytest.raises(ValueError, match="illegal key"):
        min_dash.set({}, ["__proto__"], {"foo": "bar"})


@pytest.mark.upstream(
    "min-dash/test/object.spec.js", "should not allow prototype polution via constructor"
)
def test_set_rejects_constructor_key() -> None:
    with pytest.raises(ValueError, match="illegal key"):
        min_dash.set({}, ["constructor", "prototype", "polluted"], "success")


@pytest.mark.upstream("min-dash/test/object.spec.js", "should not allow array as key")
def test_set_rejects_array_key() -> None:
    with pytest.raises(TypeError, match="illegal key type"):
        min_dash.set({}, [["__proto__"], "polluted"], "success")


@pytest.mark.upstream("min-dash/test/object.spec.js", "should not allow object as key")
def test_set_rejects_object_key() -> None:
    with pytest.raises(TypeError, match="illegal key type"):
        min_dash.set({}, [{}, "polluted"], "success")


@pytest.mark.upstream("min-dash/test/object.spec.js", "should return object property")
def test_get_object_not_transposed() -> None:
    # N-A: `get` is unused by the ported libraries (see docs/naming.md § min-dash).
    assert not hasattr(min_dash, "get")
    assert "get" not in min_dash.__all__


@pytest.mark.upstream("min-dash/test/object.spec.js", "should return array property")
def test_get_array_not_transposed() -> None:
    # N-A: `get` is unused by the ported libraries (see docs/naming.md § min-dash).
    assert not hasattr(min_dash, "get")
