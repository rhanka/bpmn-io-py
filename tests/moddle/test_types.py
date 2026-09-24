"""Ported moddle type cases (Lot 4).

Transcribes every ``moddle/test/spec/types.js`` ``it()`` title: one test per
unique ledger title (13 claims). Verification mirrors the upstream assertions:
``eql``/``equal`` become ``==``/``is``, ``true``/``false`` become ``is True``/
``is False``. Only the public ``bpmn_io.moddle`` API is used.
"""

from __future__ import annotations

import pytest

from bpmn_io.moddle import coerce_type, is_built_in_type, is_simple_type

OBJECT_PROPERTIES = ["constructor", "toString", "__proto__", "hasOwnProperty"]


@pytest.mark.upstream("moddle/test/spec/types.js", "should convert Real")
def test_001_convert_real() -> None:
    assert coerce_type("Real", "420") == 420.0


@pytest.mark.upstream("moddle/test/spec/types.js", "should convert Real (-0.01)")
def test_002_convert_real_negative() -> None:
    assert coerce_type("Real", "-0.01") == -0.01


@pytest.mark.upstream("moddle/test/spec/types.js", "should convert Boolean (true)")
def test_003_convert_boolean_true() -> None:
    assert coerce_type("Boolean", "true") is True


@pytest.mark.upstream("moddle/test/spec/types.js", "should convert Boolean (false)")
def test_004_convert_boolean_false() -> None:
    assert coerce_type("Boolean", "false") is False


@pytest.mark.upstream("moddle/test/spec/types.js", "should convert Integer")
def test_005_convert_integer() -> None:
    assert coerce_type("Integer", "12012") == 12012


@pytest.mark.upstream("moddle/test/spec/types.js", "should NOT convert complex")
def test_006_not_convert_complex() -> None:
    complex_element = {"a": "A"}

    assert coerce_type("Element", complex_element) is complex_element


@pytest.mark.upstream("moddle/test/spec/types.js", "should NOT convert Object properties")
def test_007_not_convert_object_properties() -> None:
    for prop in OBJECT_PROPERTIES:
        value = {"a": "A"}

        assert coerce_type(prop, value) is value, prop


@pytest.mark.upstream("moddle/test/spec/types.js", "should recognize built-in types")
def test_008_recognize_built_in_types() -> None:
    assert is_built_in_type("String") is True
    assert is_built_in_type("Boolean") is True
    assert is_built_in_type("Integer") is True
    assert is_built_in_type("Real") is True
    assert is_built_in_type("Element") is True


@pytest.mark.upstream("moddle/test/spec/types.js", "should NOT recognize custom types")
def test_009_not_recognize_custom_types() -> None:
    assert is_built_in_type("props:Complex") is False


@pytest.mark.upstream(
    "moddle/test/spec/types.js", "should NOT recognize Object properties as built-in"
)
def test_010_not_recognize_object_properties_as_built_in() -> None:
    for prop in OBJECT_PROPERTIES:
        assert is_built_in_type(prop) is False, prop


@pytest.mark.upstream("moddle/test/spec/types.js", "should recognize simple types")
def test_011_recognize_simple_types() -> None:
    assert is_simple_type("String") is True
    assert is_simple_type("Boolean") is True
    assert is_simple_type("Integer") is True
    assert is_simple_type("Real") is True


@pytest.mark.upstream("moddle/test/spec/types.js", "should NOT recognize Element as simple")
def test_012_not_recognize_element_as_simple() -> None:
    assert is_simple_type("Element") is False


@pytest.mark.upstream(
    "moddle/test/spec/types.js", "should NOT recognize Object properties as simple"
)
def test_013_not_recognize_object_properties_as_simple() -> None:
    for prop in OBJECT_PROPERTIES:
        assert is_simple_type(prop) is False, prop
