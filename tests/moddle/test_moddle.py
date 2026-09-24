"""Ported moddle core cases (Lot 4).

Transcribes every ``moddle/test/spec/moddle.js`` ``it()`` title: one test per
unique ledger title (34 claims; the 2 titles the ledger lists twice are claimed
once, on first occurrence — the differing strict-mode body is asserted in the
same test, never with a second marker). Verification mirrors the upstream
assertions: ``exist`` becomes ``is not None``, ``eql``/``jsonEqual`` become
``==``, ``throw(/re/)`` becomes ``pytest.raises(..., match=...)``. Only the
public ``bpmn_io.moddle`` API is used.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from bpmn_io.moddle import Moddle

FIXTURES = (
    Path(__file__).resolve().parent.parent / "upstream" / "moddle" / "test" / "fixtures" / "model"
)

OBJECT_PROPERTIES = ["constructor", "toString", "__proto__"]


def _load(*names: str) -> list[dict[str, Any]]:
    """Load model fixture packages by name."""
    return [json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8")) for name in names]


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should provide types")
def test_001_provide_types() -> None:
    model = Moddle(_load("properties"))

    complex_type = model.get_type("props:Complex")
    simple_body = model.get_type("props:SimpleBody")
    attributes = model.get_type("props:Attributes")

    assert complex_type is not None
    assert simple_body is not None
    assert attributes is not None


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should provide packages by prefix")
def test_002_provide_packages_by_prefix() -> None:
    model = Moddle(_load("properties"))

    package = model.get_package("props")

    assert package is not None
    assert package["name"] == "Properties"
    assert package["uri"] == "http://properties"
    assert package["prefix"] == "props"


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should provide packages by uri")
def test_003_provide_packages_by_uri() -> None:
    model = Moddle(_load("properties"))

    package = model.get_package("http://properties")

    assert package is not None
    assert package["name"] == "Properties"
    assert package["uri"] == "http://properties"
    assert package["prefix"] == "props"


@pytest.mark.upstream(
    "moddle/test/spec/moddle.js", "should NOT return Object properties as package"
)
def test_004_not_return_object_properties_as_package() -> None:
    model = Moddle(_load("properties"))

    for prop in OBJECT_PROPERTIES:
        assert model.get_package(prop) is None, prop


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should provide type descriptor")
def test_005_provide_type_descriptor() -> None:
    model = Moddle(_load("properties"))
    complex_type = model.get_type("props:Complex")

    descriptor = model.get_element_descriptor(complex_type)

    assert descriptor is not None
    assert descriptor.name == "props:Complex"
    assert (descriptor.ns.name, descriptor.ns.prefix, descriptor.ns.local_name) == (
        "props:Complex",
        "props",
        "Complex",
    )

    assert len(descriptor.properties) == 1
    prop = descriptor.properties[0]
    assert prop.name == "id"
    assert prop.type == "String"
    assert prop.is_attr is True
    assert prop.is_id is True
    assert (prop.ns.name, prop.ns.prefix, prop.ns.local_name) == ("props:id", "props", "id")
    assert prop.inherited is True

    assert descriptor.properties_by_name["id"] is prop
    assert descriptor.properties_by_name["props:id"] is prop


@pytest.mark.upstream(
    "moddle/test/spec/moddle.js", "should provide type descriptor via $descriptor property"
)
def test_006_provide_type_descriptor_via_descriptor_property() -> None:
    model = Moddle(_load("properties"))
    complex_type = model.get_type("props:Complex")
    expected_descriptor = model.get_element_descriptor(complex_type)

    descriptor = complex_type.descriptor_

    assert descriptor is expected_descriptor


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should provide model via $model property")
def test_007_provide_model_via_model_property() -> None:
    model = Moddle(_load("properties"))
    complex_type = model.get_type("props:Complex")

    found_model = complex_type.model_

    assert found_model is model


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should provide meta-data")
def test_008_provide_meta_data() -> None:
    model = Moddle(_load("properties"))

    instance = model.create("props:BaseWithNumericId")

    assert instance.descriptor_ is not None
    assert instance.type_ == "props:BaseWithNumericId"


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should provide attrs + basic meta-data")
def test_009_provide_attrs_basic_meta_data() -> None:
    model = Moddle(_load("properties"))

    any_instance = model.create_any("other:Foo", "http://other", {"bar": "BAR"})

    assert any_instance.to_canonical_dict() == {"$type": "other:Foo", "bar": "BAR"}
    assert any_instance.instance_of("other:Foo") is True


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should provide ns meta-data")
def test_010_provide_ns_meta_data() -> None:
    model = Moddle(_load("properties"))

    any_instance = model.create_any("other:Foo", "http://other", {"bar": "BAR"})

    descriptor = any_instance.descriptor_
    assert descriptor.name == "other:Foo"
    assert descriptor.is_generic is True
    assert (descriptor.ns_prefix, descriptor.ns_local_name, descriptor.ns_uri) == (
        "other",
        "Foo",
        "http://other",
    )


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should return non-enumerable special props")
def test_011_return_non_enumerable_special_props() -> None:
    model = Moddle(_load("properties"))
    any_instance = model.create_any("other:Foo", "http://other", {"bar": "BAR"})

    assert "parent_" not in any_instance.to_canonical_dict()
    assert "instance_of" not in vars(any_instance)

    any_instance.parent_ = "foo"

    assert "parent_" not in any_instance.to_canonical_dict()
    assert "instance_of" not in vars(any_instance)


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should have getters")
def test_012_have_getters() -> None:
    model = Moddle(_load("properties"))

    any_instance = model.create_any("other:Foo", "http://other", {"bar": "BAR"})

    assert any_instance.get("bar") == "BAR"


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should have setters")
def test_013_have_setters() -> None:
    model = Moddle(_load("properties"))
    any_instance = model.create_any("other:Foo", "http://other")

    any_instance.set("bar", "BAR")

    assert any_instance.get("bar") == "BAR"


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should prevent prototype pollution")
def test_014_prevent_prototype_pollution() -> None:
    model = Moddle(_load("properties"))
    any_instance = model.create_any("other:Foo", "http://other")

    with pytest.raises(ValueError, match=re.escape("illegal key: __proto__")):
        any_instance.set("__proto__", {"hacked": True})


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should NOT allow array as key")
def test_015_not_allow_array_as_key() -> None:
    model = Moddle(_load("properties"))
    any_instance = model.create_any("other:Foo", "http://other")

    with pytest.raises(
        TypeError,
        match=re.escape("illegal key type: object. Key should be of type number or string."),
    ):
        any_instance.set(["path", "to", "key"], "value")


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should mark accessors as special props")
def test_016_mark_accessors_as_special_props() -> None:
    model = Moddle(_load("properties"))

    any_instance = model.create_any("other:Foo", "http://other", {"bar": "BAR"})

    assert "get" not in vars(any_instance)
    assert "set" not in vars(any_instance)


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should provide instantiatable type")
def test_017_provide_instantiatable_type() -> None:
    model = Moddle(_load("properties"))
    simple_body = model.get_type("props:SimpleBody")

    instance = simple_body({"body": "BAR"})

    assert isinstance(instance, simple_body) is True
    assert instance.body == "BAR"


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should query types via $instanceOf")
def test_018_query_types_via_instance_of() -> None:
    model = Moddle(_load("properties"))

    instance = model.create("props:BaseWithNumericId")

    assert instance.instance_of("props:BaseWithNumericId") is True
    assert instance.instance_of("props:Base") is True


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should provide $type in instance")
def test_019_provide_type_in_instance() -> None:
    model = Moddle(_load("properties"))
    simple_body = model.get_type("props:SimpleBody")

    instance = simple_body()

    assert instance.type_ == "props:SimpleBody"


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should provide $descriptor in instance")
def test_020_provide_descriptor_in_instance() -> None:
    model = Moddle(_load("properties"))
    simple_body = model.get_type("props:SimpleBody")

    instance = simple_body()

    assert instance.descriptor_ == simple_body.descriptor_


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should get property descriptor")
def test_021_get_property_descriptor() -> None:
    model = Moddle(_load("properties"))
    simple_body = model.get_type("props:SimpleBody")
    instance = simple_body()

    body = model.get_property_descriptor(instance, "props:body")

    assert body is not None
    assert body.name == "body"
    assert body.type == "String"
    assert body.is_body is True
    assert (body.ns.name, body.ns.prefix, body.ns.local_name) == ("props:body", "props", "body")


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should get type descriptor")
def test_022_get_type_descriptor() -> None:
    model = Moddle(_load("properties"))

    simple_body = model.get_type_descriptor("props:SimpleBody")

    assert simple_body is not None
    assert simple_body["name"] == "props:SimpleBody"
    assert simple_body["superClass"] == ["Base"]
    assert "properties" in simple_body


@pytest.mark.upstream(
    "moddle/test/spec/moddle.js", "should NOT resolve Object properties as type / descriptor"
)
def test_023_not_resolve_object_properties_as_type_descriptor() -> None:
    model = Moddle(_load("properties"))
    simple_body = model.get_type("props:SimpleBody")
    instance = simple_body()

    for prop in OBJECT_PROPERTIES:
        with pytest.raises(ValueError, match="unknown type"):
            model.get_type(prop)

        assert model.get_type_descriptor(prop) is None, prop
        assert model.get_property_descriptor(instance, prop) is None, prop
        assert model.has_type(instance, prop) is False, prop


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should handle package redefinition")
def test_024_handle_package_redefinition() -> None:
    packages = _load("properties", "properties")

    with pytest.raises(ValueError, match=re.escape("package with prefix <props>")):
        Moddle(packages)


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should access basic")
def test_025_access_basic() -> None:
    moddle = Moddle(_load("properties", "properties-extended"))

    element = moddle.create("props:ComplexCount", {"count": 10})

    assert element.get("count") == 10
    assert element.get("props:count") == 10
    assert element.count is not None

    # same ledger title, second occurrence transcribes the strict-mode body
    strict = Moddle(_load("properties"), {"strict": True})

    strict_element = strict.create("props:ComplexCount", {"count": 10})

    assert strict_element.get("count") == 10
    assert strict_element.get("props:count") == 10
    assert strict_element.count is not None


@pytest.mark.upstream(
    "moddle/test/spec/moddle.js", "should access refined property, created via base name"
)
def test_026_access_refined_property_created_via_base_name() -> None:
    moddle = Moddle(_load("properties", "properties-extended"))

    element = moddle.create("ext:ExtendedComplex", {"count": 10})

    assert element.get("numCount") == 10
    assert element.get("ext:numCount") == 10
    assert element.get("count") == 10
    assert element.get("props:count") == 10
    assert element.numCount == 10
    assert not hasattr(element, "count")


@pytest.mark.upstream(
    "moddle/test/spec/moddle.js", "should access refined property, created via refined name"
)
def test_027_access_refined_property_created_via_refined_name() -> None:
    moddle = Moddle(_load("properties", "properties-extended"))

    element = moddle.create("ext:ExtendedComplex", {"numCount": 10})

    assert element.get("numCount") == 10
    assert element.get("ext:numCount") == 10
    assert element.get("count") == 10
    assert element.get("props:count") == 10
    assert element.numCount == 10
    assert not hasattr(element, "count")


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should access global name")
def test_028_access_global_name() -> None:
    moddle = Moddle(_load("properties", "properties-extended"))

    element = moddle.create("props:ComplexCount", {":xmlns": "http://foo"})

    assert element.get(":xmlns") == "http://foo"
    assert element.get("xmlns") == "http://foo"

    assert element.attrs_.get("xmlns") == "http://foo"

    # same ledger title, second occurrence transcribes the strict-mode body
    strict = Moddle(_load("properties"), {"strict": True})

    strict_element = strict.create("props:ComplexCount", {":xmlns": "http://foo"})

    assert strict_element.get(":xmlns") == "http://foo"

    with pytest.raises(
        TypeError,
        match=re.escape("unknown property <xmlns> on <props:ComplexCount>"),
    ):
        strict_element.get("xmlns")

    assert strict_element.attrs_.get("xmlns") == "http://foo"


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should access global name (no prefix)")
def test_029_access_global_name_no_prefix() -> None:
    moddle = Moddle(_load("properties", "properties-extended"))

    element = moddle.create("props:ComplexCount", {"xmlns": "http://foo"})

    assert element.get(":xmlns") == "http://foo"
    assert element.get("xmlns") == "http://foo"

    assert element.attrs_.get("xmlns") == "http://foo"


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should access property")
def test_030_access_property() -> None:
    moddle = Moddle(_load("properties", "properties-extended"))

    element = moddle.create_any("foo:Bar", "http://tata", {"count": 10})

    assert element["count"] == 10


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should access unknown attribute")
def test_031_access_unknown_attribute() -> None:
    moddle = Moddle(_load("properties"), {"strict": False})

    with pytest.warns(UserWarning, match=re.escape("unknown property <foo>")):
        element = moddle.create("props:ComplexCount", {"foo": "bar"})

    with pytest.warns(UserWarning, match=re.escape("unknown property <foo>")):
        assert element.get("foo") == "bar"


@pytest.mark.upstream("moddle/test/spec/moddle.js", "should configure in strict mode")
def test_032_configure_in_strict_mode() -> None:
    moddle = Moddle(_load("properties"), {"strict": True})

    assert moddle.config["strict"] is True


@pytest.mark.upstream("moddle/test/spec/moddle.js", "fail accessing unknown property")
def test_033_fail_accessing_unknown_property() -> None:
    moddle = Moddle(_load("properties"), {"strict": True})

    element = moddle.create("props:ComplexCount")

    with pytest.raises(
        TypeError, match=re.escape("unknown property <foo> on <props:ComplexCount>")
    ):
        element.get("foo")

    with pytest.raises(
        TypeError, match=re.escape("unknown property <foo> on <props:ComplexCount>")
    ):
        element.set("foo", 10)


@pytest.mark.upstream("moddle/test/spec/moddle.js", "fail instantiating with unknown property")
def test_034_fail_instantiating_with_unknown_property() -> None:
    moddle = Moddle(_load("properties"), {"strict": True})

    with pytest.raises(
        TypeError, match=re.escape("unknown property <foo> on <props:ComplexCount>")
    ):
        moddle.create("props:ComplexCount", {"foo": 10})
