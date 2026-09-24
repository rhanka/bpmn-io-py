"""Ported moddle property cases (Lot 4).

Transcribes every ``moddle/test/spec/properties.js`` active ``it()`` title: one
test per unique ledger title (39 claims; the upstream ``it.skip`` case is absent
from the ledger and is not ported, and the dynamic non-string-name template
expands to one test per ledger title). Verification mirrors the upstream
assertions: ``exist`` becomes ``is not None``, ``eql``/``jsonEqual`` become
``==``, ``throw(TypeError, msg)`` becomes ``pytest.raises``. Only the public
``bpmn_io.moddle`` API is used.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bpmn_io.moddle import Moddle

FIXTURES = (
    Path(__file__).resolve().parent.parent / "upstream" / "moddle" / "test" / "fixtures" / "model"
)

GUARD_MESSAGE = "property name must be a non-empty string"


def _load(*names: str) -> list[dict[str, Any]]:
    """Load model fixture packages by name."""
    return [json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8")) for name in names]


def _model() -> Moddle:
    """Build the model the upstream ``properties`` suite runs against."""
    return Moddle(_load("properties", "properties-extended"))


def _undefined(model: Moddle) -> object:
    """Return the JS ``undefined`` sentinel through the public ``get`` API."""
    probe = model.create_any("tmp:Probe", "http://tmp")
    return probe.get("missing")


@pytest.mark.upstream("moddle/test/spec/properties.js", "should provide id property")
def test_001_provide_id_property() -> None:
    model = _model()
    complex_type = model.get_type("props:Complex")

    descriptor = model.get_element_descriptor(complex_type)
    id_property = descriptor.properties_by_name.get("id")

    assert id_property is not None
    assert id_property.is_id is True
    assert descriptor.id_property == id_property


@pytest.mark.upstream("moddle/test/spec/properties.js", "should provide body property")
def test_002_provide_body_property() -> None:
    model = _model()
    simple_body = model.get_type("props:SimpleBody")

    descriptor = model.get_element_descriptor(simple_body)
    body_property = descriptor.properties_by_name.get("body")

    assert body_property is not None
    assert body_property.is_body is True
    assert descriptor.body_property == body_property


@pytest.mark.upstream("moddle/test/spec/properties.js", "should NOT provide default id")
def test_003_not_provide_default_id() -> None:
    model = _model()
    simple_body = model.get_type("props:SimpleBody")

    descriptor = model.get_element_descriptor(simple_body)

    assert descriptor.properties_by_name.get("id") is None


@pytest.mark.upstream("moddle/test/spec/properties.js", "single parent")
def test_004_single_parent() -> None:
    model = _model()

    descriptor = model.get_element_descriptor(model.get_type("ext:Root"))
    properties_by_name = descriptor.properties_by_name

    assert "any" in properties_by_name
    assert "elements" in properties_by_name
    assert properties_by_name["elements"].inherited is True
    assert properties_by_name["any"].inherited is True


@pytest.mark.upstream("moddle/test/spec/properties.js", "multiple parents")
def test_005_multiple_parents() -> None:
    model = _model()

    descriptor = model.get_element_descriptor(model.get_type("props:MultipleSuper"))
    properties_by_name = descriptor.properties_by_name

    assert "id" in properties_by_name
    assert "body" in properties_by_name
    assert properties_by_name["id"].inherited is True
    assert properties_by_name["body"].inherited is True


@pytest.mark.upstream(
    "moddle/test/spec/properties.js", "should set simple properties in constructor"
)
def test_006_set_simple_properties_in_constructor() -> None:
    model = _model()

    attributes = model.create(
        "props:Attributes", {"id": "ATTR_1", "booleanValue": False, "integerValue": -1000}
    )

    assert attributes.id == "ATTR_1"
    assert attributes.booleanValue is False
    assert attributes.integerValue == -1000


@pytest.mark.upstream("moddle/test/spec/properties.js", "referencing")
def test_007_set_referencing_collection_in_constructor() -> None:
    model = _model()
    reference1 = model.create("props:ComplexCount")
    reference2 = model.create("props:ComplexNesting")

    collection = model.create(
        "props:ReferencingCollection", {"references": [reference1, reference2]}
    )

    assert collection.references == [reference1, reference2]


@pytest.mark.upstream("moddle/test/spec/properties.js", "containment")
def test_008_set_contained_collection_in_constructor() -> None:
    model = _model()
    child1 = model.create("props:ComplexCount")
    child2 = model.create("props:ComplexNesting")

    collection = model.create("props:ContainedCollection", {"children": [child1, child2]})

    assert collection.children == [child1, child2]


@pytest.mark.upstream("moddle/test/spec/properties.js", "local")
def test_009_provide_local_default_value() -> None:
    model = _model()
    attributes_type = model.get_type("props:Attributes")

    instance = attributes_type()

    assert instance.defaultBooleanValue is True


@pytest.mark.upstream("moddle/test/spec/properties.js", "inherited")
def test_010_provide_inherited_default_value() -> None:
    model = _model()
    sub_attributes_type = model.get_type("props:SubAttributes")

    instance = sub_attributes_type()

    assert instance.defaultBooleanValue is True


@pytest.mark.upstream("moddle/test/spec/properties.js", "should lazy init collection properties")
def test_011_lazy_init_collection_properties() -> None:
    model = _model()
    root_type = model.get_type("props:Root")
    instance = root_type()

    assert not hasattr(instance, "any")

    any_value = instance.get("props:any")

    assert any_value == []
    assert instance.any is any_value


@pytest.mark.upstream("moddle/test/spec/properties.js", "should set property")
def test_012_set_property() -> None:
    model = _model()
    instance = model.create("props:Attributes")

    instance.set("id", "ATTR_1")

    assert instance.id == "ATTR_1"


@pytest.mark.upstream("moddle/test/spec/properties.js", "should set property (ns)")
def test_013_set_property_ns() -> None:
    model = _model()
    instance = model.create("props:Attributes")

    instance.set("props:booleanValue", True)  # noqa: FBT003
    instance.set("props:integerValue", -1000)

    assert instance.booleanValue is True
    assert instance.integerValue == -1000


@pytest.mark.upstream("moddle/test/spec/properties.js", "should set extension property")
def test_014_set_extension_property() -> None:
    model = _model()
    instance = model.create("props:Attributes")

    instance.set("foo", "bar")

    assert instance.attrs_.get("foo") == "bar"
    assert "foo" not in vars(instance)


@pytest.mark.upstream("moddle/test/spec/properties.js", "should set extension property (ns)")
def test_015_set_extension_property_ns() -> None:
    model = _model()
    instance = model.create("props:Attributes")

    instance.set("namespace:foo", "bar")

    assert instance.attrs_.get("namespace:foo") == "bar"
    assert "foo" not in vars(instance)
    assert "namespace:foo" not in vars(instance)


@pytest.mark.upstream(
    "moddle/test/spec/properties.js", "should reject empty string as property name"
)
def test_016_reject_empty_string_as_property_name() -> None:
    model = _model()
    instance = model.create("props:Attributes")

    with pytest.raises(TypeError, match=GUARD_MESSAGE):
        instance.set("", "foo")


@pytest.mark.upstream(
    "moddle/test/spec/properties.js", "should reject non-string property name <false>"
)
def test_017_reject_non_string_property_name_false() -> None:
    model = _model()
    instance = model.create("props:Attributes")

    with pytest.raises(TypeError, match=GUARD_MESSAGE):
        instance.set(False, "foo")  # noqa: FBT003


@pytest.mark.upstream(
    "moddle/test/spec/properties.js", "should reject non-string property name <true>"
)
def test_018_reject_non_string_property_name_true() -> None:
    model = _model()
    instance = model.create("props:Attributes")

    with pytest.raises(TypeError, match=GUARD_MESSAGE):
        instance.set(True, "foo")  # noqa: FBT003


@pytest.mark.upstream(
    "moddle/test/spec/properties.js", "should reject non-string property name <undefined>"
)
def test_019_reject_non_string_property_name_undefined() -> None:
    model = _model()
    instance = model.create("props:Attributes")

    with pytest.raises(TypeError, match=GUARD_MESSAGE):
        instance.set(_undefined(model), "foo")


@pytest.mark.upstream(
    "moddle/test/spec/properties.js", "should reject non-string property name <null>"
)
def test_020_reject_non_string_property_name_null() -> None:
    model = _model()
    instance = model.create("props:Attributes")

    with pytest.raises(TypeError, match=GUARD_MESSAGE):
        instance.set(None, "foo")


@pytest.mark.upstream(
    "moddle/test/spec/properties.js", "should reject non-string property name <NaN>"
)
def test_021_reject_non_string_property_name_nan() -> None:
    model = _model()
    instance = model.create("props:Attributes")

    with pytest.raises(TypeError, match=GUARD_MESSAGE):
        instance.set(float("nan"), "foo")


@pytest.mark.upstream(
    "moddle/test/spec/properties.js",
    "should reject non-string property name <function Function() { [native code] }>",
)
def test_022_reject_non_string_property_name_function() -> None:
    model = _model()
    instance = model.create("props:Attributes")

    with pytest.raises(TypeError, match=GUARD_MESSAGE):
        instance.set(len, "foo")


@pytest.mark.upstream(
    "moddle/test/spec/properties.js", "should reject non-string property name <0>"
)
def test_023_reject_non_string_property_name_zero() -> None:
    model = _model()
    instance = model.create("props:Attributes")

    with pytest.raises(TypeError, match=GUARD_MESSAGE):
        instance.set(0, "foo")


@pytest.mark.upstream(
    "moddle/test/spec/properties.js", "should reject non-string property name <1>"
)
def test_024_reject_non_string_property_name_one() -> None:
    model = _model()
    instance = model.create("props:Attributes")

    with pytest.raises(TypeError, match=GUARD_MESSAGE):
        instance.set(1, "foo")


@pytest.mark.upstream(
    "moddle/test/spec/properties.js", "should reject non-string property name <Infinity>"
)
def test_025_reject_non_string_property_name_infinity() -> None:
    model = _model()
    instance = model.create("props:Attributes")

    with pytest.raises(TypeError, match=GUARD_MESSAGE):
        instance.set(float("inf"), "foo")


@pytest.mark.upstream("moddle/test/spec/properties.js", "should update property")
def test_026_update_property() -> None:
    model = _model()
    attributes = model.create("props:Attributes", {"id": "ATTR_1"})

    attributes.set("id", "ATTR_23")

    assert attributes.id == "ATTR_23"


@pytest.mark.upstream("moddle/test/spec/properties.js", "should update property (ns)")
def test_027_update_property_ns() -> None:
    model = _model()
    attributes = model.create("props:Attributes", {"props:integerValue": -1000})

    attributes.set("props:integerValue", 1024)

    assert attributes.integerValue == 1024


@pytest.mark.upstream("moddle/test/spec/properties.js", "should update extension property")
def test_028_update_extension_property() -> None:
    model = _model()
    attributes = model.create("props:Attributes", {"foo": "bar"})

    attributes.set("foo", "baz")

    assert attributes.attrs_.get("foo") == "baz"


@pytest.mark.upstream("moddle/test/spec/properties.js", "should update extension property (ns)")
def test_029_update_extension_property_ns() -> None:
    model = _model()
    attributes = model.create("props:Attributes", {"foo:bar": "baz"})

    attributes.set("foo:bar", "qux")

    assert attributes.attrs_.get("foo:bar") == "qux"


@pytest.mark.upstream("moddle/test/spec/properties.js", "should unset property")
def test_030_unset_property() -> None:
    model = _model()
    attributes = model.create("props:Attributes", {"id": "ATTR_1"})

    assert attributes.id == "ATTR_1"

    attributes.set("id", _undefined(model))

    assert not hasattr(attributes, "id")


@pytest.mark.upstream("moddle/test/spec/properties.js", "should unset property (ns)")
def test_031_unset_property_ns() -> None:
    model = _model()
    attributes = model.create("props:Attributes", {"props:integerValue": -1000})

    assert attributes.integerValue == -1000

    attributes.set("props:integerValue", _undefined(model))

    assert "integerValue" not in vars(attributes)
    assert "props:integerValue" not in vars(attributes)


@pytest.mark.upstream("moddle/test/spec/properties.js", "should unset extension property")
def test_032_unset_extension_property() -> None:
    model = _model()
    attributes = model.create("props:Attributes", {"foobar": 42})

    assert attributes.attrs_.get("foobar") == 42

    attributes.set("foobar", _undefined(model))

    assert "foobar" not in attributes.attrs_


@pytest.mark.upstream("moddle/test/spec/properties.js", "should unset extension property (ns)")
def test_033_unset_extension_property_ns() -> None:
    model = _model()
    attributes = model.create("props:Attributes", {"foo:bar": 42})

    assert attributes.attrs_.get("foo:bar") == 42

    attributes.set("foo:bar", _undefined(model))

    assert "foo:bar" not in attributes.attrs_


@pytest.mark.upstream("moddle/test/spec/properties.js", "descriptor")
def test_034_redefine_descriptor() -> None:
    model = _model()
    base_with_id = model.get_type("props:BaseWithId")
    base_with_numeric_id = model.get_type("props:BaseWithNumericId")

    base_descriptor = base_with_id.descriptor_
    redefined_descriptor = base_with_numeric_id.descriptor_

    original_id_property = base_descriptor.properties_by_name["id"]
    refined_id_property = redefined_descriptor.properties_by_name["id"]
    numeric_id_property = redefined_descriptor.properties_by_name["idNumeric"]

    assert refined_id_property != original_id_property
    assert refined_id_property is not None
    assert refined_id_property == numeric_id_property


@pytest.mark.upstream("moddle/test/spec/properties.js", "init in constructor")
def test_035_redefine_init_in_constructor() -> None:
    model = _model()
    base_with_numeric_id = model.get_type("props:BaseWithNumericId")

    instance = base_with_numeric_id({"id": 1000})

    assert instance.idNumeric == 1000


@pytest.mark.upstream("moddle/test/spec/properties.js", "access via #get")
def test_036_redefine_access_via_get() -> None:
    model = _model()
    base_with_numeric_id = model.get_type("props:BaseWithNumericId")

    instance = base_with_numeric_id({"id": 1000})

    assert instance.get("props:idNumeric") == 1000


@pytest.mark.upstream("moddle/test/spec/properties.js", "access via #get + original name")
def test_037_redefine_access_via_get_original_name() -> None:
    model = _model()
    base_with_numeric_id = model.get_type("props:BaseWithNumericId")

    instance = base_with_numeric_id({"id": 1000})

    assert instance.get("props:id") == 1000


@pytest.mark.upstream(
    "moddle/test/spec/properties.js",
    "should return $attrs property on non-metamodel defined property access",
)
def test_038_return_attrs_property_on_undefined_property_access() -> None:
    model = _model()
    base_with_numeric_id = model.get_type("props:BaseWithNumericId")

    instance = base_with_numeric_id({"id": 1000})
    instance.attrs_["unknown"] = "UNKNOWN"

    assert instance.get("unknown") == "UNKNOWN"


@pytest.mark.upstream("moddle/test/spec/properties.js", "should support proxies")
def test_039_support_proxies() -> None:
    model = _model()
    complex_type = model.get_type("props:Complex")

    proxy = _Proxy(complex_type)

    assert proxy.descriptor_ is not None


class _Proxy:
    """Minimal forwarding proxy mirroring the upstream ``Proxy`` integration case."""

    def __init__(self, target: object) -> None:
        """Wrap ``target``, forwarding every attribute access."""
        object.__setattr__(self, "_target", target)

    def __getattr__(self, name: str) -> object:
        """Return the wrapped attribute, re-wrapped to mirror nested proxies."""
        return _Proxy(getattr(object.__getattribute__(self, "_target"), name))
