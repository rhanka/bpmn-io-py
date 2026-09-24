"""Ported moddle-xml reader cases (Lot 5).

Transcribes every ``moddle-xml/test/spec/reader.js`` ``it()`` title: one test
per claim (88 claims; the two titles the file lists twice — ``single`` and
``collection`` — are claimed once per occurrence, on their distinct bodies).
Verification mirrors the upstream assertions: ``jsonEqual`` becomes
``json_equal``, ``eql`` becomes ``==``, ``match`` becomes ``re.search`` and
promise rejections become ``pytest.raises(ParseError)``. Only the public
``bpmn_io.moddle_xml`` API (``Reader``, ``ParseError``) is used.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from bpmn_io._js import UNDEFINED
from bpmn_io.moddle import Moddle
from bpmn_io.moddle_xml import ParseError, Reader
from tests._matchers import json_equal

FIXTURES = Path(__file__).resolve().parent.parent / "upstream" / "moddle-xml" / "test" / "fixtures"
MODEL_FIXTURES = FIXTURES / "model"


def _load(*names: str) -> list[dict[str, Any]]:
    """Load model fixture packages by name."""
    return [
        json.loads((MODEL_FIXTURES / f"{name}.json").read_text(encoding="utf-8")) for name in names
    ]


def _model(*names: str, config: dict[str, Any] | None = None) -> Moddle:
    """Build a model from fixture packages (strict, as the upstream helper)."""
    return Moddle(_load(*names), config)


def _reader(*names: str) -> tuple[Moddle, Reader]:
    """Build a ``properties``-style model and its reader."""
    model = _model(*names)
    return model, Reader(model)


# api


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should resolve with context")
def test_001_resolve_with_context() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ComplexAttrs")

    xml = '<props:complexAttrs xmlns:props="http://properties"></props:complexAttrs>'

    result = reader.from_xml(xml, root_handler)

    assert result.root_element is not None
    assert result.warnings == []
    assert result.references == []
    assert result.elements_by_id == {}


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should reject with context")
def test_002_reject_with_context() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ComplexAttrs")

    with pytest.raises(ParseError, match=re.escape("unparsable content")) as exc_info:
        reader.from_xml("this-is-garbage", root_handler)

    assert exc_info.value.message
    assert exc_info.value.warnings == []


# should import > data types


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "simple")
def test_003_simple() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ComplexAttrs")

    xml = (
        '<props:complexAttrs xmlns:props="http://properties">'
        '<props:attrs integerValue="10" />'
        "</props:complexAttrs>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "props:ComplexAttrs",
            "attrs": {"$type": "props:Attributes", "integerValue": 10},
        },
    )


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "simple / xsi:type")
def test_004_simple_xsi_type() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ComplexAttrs")

    xml = (
        '<props:complexAttrs xmlns:props="http://properties" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<props:attrs xsi:type="props:SubAttributes" integerValue="10" />'
        "</props:complexAttrs>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "props:ComplexAttrs",
            "attrs": {"$type": "props:SubAttributes", "integerValue": 10},
        },
    )


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "simple / xmi:type")
def test_005_simple_xmi_type() -> None:
    _model_holder, reader = _reader("datatype", "datatype-external")
    root_handler = reader.handler("dt:Root")

    xml = (
        '<dt:root xmlns:dt="http://datatypes" xmlns:do="http://datatypes2" '
        'xmlns:xmi="http://www.omg.org/spec/XMI/20131001">'
        '<dt:xmiBounds xmi:type="dt:Rect" y="100" />'
        "</dt:root>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {"$type": "dt:Root", "xmiBounds": {"$type": "dt:Rect", "y": 100}},
    )


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "simple / default xml ns")
def test_006_simple_default_xml_ns() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ComplexAttrs")

    xml = (
        '<props:complexAttrs xmlns:props="http://properties" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<props:attrs xsi:type="props:SubAttributes" integerValue="10" />'
        "</props:complexAttrs>"
    )

    result = reader.from_xml(xml, root_handler)

    assert result.warnings == []
    assert result.root_element is not None


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "default <xml> namespace")
def test_007_default_xml_namespace() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ComplexAttrs")

    xml = '<complexAttrs xmlns="http://properties" xml:lang="en" />'

    result = reader.from_xml(xml, root_handler)

    assert result.warnings == []
    assert result.root_element is not None


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "default <xml> namespace / any element")
def test_008_default_xml_namespace_any_element() -> None:
    _model_holder, reader = _reader("extensions")
    root_handler = reader.handler("e:Root")

    xml = (
        '<e:root xmlns:e="http://extensions" xmlns:bar="http://bar" xml:lang="de">'
        '<bar:bar xml:lang="en" />'
        "</e:root>"
    )

    result = reader.from_xml(xml, root_handler)

    assert result.warnings == []
    assert result.root_element is not None
    assert result.root_element.attrs_.get("xml:lang") == "de"
    assert json_equal(
        result.root_element,
        {
            "$type": "e:Root",
            "extensions": [{"$type": "bar:bar", "xml:lang": "en"}],
        },
    )


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "simple / xsi:type / default ns")
def test_009_simple_xsi_type_default_ns() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ComplexAttrs")

    xml = (
        '<complexAttrs xmlns="http://properties" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<attrs xsi:type="SubAttributes" integerValue="10" />'
        "</complexAttrs>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "props:ComplexAttrs",
            "attrs": {"$type": "props:SubAttributes", "integerValue": 10},
        },
    )


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "simple / xsi:type / different ns prefix")
def test_010_simple_xsi_type_different_ns_prefix() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ComplexAttrs")

    xml = (
        '<a:complexAttrs xmlns:a="http://properties" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<a:attrs xsi:type="a:SubAttributes" integerValue="10" />'
        "</a:complexAttrs>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "props:ComplexAttrs",
            "attrs": {"$type": "props:SubAttributes", "integerValue": 10},
        },
    )


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "collection / no xsi:type")
def test_011_collection_no_xsi_type() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ComplexAttrsCol")

    xml = (
        '<props:complexAttrsCol xmlns:props="http://properties">'
        '<props:attrs integerValue="10" />'
        '<props:attrs booleanValue="true" />'
        "</props:complexAttrsCol>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "props:ComplexAttrsCol",
            "attrs": [
                {"$type": "props:Attributes", "integerValue": 10},
                {"$type": "props:Attributes", "booleanValue": True},
            ],
        },
    )


@pytest.mark.upstream(
    "moddle-xml/test/spec/reader.js", "collection / xsi:type / from other namespace"
)
def test_012_collection_xsi_type_other_namespace() -> None:
    _model_holder, reader = _reader("datatype", "datatype-external")
    root_handler = reader.handler("dt:Root")

    xml = (
        '<dt:root xmlns:dt="http://datatypes" xmlns:do="http://datatypes2" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dt:otherBounds xsi:type="dt:Rect" y="100" />'
        '<dt:otherBounds xsi:type="do:Rect" x="200" />'
        "</dt:root>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "dt:Root",
            "otherBounds": [
                {"$type": "dt:Rect", "y": 100},
                {"$type": "do:Rect", "x": 200},
            ],
        },
    )


@pytest.mark.upstream(
    "moddle-xml/test/spec/reader.js", "collection / xmi:type / from other namespace"
)
def test_013_collection_xmi_type_other_namespace() -> None:
    _model_holder, reader = _reader("datatype", "datatype-external")
    root_handler = reader.handler("dt:Root")

    xml = (
        '<dt:root xmlns:dt="http://datatypes" xmlns:do="http://datatypes2" '
        'xmlns:xmi="http://www.omg.org/spec/XMI/20131001">'
        '<dt:xmiManyBounds xmi:type="dt:Rect" y="100" />'
        '<dt:xmiManyBounds xmi:type="do:Rect" x="200" />'
        "</dt:root>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "dt:Root",
            "xmiManyBounds": [
                {"$type": "dt:Rect", "y": 100},
                {"$type": "do:Rect", "x": 200},
            ],
        },
    )


@pytest.mark.upstream(
    "moddle-xml/test/spec/reader.js", "collection / xsi:type / from other namespace / default ns)"
)
def test_014_collection_xsi_type_other_namespace_default_ns() -> None:
    _model_holder, reader = _reader("datatype", "datatype-external")
    root_handler = reader.handler("dt:Root")

    xml = (
        '<root xmlns="http://datatypes" xmlns:do="http://datatypes2" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<otherBounds xsi:type="Rect" y="100" />'
        '<otherBounds xsi:type="do:Rect" x="200" />'
        "</root>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "dt:Root",
            "otherBounds": [
                {"$type": "dt:Rect", "y": 100},
                {"$type": "do:Rect", "x": 200},
            ],
        },
    )


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "collection / xsi:type / type alias")
def test_015_collection_xsi_type_alias() -> None:
    _model_holder, reader = _reader("datatype", "datatype-aliased")
    root_handler = reader.handler("dt:Root")

    xml = (
        '<root xmlns="http://datatypes" xmlns:da="http://datatypes-aliased" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<otherBounds xsi:type="dt:Rect" y="100" />'
        '<otherBounds xsi:type="da:tRect" z="200" />'
        "</root>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "dt:Root",
            "otherBounds": [
                {"$type": "dt:Rect", "y": 100},
                {"$type": "da:Rect", "z": 200},
            ],
        },
    )


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "single")
def test_016_unknown_type_single() -> None:
    _model_holder, reader = _reader("datatype")
    root_handler = reader.handler("dt:Root")

    xml = (
        '<root xmlns="http://datatypes" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<bounds xsi:type="Unknown" y="100" />'
        "</root>"
    )

    with pytest.raises(
        ParseError, match=re.escape("unparsable content <bounds> detected")
    ) as exc_info:
        reader.from_xml(xml, root_handler)

    assert "unknown type <dt:Unknown>" in exc_info.value.message


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "single / ns type")
def test_017_unknown_type_single_ns_type() -> None:
    _model_holder, reader = _reader("datatype")
    root_handler = reader.handler("dt:Root")

    xml = (
        '<root xmlns="http://datatypes" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<bounds xsi:type="other:Unknown" y="100" />'
        "</root>"
    )

    with pytest.raises(
        ParseError, match=re.escape("unparsable content <bounds> detected")
    ) as exc_info:
        reader.from_xml(xml, root_handler)

    assert "unknown type <other:Unknown>" in exc_info.value.message


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "collection")
def test_018_unknown_type_collection() -> None:
    _model_holder, reader = _reader("datatype")
    root_handler = reader.handler("dt:Root")

    xml = (
        '<root xmlns="http://datatypes" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<otherBounds xsi:type="Unknown" y="100" />'
        "</root>"
    )

    with pytest.raises(
        ParseError, match=re.escape("unparsable content <otherBounds> detected")
    ) as exc_info:
        reader.from_xml(xml, root_handler)

    assert "unknown type <dt:Unknown>" in exc_info.value.message


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "generic, non-ns elements")
def test_019_generic_non_ns_elements() -> None:
    _model_holder, reader = _reader("extension/base")
    root_handler = reader.handler("b:Root")

    xml = '<b:Root xmlns:b="http://base"><Any foo="BAR" /></b:Root>'

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {"$type": "b:Root", "generic": {"$type": "Any", "foo": "BAR"}},
    )


# should import > attributes


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "with special characters")
def test_020_with_special_characters() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:SimpleBodyProperties")

    xml = (
        '<props:simpleBodyProperties xmlns:props="http://properties" str="&#60;&#62;&#10;&#38;" />'
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {"$type": "props:SimpleBodyProperties", "str": "<>\n&"},
    )


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "inherited")
def test_021_inherited() -> None:
    _model_holder, reader = _reader("properties", "properties-extended")
    root_handler = reader.handler("ext:Root")

    result = reader.from_xml('<ext:root xmlns:ext="http://extended" id="FOO" />', root_handler)

    assert json_equal(result.root_element, {"$type": "ext:Root", "id": "FOO"})


# should import > simple nested properties


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "parse int property")
def test_022_parse_int_property() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:SimpleBodyProperties")

    xml = (
        '<props:simpleBodyProperties xmlns:props="http://properties">'
        "<props:intValue>5</props:intValue>"
        "</props:simpleBodyProperties>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(result.root_element, {"$type": "props:SimpleBodyProperties", "intValue": 5})


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "parse boolean property")
def test_023_parse_boolean_property() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:SimpleBodyProperties")

    xml = (
        '<props:simpleBodyProperties xmlns:props="http://properties">'
        "<props:boolValue>false</props:boolValue>"
        "</props:simpleBodyProperties>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element, {"$type": "props:SimpleBodyProperties", "boolValue": False}
    )


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "parse string isMany prooperty")
def test_024_parse_string_is_many_property() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:SimpleBodyProperties")

    xml = (
        '<props:simpleBodyProperties xmlns:props="http://properties">'
        "<props:str>A</props:str>"
        "<props:str>B</props:str>"
        "<props:str>C</props:str>"
        "</props:simpleBodyProperties>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {"$type": "props:SimpleBodyProperties", "str": ["A", "B", "C"]},
    )


@pytest.mark.upstream(
    "moddle-xml/test/spec/reader.js", "should not discard value with an empty tag"
)
def test_025_not_discard_value_with_empty_tag() -> None:
    _model_holder, reader = _reader("replace")
    root_handler = reader.handler("r:Extension")

    xml = '<r:Extension xmlns:r="http://replace"><r:value></r:value></r:Extension>'

    result = reader.from_xml(xml, root_handler)

    assert json_equal(result.root_element, {"$type": "r:Extension", "value": ""})


# should import > body text


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "parse body text property")
def test_026_parse_body_text_property() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:SimpleBody")

    xml = '<props:simpleBody xmlns:props="http://properties">textContent</props:simpleBody>'

    result = reader.from_xml(xml, root_handler)

    assert json_equal(result.root_element, {"$type": "props:SimpleBody", "body": "textContent"})


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "parse body text property / encoded")
def test_027_parse_body_text_property_encoded() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:SimpleBody")

    xml = (
        '<props:simpleBody xmlns:props="http://properties">'
        "&lt; 10, &gt; 20, &amp;nbsp;"
        "</props:simpleBody>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element, {"$type": "props:SimpleBody", "body": "< 10, > 20, &nbsp;"}
    )


@pytest.mark.upstream(
    "moddle-xml/test/spec/reader.js", "parse body text property / trimmed whitespace"
)
def test_028_parse_body_text_property_trimmed_whitespace() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:SimpleBody")

    xml = '<props:simpleBody xmlns:props="http://properties">    </props:simpleBody>'

    result = reader.from_xml(xml, root_handler)

    assert json_equal(result.root_element, {"$type": "props:SimpleBody"})


@pytest.mark.upstream(
    "moddle-xml/test/spec/reader.js", "parse body CDATA property / trimmed whitespace"
)
def test_029_parse_body_cdata_property_trimmed_whitespace() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:SimpleBody")

    xml = (
        '<props:simpleBody xmlns:props="http://properties">'
        "   <![CDATA[<h2>HTML markup</h2>]]>"
        "</props:simpleBody>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element, {"$type": "props:SimpleBody", "body": "<h2>HTML markup</h2>"}
    )


# should import > alias


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "lowerCase")
def test_030_lower_case() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:Root")

    result = reader.from_xml('<props:root xmlns:props="http://properties" />', root_handler)

    assert json_equal(result.root_element, {"$type": "props:Root"})


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "none")
def test_031_none() -> None:
    _model_holder, reader = _reader("noalias")
    root_handler = reader.handler("na:Root")

    result = reader.from_xml('<na:Root xmlns:na="http://noalias" />', root_handler)

    assert json_equal(result.root_element, {"$type": "na:Root"})


# should import > reference


def test_032_reference_single() -> None:
    _model_holder, reader = _reader("properties", "properties-extended")
    root_handler = reader.handler("props:Root")

    xml = (
        '<props:root xmlns:props="http://properties">'
        '<props:containedCollection id="C_5">'
        '<props:complex id="C_1" />'
        '<props:complex id="C_2" />'
        "</props:containedCollection>"
        '<props:referencingSingle id="C_4" referencedComplex="C_1" />'
        "</props:root>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "props:Root",
            "any": [
                {
                    "$type": "props:ContainedCollection",
                    "id": "C_5",
                    "children": [
                        {"$type": "props:Complex", "id": "C_1"},
                        {"$type": "props:Complex", "id": "C_2"},
                    ],
                },
                {"$type": "props:ReferencingSingle", "id": "C_4"},
            ],
        },
    )

    referenced = result.root_element.get("any")[0].get("children")[0]
    referencing_single = result.root_element.get("any")[1]

    assert referencing_single.get("referencedComplex") is referenced


def test_033_reference_collection() -> None:
    _model_holder, reader = _reader("properties", "properties-extended")
    root_handler = reader.handler("props:Root")

    xml = (
        '<props:root xmlns:props="http://properties">'
        '<props:containedCollection id="C_5">'
        '<props:complex id="C_1" />'
        '<props:complex id="C_2" />'
        "</props:containedCollection>"
        '<props:referencingCollection id="C_4">'
        "<props:references>C_2</props:references>"
        "<props:references>C_5</props:references>"
        "</props:referencingCollection>"
        "</props:root>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "props:Root",
            "any": [
                {
                    "$type": "props:ContainedCollection",
                    "id": "C_5",
                    "children": [
                        {"$type": "props:Complex", "id": "C_1"},
                        {"$type": "props:Complex", "id": "C_2"},
                    ],
                },
                {"$type": "props:ReferencingCollection", "id": "C_4"},
            ],
        },
    )

    contained_collection = result.root_element.get("any")[0]
    complex_c2 = contained_collection.get("children")[1]
    referencing_collection = result.root_element.get("any")[1]

    assert json_equal(referencing_collection.get("references"), [complex_c2, contained_collection])


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "attribute collection")
def test_034_attribute_collection() -> None:
    _model_holder, reader = _reader("properties", "properties-extended")
    root_handler = reader.handler("props:Root")

    xml = (
        '<props:root xmlns:props="http://properties">'
        '<props:containedCollection id="C_5">'
        '<props:complex id="C_1" />'
        '<props:complex id="C_2" />'
        '<props:complex id="C_3" />'
        "</props:containedCollection>"
        '<props:attributeReferenceCollection id="C_4" refs="C_2 C_3 C_5" />'
        "</props:root>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "props:Root",
            "any": [
                {
                    "$type": "props:ContainedCollection",
                    "id": "C_5",
                    "children": [
                        {"$type": "props:Complex", "id": "C_1"},
                        {"$type": "props:Complex", "id": "C_2"},
                        {"$type": "props:Complex", "id": "C_3"},
                    ],
                },
                {"$type": "props:AttributeReferenceCollection", "id": "C_4"},
            ],
        },
    )

    contained_collection = result.root_element.get("any")[0]
    complex_c2 = contained_collection.get("children")[1]
    complex_c3 = contained_collection.get("children")[2]
    attr_reference_collection = result.root_element.get("any")[1]

    assert json_equal(
        attr_reference_collection.get("refs"), [complex_c2, complex_c3, contained_collection]
    )


# should not import > wrong namespace


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "same alias")
def test_035_same_alias() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:Root")

    xml = (
        '<props:root xmlns:props="http://invalid"><props:referencingSingle id="C_4" /></props:root>'
    )

    with pytest.raises(ParseError, match=re.escape("unexpected element")):
        reader.from_xml(xml, root_handler)


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "different alias")
def test_036_different_alias() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:Root")

    xml = (
        '<props1:root xmlns:props1="http://invalid">'
        '<props1:referencingSingle id="C_4" />'
        "</props1:root>"
    )

    with pytest.raises(ParseError, match=re.escape("unexpected element")):
        reader.from_xml(xml, root_handler)


# internal > should identify references


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "on attribute")
def test_037_on_attribute() -> None:
    _model_holder, reader = _reader("properties", "properties-extended")
    root_handler = reader.handler("props:ReferencingSingle")

    xml = (
        '<props:referencingSingle xmlns:props="http://properties" '
        'id="C_4" referencedComplex="C_1" />'
    )

    result = reader.from_xml(xml, root_handler)

    assert len(result.references) == 1
    reference = result.references[0]
    assert reference["property"] == "props:referencedComplex"
    assert reference["id"] == "C_1"
    assert json_equal(reference["element"], {"$type": "props:ReferencingSingle", "id": "C_4"})


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "embedded")
def test_038_embedded() -> None:
    _model_holder, reader = _reader("properties", "properties-extended")
    root_handler = reader.handler("props:ReferencingCollection")

    xml = (
        '<props:referencingCollection xmlns:props="http://properties" id="C_4">'
        "<props:references>C_2</props:references>"
        "<props:references>C_5</props:references>"
        "</props:referencingCollection>"
    )

    result = reader.from_xml(xml, root_handler)

    expected_target = {"$type": "props:ReferencingCollection", "id": "C_4"}

    assert len(result.references) == 2
    assert result.references[0]["property"] == "props:references"
    assert result.references[0]["id"] == "C_2"
    assert json_equal(result.references[0]["element"], expected_target)
    assert result.references[1]["property"] == "props:references"
    assert result.references[1]["id"] == "C_5"
    assert json_equal(result.references[1]["element"], expected_target)


# error handling


def _assert_warnings_match(warnings: list[Any], patterns: list[str]) -> None:
    """Check warning messages against regex patterns, positionally."""
    assert len(warnings) == len(patterns)
    for warning, pattern in zip(warnings, patterns, strict=True):
        assert re.search(pattern, warning.message) is not None


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should handle non-xml text files")
def test_039_handle_non_xml_text_files() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ComplexAttrs")

    data = (FIXTURES / "error" / "no-xml.txt").read_text(encoding="utf-8")

    with pytest.raises(ParseError, match=re.escape("unparsable content")):
        reader.from_xml(data, root_handler)


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should handle unexpected text")
def test_040_handle_unexpected_text() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ComplexAttrs")

    xml = '<props:complexAttrs xmlns:props="http://properties">a</props:complexAttrs>'

    result = reader.from_xml(xml, root_handler)

    _assert_warnings_match(result.warnings, [r"unexpected body text <a>"])

    assert json_equal(result.root_element, {"$type": "props:ComplexAttrs"})


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should handle unexpected CDATA")
def test_041_handle_unexpected_cdata() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ComplexAttrs")

    xml = '<props:complexAttrs xmlns:props="http://properties"><![CDATA[a]]></props:complexAttrs>'

    result = reader.from_xml(xml, root_handler)

    _assert_warnings_match(result.warnings, [r"unexpected body text <a>"])

    assert json_equal(result.root_element, {"$type": "props:ComplexAttrs"})


@pytest.mark.upstream(
    "moddle-xml/test/spec/reader.js", "should handle incomplete attribute declaration"
)
def test_042_handle_incomplete_attribute_declaration() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ComplexAttrs")

    xml = '<props:complexAttrs xmlns:props="http://properties" foo />'

    result = reader.from_xml(xml, root_handler)

    _assert_warnings_match(result.warnings, [r"nested error: missing attribute value"])

    assert json_equal(result.root_element, {"$type": "props:ComplexAttrs"})


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should handle attribute re-definition")
def test_043_handle_attribute_redefinition() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ComplexAttrs")

    xml = '<props:complexAttrs xmlns:props="http://properties" id="A" id="B" />'

    result = reader.from_xml(xml, root_handler)

    _assert_warnings_match(result.warnings, [r"nested error: attribute <id> already defined"])

    assert json_equal(result.root_element, {"$type": "props:ComplexAttrs", "id": "A"})


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should handle unparsable attributes")
def test_044_handle_unparsable_attributes() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ComplexAttrs")

    xml = '<props:complexAttrs id="A" foo=\'"" />'

    result = reader.from_xml(xml, root_handler)

    _assert_warnings_match(
        result.warnings,
        [
            r"nested error: attribute value quote missmatch",
            r"nested error: illegal character after attribute end",
        ],
    )

    assert json_equal(result.root_element, {"$type": "props:ComplexAttrs", "id": "A"})


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should handle illegal ID attribute")
def test_045_handle_illegal_id_attribute() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ComplexAttrs")

    xml = '<props:complexAttrs id="a&lt;" />'

    with pytest.raises(ParseError, match=r"nested error: illegal ID <a<>"):
        reader.from_xml(xml, root_handler)


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should handle non-xml binary file")
def test_046_handle_non_xml_binary_file() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ComplexAttrs")

    data = (FIXTURES / "error" / "binary.png").read_bytes().decode("utf-8", errors="replace")

    with pytest.raises(ParseError, match=re.escape("unparsable content")):
        reader.from_xml(data, root_handler)


# error handling > should handle invalid root element


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "wrong type")
def test_047_wrong_type() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ComplexAttrs")

    xml = (
        '<props:referencingCollection xmlns:props="http://properties" id="C_4">'
        "<props:references>C_2</props:references>"
        "<props:references>C_5</props:references>"
        "</props:referencingCollection>"
    )

    expected_error = (
        "unparsable content <props:referencingCollection> detected\n\t"
        "line: 0\n\t"
        "column: 0\n\t"
        "nested error: unexpected element <props:referencingCollection>"
    )

    with pytest.raises(ParseError, match=re.escape("unexpected element")) as exc_info:
        reader.from_xml(xml, root_handler)

    assert exc_info.value.message == expected_error


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "wrong uri")
def test_048_wrong_uri() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:Root")

    xml = (
        '<props:root xmlns:props="http://invalid"><props:referencingSingle id="C_4" /></props:root>'
    )

    with pytest.raises(ParseError, match=re.escape("unexpected element <props:root>")) as exc_info:
        reader.from_xml(xml, root_handler)

    assert exc_info.value is not None


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "unknown uri + prefix")
def test_049_unknown_uri_prefix() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:Root")

    xml = (
        '<props1:root xmlns:props1="http://invalid">'
        '<props1:referencingSingle id="C_4" />'
        "</props1:root>"
    )

    with pytest.raises(ParseError, match=re.escape("unexpected element <props1:root>")) as exc_info:
        reader.from_xml(xml, root_handler)

    assert exc_info.value is not None


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "missing namespace")
def test_050_missing_namespace() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:Root")

    xml = '<root xmlns:props="http://properties"><referencingSingle id="C_4" /></root>'

    with pytest.raises(
        ParseError, match=re.escape("unparsable content <root> detected")
    ) as exc_info:
        reader.from_xml(xml, root_handler)

    assert exc_info.value is not None


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "unparsable root element / lax mode")
def test_051_unparsable_root_element_lax_mode() -> None:
    model = _model("properties")
    reader = Reader({"model": model, "lax": True})
    root_handler = reader.handler("props:Root")

    xml = '<root xmlns:props="http://properties"><referencingSingle id="C_4" /></root>'

    with pytest.raises(
        ParseError, match=re.escape("failed to parse document as <props:Root>")
    ) as exc_info:
        reader.from_xml(xml, root_handler)

    assert exc_info.value is not None


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should handle invalid child element")
def test_052_handle_invalid_child_element() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ReferencingCollection")

    xml = (
        '<props:referencingCollection xmlns:props="http://properties" id="C_4">'
        "<props:references>C_2</props:references>"
        "<props:invalid>C_5</props:invalid>"
        "</props:referencingCollection>"
    )

    expected_error = (
        "unparsable content <props:invalid> detected\n\t"
        "line: 0\n\t"
        "column: 110\n\t"
        "nested error: unknown type <props:Invalid>"
    )

    with pytest.raises(ParseError, match=re.escape("unknown type")) as exc_info:
        reader.from_xml(xml, root_handler)

    assert exc_info.value.message == expected_error


@pytest.mark.upstream(
    "moddle-xml/test/spec/reader.js", "should handle invalid child element / non-model schema"
)
def test_053_handle_invalid_child_element_non_model_schema() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ReferencingCollection")

    xml = (
        '<props:referencingCollection xmlns:props="http://properties" '
        'xmlns:other="http://other">'
        "<other:foo>C_2</other:foo>"
        "</props:referencingCollection>"
    )

    expected_error = (
        "unparsable content <other:foo> detected\n\t"
        "line: 0\n\t"
        "column: 88\n\t"
        "nested error: unrecognized element <other:foo>"
    )

    with pytest.raises(ParseError, match=re.escape("unrecognized element")) as exc_info:
        reader.from_xml(xml, root_handler)

    assert exc_info.value.message == expected_error


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should handle duplicate id")
def test_054_handle_duplicate_id() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:Root")

    xml = (
        '<props:root xmlns:props="http://properties" id="root">'
        '<props:baseWithId id="root" />'
        "</props:root>"
    )

    expected_error = (
        "unparsable content <props:baseWithId> detected\n\t"
        "line: 0\n\t"
        "column: 54\n\t"
        "nested error: duplicate ID <root>"
    )

    with pytest.raises(ParseError, match=re.escape("duplicate ID")) as exc_info:
        reader.from_xml(xml, root_handler)

    assert exc_info.value.message == expected_error


# error handling > references > should log warning


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "on unresolvable reference")
def test_055_on_unresolvable_reference() -> None:
    _model_holder, reader = _reader("properties", "properties-extended")
    root_handler = reader.handler("props:Root")

    xml = (
        '<props:root xmlns:props="http://properties">'
        '<props:referencingSingle id="C_4" referencedComplex="C_1" />'
        "</props:root>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "props:Root",
            "any": [{"$type": "props:ReferencingSingle", "id": "C_4"}],
        },
    )

    referencing_single = result.root_element.get("any")[0]

    assert not referencing_single.get("referencedComplex")

    assert len(result.warnings) == 1
    warning = result.warnings[0]
    assert warning.message == "unresolved reference <C_1>"
    assert warning.element is referencing_single
    assert warning.property == "props:referencedComplex"
    assert warning.value == "C_1"


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "on unresolvable collection reference")
def test_056_on_unresolvable_collection_reference() -> None:
    _model_holder, reader = _reader("properties", "properties-extended")
    root_handler = reader.handler("props:Root")

    xml = (
        '<props:root xmlns:props="http://properties">'
        '<props:containedCollection id="C_5">'
        '<props:complex id="C_2" />'
        "</props:containedCollection>"
        '<props:referencingCollection id="C_4">'
        "<props:references>C_1</props:references>"
        "<props:references>C_2</props:references>"
        "</props:referencingCollection>"
        "</props:root>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "props:Root",
            "any": [
                {
                    "$type": "props:ContainedCollection",
                    "id": "C_5",
                    "children": [{"$type": "props:Complex", "id": "C_2"}],
                },
                {"$type": "props:ReferencingCollection", "id": "C_4"},
            ],
        },
    )

    c2 = result.root_element.get("any")[0].get("children")[0]
    referencing_collection = result.root_element.get("any")[1]

    assert json_equal(referencing_collection.get("references"), [c2])

    assert len(result.warnings) == 1
    warning = result.warnings[0]
    assert warning.message == "unresolved reference <C_1>"
    assert warning.element is referencing_collection
    assert warning.property == "props:references"
    assert warning.value == "C_1"


# lax error handling


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should ignore namespaced invalid child")
def test_057_ignore_namespaced_invalid_child() -> None:
    model = _model("properties")
    reader = Reader({"model": model, "lax": True})
    root_handler = reader.handler("props:ComplexAttrs")

    xml = (
        '<props:complexAttrs xmlns:props="http://properties">'
        '<props:unknownElement foo="bar">'
        "<props:unknownChild />"
        "</props:unknownElement>"
        "</props:complexAttrs>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(result.root_element, {"$type": "props:ComplexAttrs"})

    assert len(result.warnings) == 1
    assert result.warnings[0].message == (
        "unparsable content <props:unknownElement> detected\n\t"
        "line: 0\n\t"
        "column: 52\n\t"
        "nested error: unknown type <props:UnknownElement>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should ignore invalid child")
def test_058_ignore_invalid_child() -> None:
    model = _model("properties")
    reader = Reader({"model": model, "lax": True})
    root_handler = reader.handler("props:ComplexAttrs")

    xml = (
        '<props:complexAttrs xmlns:props="http://properties">'
        '<unknownElement foo="bar" />'
        "</props:complexAttrs>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(result.root_element, {"$type": "props:ComplexAttrs"})

    assert len(result.warnings) == 1
    assert result.warnings[0].message == (
        "unparsable content <unknownElement> detected\n\t"
        "line: 0\n\t"
        "column: 52\n\t"
        "nested error: unrecognized element <unknownElement>"
    )


# extension handling > attributes


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should read extension attributes")
def test_059_read_extension_attributes() -> None:
    _model_holder, reader = _reader("extensions")
    root_handler = reader.handler("e:Root")

    xml = '<e:root xmlns:e="http://extensions" xmlns:other="http://other" other:foo="BAR" />'

    result = reader.from_xml(xml, root_handler)

    assert result.root_element.attrs_ == {
        "xmlns:e": "http://extensions",
        "xmlns:other": "http://other",
        "other:foo": "BAR",
    }


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should read default ns")
def test_060_read_default_ns() -> None:
    _model_holder, reader = _reader("extensions")
    root_handler = reader.handler("e:Root")

    xml = '<root xmlns="http://extensions" />'

    result = reader.from_xml(xml, root_handler)

    assert result.root_element.attrs_ == {"xmlns": "http://extensions"}


# extension handling > elements


@pytest.mark.upstream(
    "moddle-xml/test/spec/reader.js", "should read self-closing extension elements"
)
def test_061_read_self_closing_extension_elements() -> None:
    _model_holder, reader = _reader("extensions")
    root_handler = reader.handler("e:Root")

    xml = (
        '<e:root xmlns:e="http://extensions" xmlns:other="http://other">'
        "<e:id>FOO</e:id>"
        '<other:meta key="FOO" value="BAR" />'
        '<other:meta key="BAZ" value="FOOBAR" />'
        "</e:root>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "e:Root",
            "id": "FOO",
            "extensions": [
                {"$type": "other:meta", "key": "FOO", "value": "BAR"},
                {"$type": "other:meta", "key": "BAZ", "value": "FOOBAR"},
            ],
        },
    )


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should read extension element body")
def test_062_read_extension_element_body() -> None:
    _model_holder, reader = _reader("extensions")
    root_handler = reader.handler("e:Root")

    xml = (
        '<e:root xmlns:e="http://extensions" xmlns:other="http://other">'
        "<e:id>FOO</e:id>"
        "<other:note>a note</other:note>"
        "</e:root>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "e:Root",
            "id": "FOO",
            "extensions": [{"$type": "other:note", "$body": "a note"}],
        },
    )


@pytest.mark.upstream(
    "moddle-xml/test/spec/reader.js", "should read extension element body with whitespaces"
)
def test_063_read_extension_element_body_with_whitespaces() -> None:
    _model_holder, reader = _reader("extensions")
    root_handler = reader.handler("e:Root")

    xml = (
        '<e:root xmlns:e="http://extensions" xmlns:other="http://other">'
        "<e:id>FOO</e:id>"
        "<other:note> a note with leading and trailing whitespaces </other:note>"
        "<other:additionalNote>  </other:additionalNote>"
        "</e:root>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "e:Root",
            "id": "FOO",
            "extensions": [
                {
                    "$type": "other:note",
                    "$body": " a note with leading and trailing whitespaces ",
                },
                {"$type": "other:additionalNote"},
            ],
        },
    )


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should read nested extension element")
def test_064_read_nested_extension_element() -> None:
    _model_holder, reader = _reader("extensions")
    root_handler = reader.handler("e:Root")

    xml = (
        '<e:root xmlns:e="http://extensions" xmlns:other="http://other">'
        "<e:id>FOO</e:id>"
        "<other:nestedMeta>"
        '<other:meta key="k1" value="v1" />'
        '<other:meta key="k2" value="v2" />'
        "<other:additionalNote>this is some text</other:additionalNote>"
        "</other:nestedMeta>"
        "</e:root>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "e:Root",
            "id": "FOO",
            "extensions": [
                {
                    "$type": "other:nestedMeta",
                    "$children": [
                        {"$type": "other:meta", "key": "k1", "value": "v1"},
                        {"$type": "other:meta", "key": "k2", "value": "v2"},
                        {
                            "$type": "other:additionalNote",
                            "$body": "this is some text",
                        },
                    ],
                }
            ],
        },
    )


# extension handling > elements > descriptor


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should exist")
def test_065_descriptor_should_exist() -> None:
    _model_holder, reader = _reader("extensions")
    root_handler = reader.handler("e:Root")

    xml = (
        '<e:root xmlns:e="http://extensions" xmlns:other="http://other">'
        "<e:id>FOO</e:id>"
        "<other:note>a note</other:note>"
        "</e:root>"
    )

    result = reader.from_xml(xml, root_handler)

    note = result.root_element.get("extensions")[0]

    assert note.descriptor_ is not None


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should contain namespace information")
def test_066_descriptor_should_contain_namespace_information() -> None:
    _model_holder, reader = _reader("extensions")
    root_handler = reader.handler("e:Root")

    xml = (
        '<e:root xmlns:e="http://extensions" xmlns:other="http://other">'
        "<e:id>FOO</e:id>"
        "<other:note>a note</other:note>"
        "</e:root>"
    )

    result = reader.from_xml(xml, root_handler)

    note = result.root_element.get("extensions")[0]

    assert note.descriptor_.name == "other:note"
    assert note.descriptor_.is_generic is True
    assert note.descriptor_.ns_prefix == "other"
    assert note.descriptor_.ns_local_name == "note"
    assert note.descriptor_.ns_uri == "http://other"


# parent -> child relationship


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should expose $parent on model elements")
def test_067_expose_parent_on_model_elements() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ComplexAttrs")

    xml = (
        '<props:complexAttrs xmlns:props="http://properties" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<props:attrs xsi:type="props:Attributes" integerValue="10" />'
        "</props:complexAttrs>"
    )

    result = reader.from_xml(xml, root_handler)

    assert not result.root_element.parent_
    assert result.root_element.get("attrs").parent_ is result.root_element


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should expose $parent on references")
def test_068_expose_parent_on_references() -> None:
    _model_holder, reader = _reader("properties", "properties-extended")
    root_handler = reader.handler("props:Root")

    xml = (
        '<props:root xmlns:props="http://properties">'
        '<props:containedCollection id="C_5">'
        '<props:complex id="C_1" />'
        '<props:complex id="C_2" />'
        "</props:containedCollection>"
        '<props:referencingSingle id="C_4" referencedComplex="C_1" />'
        "</props:root>"
    )

    result = reader.from_xml(xml, root_handler)

    contained_collection = result.root_element.get("any")[0]
    referenced_complex = result.root_element.get("any")[1].get("referencedComplex")

    assert referenced_complex.parent_ is contained_collection


@pytest.mark.upstream(
    "moddle-xml/test/spec/reader.js", "should expose $parent on extension elements"
)
def test_069_expose_parent_on_extension_elements() -> None:
    _model_holder, reader = _reader("extensions")
    root_handler = reader.handler("e:Root")

    xml = (
        '<e:root xmlns:e="http://extensions" xmlns:other="http://other">'
        "<e:id>FOO</e:id>"
        "<other:nestedMeta>"
        '<other:meta key="k1" value="v1" />'
        '<other:meta key="k2" value="v2" />'
        "<other:additionalNote>this is some text</other:additionalNote>"
        "</other:nestedMeta>"
        "</e:root>"
    )

    result = reader.from_xml(xml, root_handler)

    child = result.root_element.get("extensions")[0]
    nested = child.get("$children")[0]

    assert child.parent_ is result.root_element
    assert nested.parent_ is child

    assert json_equal(
        result.root_element,
        {
            "$type": "e:Root",
            "id": "FOO",
            "extensions": [
                {
                    "$type": "other:nestedMeta",
                    "$children": [
                        {"$type": "other:meta", "key": "k1", "value": "v1"},
                        {"$type": "other:meta", "key": "k2", "value": "v2"},
                        {
                            "$type": "other:additionalNote",
                            "$body": "this is some text",
                        },
                    ],
                }
            ],
        },
    )


# qualified extensions


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should read typed extension property")
def test_070_read_typed_extension_property() -> None:
    _model_holder, reader = _reader("extension/base", "extension/custom")
    root_handler = reader.handler("b:Root")

    xml = (
        '<b:Root xmlns:b="http://base" xmlns:c="http://custom">'
        '<c:CustomGeneric count="10" />'
        "</b:Root>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {"$type": "b:Root", "generic": {"$type": "c:CustomGeneric", "count": 10}},
    )


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should read typed extension attribute")
def test_071_read_typed_extension_attribute() -> None:
    _model_holder, reader = _reader("extension/base", "extension/custom")
    root_handler = reader.handler("b:Root")

    xml = '<b:Root xmlns:b="http://base" xmlns:c="http://custom" c:customAttr="666"></b:Root>'

    result = reader.from_xml(xml, root_handler)

    assert json_equal(result.root_element, {"$type": "b:Root", "customAttr": 666})


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should read generic collection")
def test_072_read_generic_collection() -> None:
    _model_holder, reader = _reader("extension/base", "extension/custom")
    root_handler = reader.handler("b:Root")

    xml = (
        '<b:Root xmlns:b="http://base" xmlns:c="http://custom" xmlns:other="http://other">'
        '<c:Property key="foo" value="FOO" />'
        '<c:Property key="bar" value="BAR" />'
        "<other:Xyz>content</other:Xyz>"
        "</b:Root>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "b:Root",
            "genericCollection": [
                {"$type": "c:Property", "key": "foo", "value": "FOO"},
                {"$type": "c:Property", "key": "bar", "value": "BAR"},
                {"$type": "other:Xyz", "$body": "content"},
            ],
        },
    )


# qualified extensions > validation


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "extension NS")
def test_073_validation_extension_ns() -> None:
    _model_holder, reader = _reader("extension/base", "extension/custom")
    root_handler = reader.handler("b:Root")

    xml = (
        '<b:Root xmlns:b="http://base" xmlns:c="http://custom" '
        'xmlns:foo="http://foo" c:unknownAttribute="XXX"></b:Root>'
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(result.root_element, {"$type": "b:Root"})

    assert result.root_element.attrs_ == {
        "xmlns:b": "http://base",
        "xmlns:c": "http://custom",
        "xmlns:foo": "http://foo",
        "c:unknownAttribute": "XXX",
    }

    assert len(result.warnings) == 1
    assert result.warnings[0].message == "unknown attribute <c:unknownAttribute>"


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "local NS")
def test_074_validation_local_ns() -> None:
    model = _model("properties")
    reader = Reader({"model": model, "lax": True})
    root_handler = reader.handler("props:ComplexAttrs")

    xml = '<props:complexAttrs xmlns:props="http://properties" props:unknownAttribute="FOO" />'

    result = reader.from_xml(xml, root_handler)

    assert json_equal(result.root_element, {"$type": "props:ComplexAttrs"})

    assert result.root_element.attrs_ == {
        "xmlns:props": "http://properties",
        "props:unknownAttribute": "FOO",
    }

    assert len(result.warnings) == 1
    assert result.warnings[0].message == "unknown attribute <props:unknownAttribute>"


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should permit non-well-known attributes")
def test_075_permit_non_well_known_attributes() -> None:
    _model_holder, reader = _reader("extension/base", "extension/custom")
    root_handler = reader.handler("b:Root")

    xml = '<b:Root xmlns:b="http://base" xmlns:blub="http://blub" blub:attr="XXX"></b:Root>'

    result = reader.from_xml(xml, root_handler)

    assert json_equal(result.root_element, {"$type": "b:Root"})

    assert result.root_element.attrs_ == {
        "xmlns:b": "http://base",
        "xmlns:blub": "http://blub",
        "blub:attr": "XXX",
    }

    assert result.warnings == []


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should fail parsing unknown element")
def test_076_fail_parsing_unknown_element() -> None:
    _model_holder, reader = _reader("extension/base", "extension/custom")
    root_handler = reader.handler("b:Root")

    xml = (
        '<b:Root xmlns:b="http://base" xmlns:c="http://custom" xmlns:other="http://other">'
        "<c:NonExisting />"
        "</b:Root>"
    )

    with pytest.raises(ParseError, match=re.escape("unknown type")):
        reader.from_xml(xml, root_handler)


# fake ids


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should ignore (non-id) id attribute")
def test_077_ignore_non_id_id_attribute() -> None:
    _model_holder, reader = _reader("fake-id")
    root_handler = reader.handler("fi:Root")

    xml = '<fi:Root xmlns:fi="http://fakeid"><fi:ChildWithFakeId id="FOO" /></fi:Root>'

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "fi:Root",
            "children": [{"$type": "fi:ChildWithFakeId", "id": "FOO"}],
        },
    )

    assert result.elements_by_id == {}


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should not-resolve (non-id) id references")
def test_078_not_resolve_non_id_id_references() -> None:
    _model_holder, reader = _reader("fake-id")
    root_handler = reader.handler("fi:Root")

    xml = (
        '<fi:Root xmlns:fi="http://fakeid">'
        '<fi:ChildWithFakeId id="FOO" />'
        '<fi:ChildWithFakeId ref="FOO" />'
        "</fi:Root>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "fi:Root",
            "children": [
                {"$type": "fi:ChildWithFakeId", "id": "FOO"},
                {"$type": "fi:ChildWithFakeId"},
            ],
        },
    )

    assert len(result.warnings) == 1
    assert result.warnings[0].message == "unresolved reference <FOO>"


# encoding


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should decode UTF-8, no problemo")
def test_079_decode_utf8_no_problemo() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ComplexAttrs")

    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<props:complexAttrs xmlns:props="http://properties">'
        "</props:complexAttrs>"
    )

    result = reader.from_xml(xml, root_handler)

    assert result.warnings == []
    assert result.root_element is not None


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should warn on non-UTF-8 encoded files")
def test_080_warn_on_non_utf8_encoded_files() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ComplexAttrs")

    xml = (
        '<?xml encoding="windows-1252"?>'
        '<props:complexAttrs xmlns:props="http://properties">'
        "</props:complexAttrs>"
    )

    result = reader.from_xml(xml, root_handler)

    assert len(result.warnings) == 1
    assert re.search(r"unsupported document encoding <windows-1252>", result.warnings[0].message)

    assert result.root_element is not None


@pytest.mark.upstream(
    "moddle-xml/test/spec/reader.js", "should warn on non-UTF-8 encoded files / CAPITALIZED"
)
def test_081_warn_on_non_utf8_encoded_files_capitalized() -> None:
    _model_holder, reader = _reader("properties")
    root_handler = reader.handler("props:ComplexAttrs")

    xml = (
        '<?XML ENCODING="WINDOWS-1252"?>'
        '<props:complexAttrs xmlns:props="http://properties">'
        "</props:complexAttrs>"
    )

    result = reader.from_xml(xml, root_handler)

    assert len(result.warnings) == 1
    assert re.search(r"unsupported document encoding <WINDOWS-1252>", result.warnings[0].message)

    assert result.root_element is not None


# attr <> child conflict


@pytest.mark.upstream(
    "moddle-xml/test/spec/reader.js", "should import attr and child with the same name"
)
def test_082_import_attr_and_child_with_same_name() -> None:
    _model_holder, reader = _reader("attr-child-conflict")
    root_handler = reader.handler("s:Foo")

    xml = '<s:foo xmlns:s="http://s" bar="Bar"><s:bar woop="WHOOPS"></s:bar></s:foo>'

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "s:Foo",
            "bar": "Bar",
            "bars": [{"$type": "s:Bar", "woop": "WHOOPS"}],
        },
    )


# namespace declarations


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should handle nested (generic)")
def test_083_handle_nested_generic() -> None:
    _model_holder, reader = _reader("extensions")
    root_handler = reader.handler("e:Root")

    xml = (
        '<e:root xmlns:e="http://extensions">'
        '<bar:bar xmlns:bar="http://bar">'
        '<other:child b="B" xmlns:other="http://other" />'
        "</bar:bar>"
        '<foo xmlns="http://foo">'
        '<child a="A" />'
        "</foo>"
        "</e:root>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "e:Root",
            "extensions": [
                {
                    "$type": "bar:bar",
                    "xmlns:bar": "http://bar",
                    "$children": [
                        {
                            "$type": "other:child",
                            "xmlns:other": "http://other",
                            "b": "B",
                        }
                    ],
                },
                {
                    "$type": "ns0:foo",
                    "xmlns": "http://foo",
                    "$children": [{"$type": "ns0:child", "a": "A"}],
                },
            ],
        },
    )


@pytest.mark.upstream(
    "moddle-xml/test/spec/reader.js", "should handle nested, re-declaring default"
)
def test_084_handle_nested_redeclaring_default() -> None:
    _model_holder, reader = _reader("extensions")
    root_handler = reader.handler("e:Root")

    xml = (
        '<root xmlns="http://extensions">'
        '<bar:bar xmlns:bar="http://bar">'
        '<other:child b="B" xmlns:other="http://other" />'
        "</bar:bar>"
        '<foo xmlns="http://foo">'
        '<child a="A" />'
        "</foo>"
        "</root>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "e:Root",
            "extensions": [
                {
                    "$type": "bar:bar",
                    "xmlns:bar": "http://bar",
                    "$children": [
                        {
                            "$type": "other:child",
                            "xmlns:other": "http://other",
                            "b": "B",
                        }
                    ],
                },
                {
                    "$type": "ns0:foo",
                    "xmlns": "http://foo",
                    "$children": [{"$type": "ns0:child", "a": "A"}],
                },
            ],
        },
    )


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should handle unused global")
def test_085_handle_unused_global() -> None:
    _model_holder, reader = _reader("properties", "properties-extended")
    root_handler = reader.handler("ext:Root")

    xml = '<root xmlns="http://extended" id="Root"><base xmlns="http://properties" /></root>'

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {"$type": "ext:Root", "id": "Root", "any": [{"$type": "props:Base"}]},
    )


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should handle local override")
def test_086_handle_local_override() -> None:
    _model_holder, reader = _reader("properties", "properties-extended")
    root_handler = reader.handler("props:ComplexNesting")

    xml = (
        '<root:complexNesting xmlns:root="http://properties" id="ComplexNesting">'
        '<complexNesting xmlns="http://properties">'
        "<complexNesting>"
        '<foo:complexNesting xmlns:foo="http://properties" />'
        "</complexNesting>"
        "</complexNesting>"
        "</root:complexNesting>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "props:ComplexNesting",
            "id": "ComplexNesting",
            "nested": [
                {
                    "$type": "props:ComplexNesting",
                    "nested": [
                        {
                            "$type": "props:ComplexNesting",
                            "nested": [{"$type": "props:ComplexNesting"}],
                        }
                    ],
                }
            ],
        },
    )


# custom namespace mapping


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should read remapped xmi:type")
def test_087_read_remapped_xmi_type() -> None:
    model = _model(
        "datatype",
        "datatype-external",
        config={"nsMap": {"http://www.omg.org/spec/XMI/20131001": "xmi"}},
    )
    reader = Reader(model)
    root_handler = reader.handler("dt:Root")

    xml = (
        '<dt:root xmlns:dt="http://datatypes">'
        '<dt:xmiBounds xmlns:do="http://datatypes2" '
        'xmlns:foo="http://www.omg.org/spec/XMI/20131001" xmlns:f="http://foo" '
        'foo:type="do:Rect" x="100" f:bar="BAR" />'
        "</dt:root>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {"$type": "dt:Root", "xmiBounds": {"$type": "do:Rect", "x": 100}},
    )


@pytest.mark.upstream("moddle-xml/test/spec/reader.js", "should read remapped generic prefix")
def test_088_read_remapped_generic_prefix() -> None:
    model = _model(
        "extensions",
        config={"nsMap": {"http://other": "o", "http://foo": "f"}},
    )
    reader = Reader(model)
    root_handler = reader.handler("e:Root")

    xml = (
        '<e:root xmlns:e="http://extensions">'
        '<bar:bar xmlns:bar="http://bar">'
        '<other:child b="B" xmlns:other="http://other" />'
        "</bar:bar>"
        '<foo xmlns="http://foo">'
        '<child a="A" />'
        "</foo>"
        "</e:root>"
    )

    result = reader.from_xml(xml, root_handler)

    assert json_equal(
        result.root_element,
        {
            "$type": "e:Root",
            "extensions": [
                {
                    "$type": "bar:bar",
                    "xmlns:bar": "http://bar",
                    "$children": [{"$type": "o:child", "xmlns:other": "http://other", "b": "B"}],
                },
                {
                    "$type": "f:foo",
                    "xmlns": "http://foo",
                    "$children": [{"$type": "f:child", "a": "A"}],
                },
            ],
        },
    )


def test_089_hostile_generic_attrs_cannot_clobber_internals() -> None:
    """Port-specific security test (cyber-review B1, no upstream case).

    Attribute names colliding with generic-element internals (``model_``,
    ``type_``, ``get``, …) are unreachable from XML upstream (``$`` is an
    illegal attribute-name char) but reachable in the port through the
    ``xxx_`` renaming. The reader must drop them: internals survive, the
    child still parses, and the tree serializes.
    """
    _model_holder, reader = _reader("extensions")

    xml = (
        '<e:root xmlns:e="http://extensions">'
        '<foo:custom xmlns:foo="http://foo" model_="PWNED" descriptor_="PWNED" '
        'parent_="PWNED" type_="PWNED" get="PWNED" set="PWNED">'
        '<foo:child a="A" />'
        "</foo:custom>"
        "</e:root>"
    )

    result = reader.from_xml(xml, reader.handler("e:Root"))

    (custom,) = result.root_element.get("extensions")
    assert custom.type_ == "foo:custom"
    assert isinstance(custom.model_, Moddle)
    assert callable(custom.get)
    assert custom.get("$children") is not UNDEFINED
    assert json_equal(
        custom,
        {
            "$type": "foo:custom",
            "xmlns:foo": "http://foo",
            "$children": [{"$type": "foo:child", "a": "A"}],
        },
    )


def test_090_warning_flood_is_truncated() -> None:
    """Port-specific security test (cyber-review S1, no upstream case).

    Past ``MAX_WARNINGS`` the reader keeps a single truncation marker instead
    of accumulating unbounded O(document)-cost warnings.
    """
    from bpmn_io.moddle_xml.read import MAX_WARNINGS

    model_holder = _model("extensions")
    reader = Reader({"model": model_holder, "lax": True})

    tasks = "".join(f'<e:item id="T{i}" bogus="v" />' for i in range(MAX_WARNINGS + 100))
    result = reader.from_xml(
        f'<e:root xmlns:e="http://extensions">{tasks}</e:root>',
        reader.handler("e:Root"),
    )

    assert len(result.warnings) == MAX_WARNINGS + 1
    assert result.warnings[-1].message == "too many warnings, further warnings truncated"
