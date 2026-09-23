"""Ported moddle-xml writer cases (Lot 6).

Transcribes every ``moddle-xml/test/spec/writer.js`` ``it()`` title: one test
per claim (77 claims; the two titles the file lists twice — ``single`` and
``collection`` — are claimed once per occurrence, on their distinct bodies:
embedded-properties vs reference). Verification mirrors the upstream
assertions as ``to_xml`` string equality. Only the public
``bpmn_io.moddle_xml`` API (``Writer``) plus model building via
``bpmn_io.moddle`` is used.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bpmn_io._js import UNDEFINED
from bpmn_io.moddle import Moddle
from bpmn_io.moddle_xml import Writer

FIXTURES = Path(__file__).resolve().parent.parent / "upstream" / "moddle-xml" / "test" / "fixtures"
MODEL_FIXTURES = FIXTURES / "model"


def _load(*names: str) -> list[dict[str, Any]]:
    """Load model fixture packages by name."""
    return [
        json.loads((MODEL_FIXTURES / f"{name}.json").read_text(encoding="utf-8")) for name in names
    ]


def _model(*names: str, config: dict[str, Any] | None = None) -> Moddle:
    """Build a model from fixture packages (strict, as the upstream helper)."""
    return Moddle(_load(*names), {"strict": True, **(config or {})})


def _writer(*, format: bool = False, preamble: bool = False) -> Writer:  # noqa: A002
    """Build a writer with the upstream defaults (no preamble unless asked)."""
    return Writer(format=format, preamble=preamble)


# should export > base


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should write xml preamble")
def test_001_write_xml_preamble() -> None:
    model = _model("properties")
    writer = Writer(preamble=True)
    root = model.create("props:Root")

    xml = writer.to_xml(root)

    assert xml == (
        '<?xml version="1.0" encoding="UTF-8"?>\n<props:root xmlns:props="http://properties" />'
    )


# should export > datatypes


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "via xsi:type")
def test_002_via_xsi_type() -> None:
    model = _model(
        "datatype",
        "datatype-external",
        "datatype-aliased",
        config={"nsMap": {"http://www.omg.org/spec/XMI/20131001": "xmi"}},
    )
    writer = _writer()
    root = model.create("dt:Root")
    root.set("bounds", model.create("dt:Rect", {"y": 100}))

    xml = writer.to_xml(root)

    assert xml == ('<dt:root xmlns:dt="http://datatypes"><dt:bounds y="100" /></dt:root>')


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "via xmi:type")
def test_003_via_xmi_type() -> None:
    model = _model(
        "datatype",
        "datatype-external",
        "datatype-aliased",
        config={"nsMap": {"http://www.omg.org/spec/XMI/20131001": "xmi"}},
    )
    writer = _writer()
    root = model.create("dt:Root")
    root.set("xmiBounds", model.create("dt:Rect", {"y": 100}))

    xml = writer.to_xml(root)

    assert xml == ('<dt:root xmlns:dt="http://datatypes"><dt:xmiBounds y="100" /></dt:root>')


@pytest.mark.upstream(
    "moddle-xml/test/spec/writer.js", "via xsi:type / default / extension attributes"
)
def test_004_via_xsi_type_default_extension_attributes() -> None:
    model = _model(
        "datatype",
        "datatype-external",
        "datatype-aliased",
        config={"nsMap": {"http://www.omg.org/spec/XMI/20131001": "xmi"}},
    )
    writer = _writer()
    root = model.create("dt:Root")
    root.set(
        "bounds",
        model.create("dt:Rect", {"y": 100, "xmlns:f": "http://foo", "f:bar": "BAR"}),
    )

    xml = writer.to_xml(root)

    assert xml == (
        '<dt:root xmlns:dt="http://datatypes">'
        '<dt:bounds xmlns:f="http://foo" y="100" f:bar="BAR" />'
        "</dt:root>"
    )


@pytest.mark.upstream(
    "moddle-xml/test/spec/writer.js", "via xsi:type / explicit / extension attributes"
)
def test_005_via_xsi_type_explicit_extension_attributes() -> None:
    model = _model(
        "datatype",
        "datatype-external",
        "datatype-aliased",
        config={"nsMap": {"http://www.omg.org/spec/XMI/20131001": "xmi"}},
    )
    writer = _writer()
    root = model.create("dt:Root")
    root.set(
        "bounds",
        model.create("do:Rect", {"x": 100, "xmlns:f": "http://foo", "f:bar": "BAR"}),
    )

    xml = writer.to_xml(root)

    assert xml == (
        '<dt:root xmlns:dt="http://datatypes">'
        '<dt:bounds xmlns:do="http://datatypes2" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:f="http://foo" xsi:type="do:Rect" '
        'x="100" f:bar="BAR" />'
        "</dt:root>"
    )


@pytest.mark.upstream(
    "moddle-xml/test/spec/writer.js", "via xsi:type / explicit / local ns declaration"
)
def test_006_via_xsi_type_explicit_local_ns_declaration() -> None:
    model = _model(
        "datatype",
        "datatype-external",
        "datatype-aliased",
        config={"nsMap": {"http://www.omg.org/spec/XMI/20131001": "xmi"}},
    )
    writer = _writer()
    root = model.create("dt:Root")
    root.set(
        "bounds",
        model.create(
            "do:Rect",
            {"x": 100, "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance"},
        ),
    )

    xml = writer.to_xml(root)

    assert xml == (
        '<dt:root xmlns:dt="http://datatypes">'
        '<dt:bounds xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:do="http://datatypes2" '
        'xsi:type="do:Rect" '
        'x="100" />'
        "</dt:root>"
    )


@pytest.mark.upstream(
    "moddle-xml/test/spec/writer.js", "via xsi:type / overriding existing <xsi:type> attr"
)
def test_007_via_xsi_type_overriding_existing_xsi_type_attr() -> None:
    model = _model(
        "datatype",
        "datatype-external",
        "datatype-aliased",
        config={"nsMap": {"http://www.omg.org/spec/XMI/20131001": "xmi"}},
    )
    writer = _writer()
    root = model.create(
        "dt:Root",
        {"xmlns:foo": "http://datatypes", "xmlns:bar": "http://datatypes2"},
    )
    root.set("bounds", model.create("do:Rect", {"x": 100, "xsi:type": "other:Rect"}))

    xml = writer.to_xml(root)

    assert xml == (
        "<foo:root "
        'xmlns:foo="http://datatypes" '
        'xmlns:bar="http://datatypes2" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<foo:bounds xsi:type="bar:Rect" x="100" />'
        "</foo:root>"
    )


@pytest.mark.upstream(
    "moddle-xml/test/spec/writer.js", "via xmi:type / implicit / extension attributes"
)
def test_008_via_xmi_type_implicit_extension_attributes() -> None:
    model = _model(
        "datatype",
        "datatype-external",
        "datatype-aliased",
        config={"nsMap": {"http://www.omg.org/spec/XMI/20131001": "xmi"}},
    )
    writer = _writer()
    root = model.create("dt:Root")
    root.set(
        "xmiBounds",
        model.create("do:Rect", {"x": 100, "xmlns:f": "http://foo", "f:bar": "BAR"}),
    )

    xml = writer.to_xml(root)

    assert xml == (
        '<dt:root xmlns:dt="http://datatypes">'
        '<dt:xmiBounds xmlns:do="http://datatypes2" '
        'xmlns:xmi="http://www.omg.org/spec/XMI/20131001" '
        'xmlns:f="http://foo" xmi:type="do:Rect" '
        'x="100" f:bar="BAR" />'
        "</dt:root>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "via xsi:type / no namespace")
def test_009_via_xsi_type_no_namespace() -> None:
    model = _model(
        "datatype",
        "datatype-external",
        "datatype-aliased",
        config={"nsMap": {"http://www.omg.org/spec/XMI/20131001": "xmi"}},
    )
    writer = _writer()
    root = model.create("dt:Root", {":xmlns": "http://datatypes"})
    root.set("bounds", model.create("dt:Rect", {"y": 100}))

    xml = writer.to_xml(root)

    assert xml == '<root xmlns="http://datatypes"><bounds y="100" /></root>'


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "via xsi:type / other namespace")
def test_010_via_xsi_type_other_namespace() -> None:
    model = _model(
        "datatype",
        "datatype-external",
        "datatype-aliased",
        config={"nsMap": {"http://www.omg.org/spec/XMI/20131001": "xmi"}},
    )
    writer = _writer()
    root = model.create("dt:Root", {"xmlns:a": "http://datatypes"})
    root.set("bounds", model.create("dt:Rect", {"y": 100}))

    xml = writer.to_xml(root)

    assert xml == ('<a:root xmlns:a="http://datatypes"><a:bounds y="100" /></a:root>')


@pytest.mark.upstream(
    "moddle-xml/test/spec/writer.js", "via xsi:type / in collection / other namespace)"
)
def test_011_via_xsi_type_in_collection_other_namespace() -> None:
    model = _model(
        "datatype",
        "datatype-external",
        "datatype-aliased",
        config={"nsMap": {"http://www.omg.org/spec/XMI/20131001": "xmi"}},
    )
    writer = _writer()
    root = model.create("dt:Root")
    other_bounds = root.get("otherBounds")
    other_bounds.append(model.create("dt:Rect", {"y": 200}))
    other_bounds.append(model.create("do:Rect", {"x": 100}))

    xml = writer.to_xml(root)

    assert xml == (
        '<dt:root xmlns:dt="http://datatypes" '
        'xmlns:do="http://datatypes2" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dt:otherBounds y="200" />'
        '<dt:otherBounds xsi:type="do:Rect" x="100" />'
        "</dt:root>"
    )


@pytest.mark.upstream(
    "moddle-xml/test/spec/writer.js", "via xsi:type / in collection / type prefix"
)
def test_012_via_xsi_type_in_collection_type_prefix() -> None:
    model = _model(
        "datatype",
        "datatype-external",
        "datatype-aliased",
        config={"nsMap": {"http://www.omg.org/spec/XMI/20131001": "xmi"}},
    )
    writer = _writer()
    root = model.create("dt:Root")
    other_bounds = root.get("otherBounds")
    other_bounds.append(model.create("da:Rect", {"z": 200}))
    other_bounds.append(model.create("dt:Rect", {"y": 100}))

    xml = writer.to_xml(root)

    assert xml == (
        '<dt:root xmlns:dt="http://datatypes" '
        'xmlns:da="http://datatypes-aliased" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dt:otherBounds xsi:type="da:tRect" z="200" />'
        '<dt:otherBounds y="100" />'
        "</dt:root>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "via xsi:type / body property")
def test_013_via_xsi_type_body_property() -> None:
    model = _model("properties")
    writer = _writer()
    body = model.create("props:SimpleBody", {"body": "${ foo < bar }"})
    root = model.create("props:WithBody", {"someBody": body})

    xml = writer.to_xml(root)

    assert xml == (
        '<props:withBody xmlns:props="http://properties" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<props:someBody xsi:type="props:SimpleBody">'
        "${ foo &lt; bar }"
        "</props:someBody>"
        "</props:withBody>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "via xsi:type / body property / formated")
def test_014_via_xsi_type_body_property_formated() -> None:
    model = _model("properties")
    writer = _writer(format=True)
    body = model.create("props:SimpleBody", {"body": "${ foo < bar }"})
    root = model.create("props:WithBody", {"someBody": body})

    xml = writer.to_xml(root)

    assert xml == (
        '<props:withBody xmlns:props="http://properties" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
        "  <props:someBody "
        'xsi:type="props:SimpleBody">${ foo &lt; bar }</props:someBody>\n'
        "</props:withBody>\n"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "keep empty tag")
def test_015_keep_empty_tag() -> None:
    model = _model("replace")
    writer = _writer()
    simple = model.create("r:Extension", {"value": ""})

    xml = writer.to_xml(simple)

    assert xml == ('<r:Extension xmlns:r="http://replace"><r:value></r:value></r:Extension>')


# should export > attributes


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "with line breaks")
def test_016_with_line_breaks() -> None:
    model = _model("properties")
    writer = _writer()
    root = model.create("props:BaseWithId", {"id": "FOO\nBAR"})

    xml = writer.to_xml(root)

    assert xml == '<props:baseWithId xmlns:props="http://properties" id="FOO&#10;BAR" />'


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "inherited")
def test_017_inherited() -> None:
    model = _model("properties", "properties-extended")
    writer = _writer()
    root = model.create("ext:Root", {"id": "FOO"})

    xml = writer.to_xml(root)

    assert xml == '<ext:root xmlns:ext="http://extended" id="FOO" />'


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "extended")
def test_018_extended() -> None:
    model = _model("extension/base", "extension/custom")
    writer = _writer()
    root = model.create("b:SubRoot", {"customAttr": 1, "subAttr": "FOO", "ownAttr": "OWN"})

    xml = writer.to_xml(root)

    assert xml == (
        '<b:SubRoot xmlns:b="http://base" '
        'xmlns:c="http://custom" '
        'ownAttr="OWN" '
        'c:customAttr="1" '
        'subAttr="FOO" />'
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "ignore undefined attribute values")
def test_019_ignore_undefined_attribute_values() -> None:
    model = _model("properties")
    writer = _writer()
    root = model.create("props:BaseWithId", {"id": UNDEFINED})

    xml = writer.to_xml(root)

    assert xml == '<props:baseWithId xmlns:props="http://properties" />'


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "ignore null attribute values")
def test_020_ignore_null_attribute_values() -> None:
    model = _model("properties")
    writer = _writer()
    root = model.create("props:BaseWithId", {"id": None})

    xml = writer.to_xml(root)

    assert xml == '<props:baseWithId xmlns:props="http://properties" />'


# should export > simple properties


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "attribute")
def test_021_attribute() -> None:
    model = _model("properties")
    writer = _writer()
    attributes = model.create("props:Attributes", {"integerValue": 1000})

    xml = writer.to_xml(attributes)

    assert xml == ('<props:attributes xmlns:props="http://properties" integerValue="1000" />')


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "attribute, escaping special characters")
def test_022_attribute_escaping_special_characters() -> None:
    model = _model("properties")
    writer = _writer()
    complex_elem = model.create("props:Complex", {"id": "<>\n&"})

    xml = writer.to_xml(complex_elem)

    assert xml == ('<props:complex xmlns:props="http://properties" id="&#60;&#62;&#10;&#38;" />')


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "write integer property")
def test_023_write_integer_property() -> None:
    model = _model("properties")
    writer = _writer()
    root = model.create("props:SimpleBodyProperties", {"intValue": 5})

    xml = writer.to_xml(root)

    assert xml == (
        '<props:simpleBodyProperties xmlns:props="http://properties">'
        "<props:intValue>5</props:intValue>"
        "</props:simpleBodyProperties>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "write boolean property")
def test_024_write_boolean_property() -> None:
    model = _model("properties")
    writer = _writer()
    root = model.create("props:SimpleBodyProperties", {"boolValue": False})

    xml = writer.to_xml(root)

    assert xml == (
        '<props:simpleBodyProperties xmlns:props="http://properties">'
        "<props:boolValue>false</props:boolValue>"
        "</props:simpleBodyProperties>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "write boolean property, formated")
def test_025_write_boolean_property_formated() -> None:
    model = _model("properties")
    writer = _writer(format=True)
    root = model.create("props:SimpleBodyProperties", {"boolValue": False})

    xml = writer.to_xml(root)

    assert xml == (
        '<props:simpleBodyProperties xmlns:props="http://properties">\n'
        "  <props:boolValue>false</props:boolValue>\n"
        "</props:simpleBodyProperties>\n"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "write string isMany property")
def test_026_write_string_is_many_property() -> None:
    model = _model("properties")
    writer = _writer()
    root = model.create("props:SimpleBodyProperties", {"str": ["A", "B", "C"]})

    xml = writer.to_xml(root)

    assert xml == (
        '<props:simpleBodyProperties xmlns:props="http://properties">'
        "<props:str>A</props:str>"
        "<props:str>B</props:str>"
        "<props:str>C</props:str>"
        "</props:simpleBodyProperties>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "write string isMany property, formated")
def test_027_write_string_is_many_property_formated() -> None:
    model = _model("properties")
    writer = _writer(format=True)
    root = model.create("props:SimpleBodyProperties", {"str": ["A", "B", "C"]})

    xml = writer.to_xml(root)

    assert xml == (
        '<props:simpleBodyProperties xmlns:props="http://properties">\n'
        "  <props:str>A</props:str>\n"
        "  <props:str>B</props:str>\n"
        "  <props:str>C</props:str>\n"
        "</props:simpleBodyProperties>\n"
    )


# should export > embedded properties


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "single")
def test_028_embedded_single() -> None:
    model = _model("properties")
    writer = _writer()
    complex_count = model.create("props:ComplexCount", {"id": "ComplexCount_1"})
    embedding = model.create("props:Embedding", {"embeddedComplex": complex_count})

    xml = writer.to_xml(embedding)

    assert xml == (
        '<props:embedding xmlns:props="http://properties">'
        '<props:complexCount id="ComplexCount_1" />'
        "</props:embedding>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "property name")
def test_029_property_name() -> None:
    model = _model("properties")
    writer = _writer()
    property_value = model.create("props:BaseWithId", {"id": "PropertyValue"})
    container = model.create("props:WithProperty", {"propertyName": property_value})

    xml = writer.to_xml(container)

    assert xml == (
        '<props:withProperty xmlns:props="http://properties">'
        '<props:propertyName id="PropertyValue" />'
        "</props:withProperty>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "collection")
def test_030_embedded_collection() -> None:
    model = _model("properties")
    writer = _writer()
    root = model.create("props:Root")
    attributes = model.create("props:Attributes", {"id": "Attributes_1"})
    simple_body = model.create("props:SimpleBody")
    contained_collection = model.create("props:ContainedCollection")
    any_items = root.get("any")
    any_items.append(attributes)
    any_items.append(simple_body)
    any_items.append(contained_collection)

    xml = writer.to_xml(root)

    assert xml == (
        '<props:root xmlns:props="http://properties">'
        '<props:attributes id="Attributes_1" />'
        "<props:simpleBody />"
        "<props:containedCollection />"
        "</props:root>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "collection / different ns")
def test_031_collection_different_ns() -> None:
    model = _model("properties", "properties-extended")
    writer = _writer()
    root = model.create("ext:Root")
    attributes1 = model.create("props:Attributes", {"id": "Attributes_1"})
    attributes2 = model.create("props:Attributes", {"id": "Attributes_2"})
    extended_complex = model.create("ext:ExtendedComplex", {"numCount": 100})
    any_items = root.get("any")
    any_items.append(attributes1)
    any_items.append(attributes2)
    any_items.append(extended_complex)
    elements = root.get("elements")
    elements.append(model.create("ext:Base"))

    xml = writer.to_xml(root)

    assert xml == (
        '<ext:root xmlns:ext="http://extended" xmlns:props="http://properties">'
        '<props:attributes id="Attributes_1" />'
        '<props:attributes id="Attributes_2" />'
        '<ext:extendedComplex numCount="100" />'
        "<ext:base />"
        "</ext:root>"
    )


# should export > virtual properties


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should not serialize virtual property")
def test_032_should_not_serialize_virtual_property() -> None:
    model = _model("virtual")
    writer = _writer()
    root = model.create("virt:Root", {"child": model.create("virt:Child")})

    xml = writer.to_xml(root)

    assert xml == '<virt:Root xmlns:virt="http://virtual" />'


# should export > body text


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "write body text property")
def test_033_write_body_text_property() -> None:
    model = _model("properties")
    writer = _writer()
    root = model.create("props:SimpleBody", {"body": "textContent"})

    xml = writer.to_xml(root)

    assert xml == (
        '<props:simpleBody xmlns:props="http://properties">textContent</props:simpleBody>'
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "write encode body property")
def test_034_write_encode_body_property() -> None:
    model = _model("properties")
    writer = _writer()
    root = model.create("props:SimpleBody", {"body": '<h2>HTML&nbsp;"markup"</h2>'})

    xml = writer.to_xml(root)

    assert xml == (
        '<props:simpleBody xmlns:props="http://properties">'
        '&lt;h2&gt;HTML&amp;nbsp;"markup"&lt;/h2&gt;'
        "</props:simpleBody>"
    )


@pytest.mark.upstream(
    "moddle-xml/test/spec/writer.js", "write encode body property in subsequent calls"
)
def test_035_write_encode_body_property_in_subsequent_calls() -> None:
    model = _model("properties")
    writer = _writer()
    root1 = model.create("props:SimpleBody", {"body": "<>"})
    root2 = model.create("props:SimpleBody", {"body": "<>"})

    xml1 = writer.to_xml(root1)
    xml2 = writer.to_xml(root2)

    expected_xml = '<props:simpleBody xmlns:props="http://properties">&lt;&gt;</props:simpleBody>'

    assert xml1 == expected_xml
    assert xml2 == expected_xml


@pytest.mark.upstream(
    "moddle-xml/test/spec/writer.js", "write encode body property with special chars"
)
def test_036_write_encode_body_property_with_special_chars() -> None:
    model = _model("properties")
    writer = _writer()
    root = model.create("props:SimpleBody", {"body": "&\n<>\"'"})

    xml = writer.to_xml(root)

    assert xml == (
        '<props:simpleBody xmlns:props="http://properties">&amp;\n&lt;&gt;"\'</props:simpleBody>'
    )


# should export > alias


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "lowerCase")
def test_037_lower_case() -> None:
    model = _model("properties")
    writer = _writer()
    root = model.create("props:Root")

    xml = writer.to_xml(root)

    assert xml == '<props:root xmlns:props="http://properties" />'


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "none")
def test_038_none() -> None:
    model = _model("noalias")
    writer = _writer()
    root = model.create("na:Root")

    xml = writer.to_xml(root)

    assert xml == '<na:Root xmlns:na="http://noalias" />'


# should export > ns


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "single package")
def test_039_single_package() -> None:
    model = _model("properties")
    writer = _writer()
    root = model.create("props:Root")

    xml = writer.to_xml(root)

    assert xml == '<props:root xmlns:props="http://properties" />'


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "multiple packages")
def test_040_multiple_packages() -> None:
    model = _model("properties", "properties-extended")
    writer = _writer()
    root = model.create("props:Root")
    root.get("any").append(model.create("ext:ExtendedComplex"))

    xml = writer.to_xml(root)

    assert xml == (
        '<props:root xmlns:props="http://properties" xmlns:ext="http://extended">'
        "<ext:extendedComplex />"
        "</props:root>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "default ns")
def test_041_default_ns() -> None:
    model = _model("properties", "properties-extended")
    writer = _writer()
    root = model.create("props:Root", {":xmlns": "http://properties"})

    xml = writer.to_xml(root)

    assert xml == '<root xmlns="http://properties" />'


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "default ns / attributes")
def test_042_default_ns_attributes() -> None:
    model = _model("properties", "properties-extended")
    writer = _writer()
    root = model.create("props:Root", {":xmlns": "http://properties", "id": "Root"})
    any_items = root.get("any")
    any_items.append(model.create("ext:ExtendedComplex"))
    any_items.append(model.create("props:Attributes", {"id": "Attributes_2"}))

    xml = writer.to_xml(root)

    assert xml == (
        '<root xmlns="http://properties" xmlns:ext="http://extended" id="Root">'
        "<ext:extendedComplex />"
        '<attributes id="Attributes_2" />'
        "</root>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "default ns / extension attributes")
def test_043_default_ns_extension_attributes() -> None:
    model = _model("properties", "properties-extended")
    writer = _writer()
    root = model.create(
        "props:Root",
        {
            ":xmlns": "http://properties",
            "xmlns:foo": "http://fooo",
            "id": "Root",
            "foo:bar": "BAR",
        },
    )

    xml = writer.to_xml(root)

    assert xml == (
        '<root xmlns="http://properties" xmlns:foo="http://fooo" id="Root" foo:bar="BAR" />'
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "explicit ns / attributes")
def test_044_explicit_ns_attributes() -> None:
    model = _model("properties", "properties-extended")
    writer = _writer()
    root = model.create("props:Root", {"xmlns:foo": "http://properties", "id": "Root"})

    xml = writer.to_xml(root)

    assert xml == '<foo:root xmlns:foo="http://properties" id="Root" />'


# should export > reference


def test_045_reference_single() -> None:
    model = _model("properties")
    writer = _writer()
    complex_elem = model.create("props:Complex", {"id": "Complex_1"})
    referencing_single = model.create(
        "props:ReferencingSingle", {"referencedComplex": complex_elem}
    )

    xml = writer.to_xml(referencing_single)

    assert xml == (
        '<props:referencingSingle xmlns:props="http://properties" referencedComplex="Complex_1" />'
    )


def test_046_reference_collection() -> None:
    model = _model("properties")
    writer = _writer()
    complex_count = model.create("props:ComplexCount", {"id": "ComplexCount_1"})
    complex_nesting = model.create("props:ComplexNesting", {"id": "ComplexNesting_1"})
    referencing_collection = model.create(
        "props:ReferencingCollection", {"references": [complex_count, complex_nesting]}
    )

    xml = writer.to_xml(referencing_collection)

    assert xml == (
        '<props:referencingCollection xmlns:props="http://properties">'
        "<props:references>ComplexCount_1</props:references>"
        "<props:references>ComplexNesting_1</props:references>"
        "</props:referencingCollection>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "attribute collection")
def test_047_attribute_collection() -> None:
    model = _model("properties")
    writer = _writer()
    complex_count = model.create("props:ComplexCount", {"id": "ComplexCount_1"})
    complex_nesting = model.create("props:ComplexNesting", {"id": "ComplexNesting_1"})
    attr_reference_collection = model.create(
        "props:AttributeReferenceCollection", {"refs": [complex_count, complex_nesting]}
    )

    xml = writer.to_xml(attr_reference_collection)

    assert xml == (
        '<props:attributeReferenceCollection xmlns:props="http://properties" '
        'refs="ComplexCount_1 ComplexNesting_1" />'
    )


# should export > redefined / replaced properties


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "redefined properties")
def test_048_redefined_properties() -> None:
    model = _model("redefine")
    writer = _writer()
    element = model.create("r:Extension", {"id": 1, "name": "FOO", "value": "BAR"})

    xml = writer.to_xml(element)

    assert xml == (
        '<r:Extension xmlns:r="http://redefine">'
        "<r:id>1</r:id>"
        "<r:name>FOO</r:name>"
        "<r:value>BAR</r:value>"
        "</r:Extension>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "replaced properties")
def test_049_replaced_properties() -> None:
    model = _model("replace")
    writer = _writer()
    element = model.create("r:Extension", {"id": 1, "name": "FOO", "value": "BAR"})

    xml = writer.to_xml(element)

    assert xml == (
        '<r:Extension xmlns:r="http://replace">'
        "<r:name>FOO</r:name>"
        "<r:value>BAR</r:value>"
        "<r:id>1</r:id>"
        "</r:Extension>"
    )


# extension handling > attributes


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should write xsi:schemaLocation")
def test_050_write_xsi_schema_location() -> None:
    model = _model("extensions")
    writer = _writer()
    root = model.create("e:Root", {"xsi:schemaLocation": "http://fooo ./foo.xsd"})

    xml = writer.to_xml(root)

    assert xml == (
        '<e:root xmlns:e="http://extensions" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:schemaLocation="http://fooo ./foo.xsd" />'
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should write extension attributes")
def test_051_write_extension_attributes() -> None:
    model = _model("extensions")
    writer = _writer()
    root = model.create("e:Root", {"xmlns:foo": "http://fooo", "foo:bar": "BAR"})

    xml = writer.to_xml(root)

    assert xml == ('<e:root xmlns:e="http://extensions" xmlns:foo="http://fooo" foo:bar="BAR" />')


# extension handling > elements


@pytest.mark.upstream(
    "moddle-xml/test/spec/writer.js", "should write self-closing extension elements"
)
def test_052_write_self_closing_extension_elements() -> None:
    model = _model("extensions")
    writer = _writer()
    meta1 = model.create_any("other:meta", "http://other", {"key": "FOO", "value": "BAR"})
    meta2 = model.create_any("other:meta", "http://other", {"key": "BAZ", "value": "FOOBAR"})
    root = model.create("e:Root", {"id": "FOO", "extensions": [meta1, meta2]})

    xml = writer.to_xml(root)

    assert xml == (
        '<e:root xmlns:e="http://extensions" xmlns:other="http://other">'
        "<e:id>FOO</e:id>"
        '<other:meta key="FOO" value="BAR" />'
        '<other:meta key="BAZ" value="FOOBAR" />'
        "</e:root>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should write unqualified element")
def test_053_write_unqualified_element() -> None:
    model = _model("extensions")
    writer = _writer()
    root = model.create_any("root", None, {"key": "FOO", "value": "BAR"})  # type: ignore[arg-type]

    xml = writer.to_xml(root)

    assert xml == '<root key="FOO" value="BAR" />'


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should write extension element body")
def test_054_write_extension_element_body() -> None:
    model = _model("extensions")
    writer = _writer()
    note = model.create_any("other:note", "http://other", {"$body": "a note"})
    root = model.create("e:Root", {"id": "FOO", "extensions": [note]})

    xml = writer.to_xml(root)

    assert xml == (
        '<e:root xmlns:e="http://extensions" xmlns:other="http://other">'
        "<e:id>FOO</e:id>"
        "<other:note>"
        "a note"
        "</other:note>"
        "</e:root>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should write nested extension element")
def test_055_write_nested_extension_element() -> None:
    model = _model("extensions")
    writer = _writer()
    meta1 = model.create_any("other:meta", "http://other", {"key": "k1", "value": "v1"})
    meta2 = model.create_any("other:meta", "http://other", {"key": "k2", "value": "v2"})
    additional_note = model.create_any(
        "other:additionalNote", "http://other", {"$body": "this is some text"}
    )
    nested_meta = model.create_any(
        "other:nestedMeta", "http://other", {"$children": [meta1, meta2, additional_note]}
    )
    root = model.create("e:Root", {"id": "FOO", "extensions": [nested_meta]})

    xml = writer.to_xml(root)

    assert xml == (
        '<e:root xmlns:e="http://extensions" xmlns:other="http://other">'
        "<e:id>FOO</e:id>"
        "<other:nestedMeta>"
        '<other:meta key="k1" value="v1" />'
        '<other:meta key="k2" value="v2" />'
        "<other:additionalNote>"
        "this is some text"
        "</other:additionalNote>"
        "</other:nestedMeta>"
        "</e:root>"
    )


# qualified extensions


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should write typed extension property")
def test_056_write_typed_extension_property() -> None:
    model = _model("extension/base", "extension/custom")
    writer = _writer()
    custom_generic = model.create("c:CustomGeneric", {"count": 10})
    root = model.create("b:Root", {"generic": custom_generic})

    xml = writer.to_xml(root)

    assert xml == (
        '<b:Root xmlns:b="http://base" xmlns:c="http://custom">'
        '<c:CustomGeneric count="10" />'
        "</b:Root>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should write typed extension attribute")
def test_057_write_typed_extension_attribute() -> None:
    model = _model("extension/base", "extension/custom")
    writer = _writer()
    root = model.create("b:Root", {"customAttr": 666})

    xml = writer.to_xml(root)

    assert xml == ('<b:Root xmlns:b="http://base" xmlns:c="http://custom" c:customAttr="666" />')


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should write generic collection")
def test_058_write_generic_collection() -> None:
    model = _model("extension/base", "extension/custom")
    writer = _writer()
    property1 = model.create("c:Property", {"key": "foo", "value": "FOO"})
    property2 = model.create("c:Property", {"key": "bar", "value": "BAR"})
    any_elem = model.create_any("other:Xyz", "http://other", {"$body": "content"})
    root = model.create("b:Root", {"genericCollection": [property1, property2, any_elem]})

    xml = writer.to_xml(root)

    assert xml == (
        '<b:Root xmlns:b="http://base" xmlns:c="http://custom" '
        'xmlns:other="http://other">'
        '<c:Property key="foo" value="FOO" />'
        '<c:Property key="bar" value="BAR" />'
        "<other:Xyz>content</other:Xyz>"
        "</b:Root>"
    )


# namespace declarations > should deconflict namespace prefixes


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "on nested Any")
def test_059_deconflict_on_nested_any() -> None:
    model = _model("extensions")
    writer = _writer()
    root = model.create(
        "e:Root",
        {"extensions": [model.create_any("e:foo", "http://not-extensions", {"foo": "BAR"})]},
    )

    xml = writer.to_xml(root)

    assert xml == (
        '<e:root xmlns:e="http://extensions" xmlns:e_1="http://not-extensions">'
        '<e_1:foo foo="BAR" />'
        "</e:root>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "on explicitly added namespace")
def test_060_deconflict_on_explicitly_added_namespace() -> None:
    model = _model("extensions")
    writer = _writer()
    root = model.create("e:Root", {"xmlns:e": "http://not-extensions"})

    xml = writer.to_xml(root)

    assert xml == ('<e_1:root xmlns:e_1="http://extensions" xmlns:e="http://not-extensions" />')


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "on explicitly added namespace + Any")
def test_061_deconflict_on_explicitly_added_namespace_plus_any() -> None:
    model = _model("extensions")
    writer = _writer()
    root = model.create(
        "e:Root",
        {
            "xmlns:e": "http://not-extensions",
            "extensions": [model.create_any("e:foo", "http://not-extensions", {"foo": "BAR"})],
        },
    )

    xml = writer.to_xml(root)

    assert xml == (
        '<e_1:root xmlns:e_1="http://extensions" xmlns:e="http://not-extensions">'
        '<e:foo foo="BAR" />'
        "</e_1:root>"
    )


# namespace declarations


@pytest.mark.upstream(
    "moddle-xml/test/spec/writer.js", "should write manually added custom namespace"
)
def test_062_write_manually_added_custom_namespace() -> None:
    model = _model("extensions")
    writer = _writer()
    root = model.create("e:Root", {"xmlns:foo": "http://fooo"})

    xml = writer.to_xml(root)

    assert xml == ('<e:root xmlns:e="http://extensions" xmlns:foo="http://fooo" />')


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should ignore unknown namespace prefix")
def test_063_ignore_unknown_namespace_prefix() -> None:
    model = _model("extensions")
    writer = _writer()
    root = model.create("e:Root", {"foo:bar": "BAR"})

    xml = writer.to_xml(root)

    assert xml == '<e:root xmlns:e="http://extensions" />'


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should write custom")
def test_064_write_custom() -> None:
    model = _model("extensions")
    writer = _writer()
    root = model.create(
        "e:Root",
        {
            ":xmlns": "http://extensions",
            "extensions": [
                model.create_any(
                    "bar:bar",
                    "http://bar",
                    {
                        "xmlns:bar": "http://bar",
                        "$children": [
                            model.create_any(
                                "other:child",
                                "http://other",
                                {"xmlns:other": "http://other", "b": "B"},
                            )
                        ],
                    },
                ),
                model.create_any(
                    "ns0:foo",
                    "http://foo",
                    {
                        "xmlns": "http://foo",
                        "$children": [model.create_any("ns0:child", "http://foo", {"a": "A"})],
                    },
                ),
            ],
        },
    )

    xml = writer.to_xml(root)

    assert xml == (
        '<root xmlns="http://extensions">'
        '<bar:bar xmlns:bar="http://bar">'
        '<other:child xmlns:other="http://other" b="B" />'
        "</bar:bar>"
        '<foo xmlns="http://foo">'
        '<child a="A" />'
        "</foo>"
        "</root>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should write nested custom")
def test_065_write_nested_custom() -> None:
    model = _model("extensions")
    writer = _writer()
    root = model.create(
        "e:Root",
        {
            ":xmlns": "http://extensions",
            "extensions": [
                model.create_any(
                    "bar:bar",
                    "http://bar",
                    {"xmlns:bar": "http://bar", "bar:attr": "ATTR"},
                )
            ],
        },
    )

    xml = writer.to_xml(root)

    assert xml == (
        '<root xmlns="http://extensions"><bar:bar xmlns:bar="http://bar" attr="ATTR" /></root>'
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should strip redundant nested custom")
def test_066_strip_redundant_nested_custom() -> None:
    model = _model("extensions")
    writer = _writer()
    root = model.create(
        "e:Root",
        {
            ":xmlns": "http://extensions",
            "xmlns:bar": "http://bar",
            "extensions": [
                model.create_any(
                    "bar:bar",
                    "http://bar",
                    {"xmlns:bar": "http://bar", "bar:attr": "ATTR"},
                )
            ],
        },
    )

    xml = writer.to_xml(root)

    assert xml == (
        '<root xmlns="http://extensions" xmlns:bar="http://bar"><bar:bar attr="ATTR" /></root>'
    )


@pytest.mark.upstream(
    "moddle-xml/test/spec/writer.js", "should strip different prefix nested custom"
)
def test_067_strip_different_prefix_nested_custom() -> None:
    model = _model("extensions")
    writer = _writer()
    root = model.create(
        "e:Root",
        {
            ":xmlns": "http://extensions",
            "xmlns:otherBar": "http://bar",
            "xmlns:otherFoo": "http://foo",
            "extensions": [
                model.create_any(
                    "bar:bar",
                    "http://bar",
                    {
                        "xmlns:bar": "http://bar",
                        "xmlns:foo": "http://foo",
                        "bar:attr": "ATTR",
                        "foo:attr": "FOO_ATTR",
                    },
                )
            ],
        },
    )

    xml = writer.to_xml(root)

    assert xml == (
        '<root xmlns="http://extensions" xmlns:otherBar="http://bar" '
        'xmlns:otherFoo="http://foo">'
        '<otherBar:bar attr="ATTR" otherFoo:attr="FOO_ATTR" />'
        "</root>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should write normalized custom")
def test_068_write_normalized_custom() -> None:
    model = _model("extensions")
    writer = _writer()
    root = model.create(
        "e:Root",
        {
            ":xmlns": "http://extensions",
            "xmlns:otherBar": "http://bar",
            "extensions": [model.create_any("bar:bar", "http://bar", {"bar:attr": "ATTR"})],
        },
    )

    xml = writer.to_xml(root)

    assert xml == (
        '<root xmlns="http://extensions" xmlns:otherBar="http://bar">'
        '<otherBar:bar attr="ATTR" />'
        "</root>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should write wellknown")
def test_069_write_wellknown() -> None:
    model = _model("properties", "properties-extended")
    writer = _writer()
    root = model.create(
        "props:Root",
        {
            ":xmlns": "http://properties",
            "any": [model.create("ext:ExtendedComplex", {":xmlns": "http://extended"})],
        },
    )

    xml = writer.to_xml(root)

    assert xml == (
        '<root xmlns="http://properties"><extendedComplex xmlns="http://extended" /></root>'
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should write only actually exposed")
def test_070_write_only_actually_exposed() -> None:
    model = _model("properties", "properties-extended")
    writer = _writer()
    root = model.create(
        "ext:Root",
        {
            ":xmlns": "http://extended",
            "id": "ROOT",
            "any": [model.create("props:Complex", {":xmlns": "http://properties"})],
        },
    )

    xml = writer.to_xml(root)

    assert xml == (
        '<root xmlns="http://extended" id="ROOT"><complex xmlns="http://properties" /></root>'
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should write xsi:type namespaces")
def test_071_write_xsi_type_namespaces() -> None:
    model = _model("datatype", "datatype-external", "datatype-aliased")
    writer = _writer()
    root = model.create(
        "da:Root",
        {
            "xmlns:a": "http://datatypes-aliased",
            "otherBounds": [model.create("dt:Rect", {":xmlns": "http://datatypes", "y": 100})],
        },
    )

    xml = writer.to_xml(root)

    assert xml == (
        '<a:Root xmlns:a="http://datatypes-aliased">'
        '<otherBounds xmlns="http://datatypes" y="100" />'
        "</a:Root>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should strip unused global")
def test_072_writer_strip_unused_global() -> None:
    model = _model("properties", "properties-extended")
    writer = _writer()
    root = model.create(
        "ext:Root",
        {
            ":xmlns": "http://extended",
            "id": "Root",
            "xmlns:props": "http://properties",
            "any": [model.create("props:Base", {":xmlns": "http://properties"})],
        },
    )

    xml = writer.to_xml(root)

    assert xml == (
        '<root xmlns="http://extended" id="Root"><base xmlns="http://properties" /></root>'
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should strip xml namespace")
def test_073_strip_xml_namespace() -> None:
    model = _model("extensions")
    writer = _writer()
    root = model.create(
        "e:Root",
        {
            "xml:lang": "de",
            "extensions": [model.create_any("bar:bar", "http://bar", {"xml:lang": "en"})],
        },
    )

    xml = writer.to_xml(root)

    assert xml == (
        '<e:root xmlns:e="http://extensions" xmlns:bar="http://bar" xml:lang="de">'
        '<bar:bar xml:lang="en" />'
        "</e:root>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should keep local override")
def test_074_keep_local_override() -> None:
    model = _model("properties", "properties-extended")
    writer = _writer()
    root = model.create(
        "props:ComplexNesting",
        {
            "xmlns:root": "http://properties",
            "id": "ComplexNesting",
            "nested": [
                model.create(
                    "props:ComplexNesting",
                    {
                        ":xmlns": "http://properties",
                        "nested": [
                            model.create(
                                "props:ComplexNesting",
                                {
                                    "nested": [
                                        model.create(
                                            "props:ComplexNesting",
                                            {"xmlns:foo": "http://properties"},
                                        )
                                    ]
                                },
                            )
                        ],
                    },
                )
            ],
        },
    )

    xml = writer.to_xml(root)

    assert xml == (
        '<root:complexNesting xmlns:root="http://properties" id="ComplexNesting">'
        '<complexNesting xmlns="http://properties">'
        "<complexNesting>"
        '<foo:complexNesting xmlns:foo="http://properties" />'
        "</complexNesting>"
        "</complexNesting>"
        "</root:complexNesting>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should reuse global namespace")
def test_075_writer_reuse_global_namespace() -> None:
    model = _model("properties", "properties-extended")
    writer = _writer()
    root = model.create(
        "props:Root",
        {
            "xmlns:props": "http://properties",
            "xmlns:ext": "http://extended",
            "any": [
                model.create(
                    "props:ComplexNesting",
                    {
                        ":xmlns": "http://properties",
                        "nested": [model.create("ext:ExtendedComplex", {"numCount": 1})],
                    },
                )
            ],
        },
    )

    xml = writer.to_xml(root)

    assert xml == (
        '<props:root xmlns:props="http://properties" xmlns:ext="http://extended">'
        '<complexNesting xmlns="http://properties">'
        '<ext:extendedComplex numCount="1" />'
        "</complexNesting>"
        "</props:root>"
    )


# custom namespace mapping


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should write explicitly remapped xsi:type")
def test_076_write_explicitly_remapped_xsi_type() -> None:
    model = _model(
        "datatype",
        "datatype-external",
        config={"nsMap": {"http://www.omg.org/spec/XMI/20131001": "xmi"}},
    )
    writer = _writer()
    root = model.create("dt:Root")
    root.set(
        "bounds",
        model.create(
            "do:Rect",
            {"x": 100, "xmlns:foo": "http://www.w3.org/2001/XMLSchema-instance"},
        ),
    )

    xml = writer.to_xml(root)

    assert xml == (
        '<dt:root xmlns:dt="http://datatypes">'
        '<dt:bounds xmlns:do="http://datatypes2" '
        'xmlns:foo="http://www.w3.org/2001/XMLSchema-instance" '
        'foo:type="do:Rect" '
        'x="100" />'
        "</dt:root>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/writer.js", "should write explicitly remapped xmi:type")
def test_077_write_explicitly_remapped_xmi_type() -> None:
    model = _model(
        "datatype",
        "datatype-external",
        config={"nsMap": {"http://www.omg.org/spec/XMI/20131001": "xmi"}},
    )
    writer = _writer()
    root = model.create("dt:Root")
    root.set(
        "xmiBounds",
        model.create(
            "do:Rect",
            {"x": 100, "xmlns:foo": "http://www.omg.org/spec/XMI/20131001"},
        ),
    )

    xml = writer.to_xml(root)

    assert xml == (
        '<dt:root xmlns:dt="http://datatypes">'
        '<dt:xmiBounds xmlns:do="http://datatypes2" '
        'xmlns:foo="http://www.omg.org/spec/XMI/20131001" '
        'foo:type="do:Rect" '
        'x="100" />'
        "</dt:root>"
    )
