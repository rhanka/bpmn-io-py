"""Ported moddle extension cases (Lot 4).

Transcribes every ``moddle/test/spec/extension.js`` ``it()`` title: one test
per unique ledger title (15 claims). Verification mirrors the upstream
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


def _load(*names: str) -> list[dict[str, Any]]:
    """Load model fixture packages by name."""
    return [json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8")) for name in names]


@pytest.mark.upstream("moddle/test/spec/extension.js", "should shadow <Element>")
def test_001_shadow_element() -> None:
    model = Moddle(_load("shadow"))

    element = model.create("s:Element")

    assert element is not None
    assert element.instance_of("s:Element") is True


@pytest.mark.upstream(
    "moddle/test/spec/extension.js", "should shadow <Element> in inheritance hierarchy"
)
def test_002_shadow_element_in_hierarchy() -> None:
    model = Moddle(_load("shadow"))

    element = model.create("s:NamedElement")

    assert element is not None
    assert element.instance_of("s:Element") is True
    assert element.instance_of("s:NamedElement") is True


@pytest.mark.upstream("moddle/test/spec/extension.js", "should provide <Element> built-in type")
def test_003_provide_element_built_in_type() -> None:
    model = Moddle(_load("shadow"))

    element = model.create("s:ExtendsBuiltinElement")

    assert element is not None
    assert element.instance_of("Element") is True
    assert element.instance_of("s:ExtendsBuiltinElement") is True


@pytest.mark.upstream("moddle/test/spec/extension.js", "should not provide meta-data")
def test_004_not_provide_meta_data() -> None:
    model = Moddle(_load("extension/base", "extension/custom"))

    with pytest.raises(
        ValueError, match=re.escape("cannot create <c:CustomRoot> extending <b:Root>")
    ):
        model.get_type("c:CustomRoot")


@pytest.mark.upstream("moddle/test/spec/extension.js", "should indicate non-inherited")
def test_005_indicate_non_inherited() -> None:
    model = Moddle(_load("extension/base", "extension/custom"))
    complex_type = model.get_type("b:Root")

    descriptor = model.get_element_descriptor(complex_type)

    assert descriptor.properties_by_name["customAttr"].inherited is False
    assert descriptor.properties_by_name["customBaseAttr"].inherited is False
    assert descriptor.properties_by_name["ownAttr"].inherited is True


@pytest.mark.upstream("moddle/test/spec/extension.js", "should plug-in into type hierarchy")
def test_006_plug_in_into_type_hierarchy() -> None:
    model = Moddle(_load("extension/base", "extension/custom"))

    root = model.create("b:Root")

    assert root.instance_of("c:CustomRoot") is True


@pytest.mark.upstream("moddle/test/spec/extension.js", "should add custom attribute")
def test_007_add_custom_attribute() -> None:
    model = Moddle(_load("extension/base", "extension/custom"))

    root = model.create("b:Root", {"customAttr": -1})

    assert root.customAttr == -1


@pytest.mark.upstream("moddle/test/spec/extension.js", "should refine property")
def test_008_refine_property() -> None:
    model = Moddle(_load("extension/base", "extension/custom"))
    prop_type = model.get_type("b:Root")

    generic_property = prop_type.descriptor_.properties_by_name["generic"]

    assert generic_property.type == "c:CustomGeneric"


@pytest.mark.upstream("moddle/test/spec/extension.js", "should use refined property")
def test_009_use_refined_property() -> None:
    model = Moddle(_load("extension/base", "extension/custom"))
    custom_generic = model.create("c:CustomGeneric", {"count": 100})

    root = model.create("b:Root", {"generic": custom_generic})

    assert root.generic == custom_generic


@pytest.mark.upstream("moddle/test/spec/extension.js", "should provide custom types")
def test_010_provide_custom_types() -> None:
    model = Moddle(_load("extension/base", "extension/custom"))

    prop = model.create("c:Property")

    assert prop.instance_of("c:Property") is True


@pytest.mark.upstream("moddle/test/spec/extension.js", "should extend Element")
def test_011_extend_element() -> None:
    model = Moddle(_load("extension/base", "extension/custom"))

    custom_generic = model.create("c:CustomGeneric", {"count": 100})

    assert custom_generic.instance_of("Element") is True


@pytest.mark.upstream("moddle/test/spec/extension.js", "should be part of generic collection")
def test_012_be_part_of_generic_collection() -> None:
    model = Moddle(_load("extension/base", "extension/custom"))
    custom_property = model.create("c:Property", {"key": "foo", "value": "bar"})

    root = model.create("b:Root", {"genericCollection": [custom_property]})

    assert root.genericCollection == [custom_property]


@pytest.mark.upstream("moddle/test/spec/extension.js", "should replace in descriptor")
def test_013_replace_in_descriptor() -> None:
    model = Moddle(_load("replaces/base"))
    extension = model.get_type("b:Extension")

    descriptor = model.get_element_descriptor(extension)
    property_names = [prop.name for prop in descriptor.properties]

    assert property_names == ["name", "value", "id"]
    assert descriptor.properties_by_name["b:id"].type == "Integer"
    assert descriptor.properties_by_name["id"].type == "Integer"


@pytest.mark.upstream("moddle/test/spec/extension.js", "should redefine in descriptor")
def test_014_redefine_in_descriptor() -> None:
    model = Moddle(_load("redefines/base"))
    extension = model.get_type("b:Extension")

    descriptor = model.get_element_descriptor(extension)
    property_names = [prop.name for prop in descriptor.properties]

    assert property_names == ["id", "name", "value"]
    assert descriptor.properties_by_name["b:id"].type == "Integer"
    assert descriptor.properties_by_name["id"].type == "Integer"


@pytest.mark.upstream("moddle/test/spec/extension.js", "should self-extend")
def test_015_self_extend() -> None:
    model = Moddle(_load("self-extend"))

    element = model.create("se:Rect")

    assert element.instance_of("se:ExtendedRect") is True
    assert element.instance_of("se:OtherExtendedRect") is True
