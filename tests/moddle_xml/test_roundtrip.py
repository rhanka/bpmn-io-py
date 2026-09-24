"""Ported moddle-xml roundtrip cases (Lot 6).

Transcribes every ``moddle-xml/test/spec/rountrip.js`` ``it()`` title (14
claims): one test per claim. Roundtrip cases assert
``to_xml(from_xml(input))`` equality, so each needs the reader and the
writer together. Only the public ``bpmn_io.moddle_xml`` API (``Reader``,
``Writer``) plus model building via ``bpmn_io.moddle`` is used.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from bpmn_io.moddle import Moddle
from bpmn_io.moddle_xml import Reader, Writer

FIXTURES = Path(__file__).resolve().parent.parent / "upstream" / "moddle-xml" / "test" / "fixtures"
MODEL_FIXTURES = FIXTURES / "model"
XML_FIXTURES = FIXTURES / "xml"


def _load(*names: str) -> list[dict[str, Any]]:
    """Load model fixture packages by name."""
    return [
        json.loads((MODEL_FIXTURES / f"{name}.json").read_text(encoding="utf-8")) for name in names
    ]


def _model(*names: str, config: dict[str, Any] | None = None) -> Moddle:
    """Build a model from fixture packages (strict, as the upstream helper)."""
    return Moddle(_load(*names), {"strict": True, **(config or {})})


def _roundtrip(
    model: Moddle,
    root_type: str,
    xml: str,
    *,
    format: bool = False,  # noqa: A002 - upstream option name
    preamble: bool = False,
) -> str:
    """Parse ``xml`` and serialize the root element back to a string."""
    reader = Reader(model)
    writer = Writer(format=format, preamble=preamble)
    result = reader.from_xml(xml, reader.handler(root_type))
    return writer.to_xml(result.root_element)


# Roundtrip


@pytest.mark.upstream("moddle-xml/test/spec/rountrip.js", "should strip unused global")
def test_001_strip_unused_global() -> None:
    model = _model("properties", "properties-extended")

    input_xml = (
        '<root xmlns="http://extended" xmlns:props="http://properties" id="Root">'
        '<props:Base xmlns="http://properties" />'
        "</root>"
    )

    output = _roundtrip(model, "ext:Root", input_xml)

    assert output == (
        '<root xmlns="http://extended" id="Root"><base xmlns="http://properties" /></root>'
    )


@pytest.mark.upstream("moddle-xml/test/spec/rountrip.js", "should strip unused <xsi:type>")
def test_002_strip_unused_xsi_type() -> None:
    model = _model("datatype")

    input_xml = (
        '<dt:root xmlns:dt="http://datatypes"><dt:bounds xsi:type="dt:Rect" y="100" /></dt:root>'
    )

    output = _roundtrip(model, "dt:Root", input_xml)

    assert output == ('<dt:root xmlns:dt="http://datatypes"><dt:bounds y="100" /></dt:root>')


@pytest.mark.upstream("moddle-xml/test/spec/rountrip.js", "should reuse global namespace")
def test_003_reuse_global_namespace() -> None:
    model = _model("properties", "properties-extended")

    input_xml = (
        '<root:complexNesting xml:lang="en" '
        'xmlns:root="http://properties" xmlns:ext="http://extended">'
        '<complexNesting xmlns="http://properties">'
        '<ext:extendedComplex numCount="1" />'
        "</complexNesting>"
        "</root:complexNesting>"
    )

    output = _roundtrip(model, "props:ComplexNesting", input_xml)

    assert output == (
        '<root:complexNesting xmlns:root="http://properties" '
        'xmlns:ext="http://extended" xml:lang="en">'
        '<complexNesting xmlns="http://properties">'
        '<ext:extendedComplex numCount="1" />'
        "</complexNesting>"
        "</root:complexNesting>"
    )


@pytest.mark.upstream("moddle-xml/test/spec/rountrip.js", "should keep default <xml> namespace")
def test_004_keep_default_xml_namespace() -> None:
    model = _model("properties")

    input_xml = '<root:complexNesting xmlns:root="http://properties" xml:lang="en" />'

    output = _roundtrip(model, "props:ComplexNesting", input_xml)

    assert output == input_xml


@pytest.mark.upstream("moddle-xml/test/spec/rountrip.js", "should de-duplicate attribute names")
def test_005_de_duplicate_attribute_names() -> None:
    model = _model("extension/base")

    input_xml = (
        '<base:Root xmlns:base="http://base" xmlns:test="http://test" '
        'ownAttr="A" base:ownAttr="B">'
        '<test:test test:duplicate="1" duplicate="2" />'
        "</base:Root>"
    )

    output = _roundtrip(model, "b:Root", input_xml)

    assert output == (
        '<base:Root xmlns:base="http://base" xmlns:test="http://test" ownAttr="B">'
        '<test:test duplicate="2" />'
        "</base:Root>"
    )


# Roundtrip > generic


@pytest.mark.upstream("moddle-xml/test/spec/rountrip.js", "should keep local ns attribute")
def test_006_keep_local_ns_attribute() -> None:
    model = _model("extensions")

    input_xml = (
        '<e:root xmlns:e="http://extensions" xmlns:woop="https://woop">'
        '<Bar xmlns="http://foobar">'
        '<Foo woop:boop="Some" />'
        "</Bar>"
        "</e:root>"
    )

    output = _roundtrip(model, "e:Root", input_xml)

    assert output == input_xml


@pytest.mark.upstream("moddle-xml/test/spec/rountrip.js", "should keep local <xsi:type>")
def test_007_keep_local_xsi_type() -> None:
    model = _model("extensions")

    input_xml = (
        '<e:root xmlns:e="http://extensions" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<Bar xmlns="http://foobar">'
        '<Foo xsi:type="Some" y="100" />'
        "</Bar>"
        "</e:root>"
    )

    output = _roundtrip(model, "e:Root", input_xml)

    assert output == input_xml


@pytest.mark.upstream("moddle-xml/test/spec/rountrip.js", "should keep local <xsi:type> (renamed)")
def test_008_keep_local_xsi_type_renamed() -> None:
    model = _model("extensions")

    input_xml = (
        '<e:root xmlns:e="http://extensions" '
        'xmlns:foo="http://www.w3.org/2001/XMLSchema-instance">'
        '<Bar xmlns="http://foobar">'
        '<Foo foo:type="Some" y="100" />'
        "</Bar>"
        "</e:root>"
    )

    output = _roundtrip(model, "e:Root", input_xml)

    assert output == input_xml


@pytest.mark.upstream("moddle-xml/test/spec/rountrip.js", "should keep generic <xsi:type>")
def test_009_keep_generic_xsi_type() -> None:
    model = _model("extensions")

    input_xml = (
        '<e:root xmlns:e="http://extensions" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<Bar xmlns="http://foobar">'
        '<Foo xsi:type="Some" y="100" />'
        "</Bar>"
        "</e:root>"
    )

    output = _roundtrip(model, "e:Root", input_xml)

    assert output == input_xml


@pytest.mark.upstream("moddle-xml/test/spec/rountrip.js", "should keep generic <xmi:type>")
def test_010_keep_generic_xmi_type() -> None:
    model = _model("extensions")

    input_xml = (
        '<e:root xmlns:e="http://extensions" '
        'xmlns:xmi="http://www.omg.org/spec/XMI/20131001">'
        '<Bar xmlns="http://foobar" xmi:type="FOOBAR" />'
        "</e:root>"
    )

    output = _roundtrip(model, "e:Root", input_xml)

    assert output == input_xml


@pytest.mark.upstream("moddle-xml/test/spec/rountrip.js", "should keep generic <xmi:type> (local)")
def test_011_keep_generic_xmi_type_local() -> None:
    model = _model("extensions")

    input_xml = (
        '<e:root xmlns:e="http://extensions">'
        '<Bar xmlns="http://foobar" '
        'xmlns:xmi="http://www.omg.org/spec/XMI/20131001" xmi:type="FOOBAR" />'
        "</e:root>"
    )

    output = _roundtrip(model, "e:Root", input_xml)

    assert output == input_xml


@pytest.mark.upstream("moddle-xml/test/spec/rountrip.js", "should keep generic <xmi:type> (nested)")
def test_012_keep_generic_xmi_type_nested() -> None:
    model = _model("extensions")

    input_xml = (
        '<e:root xmlns:e="http://extensions" '
        'xmlns:xmi="http://www.omg.org/spec/XMI/20131001">'
        '<Bar xmlns="http://foobar">'
        '<Foo xmi:type="Some" y="100" />'
        "</Bar>"
        "</e:root>"
    )

    output = _roundtrip(model, "e:Root", input_xml)

    assert output == input_xml


# Roundtrip > custom namespace mapping


@pytest.mark.upstream("moddle-xml/test/spec/rountrip.js", "should preserve remapped xmi:type")
def test_013_preserve_remapped_xmi_type() -> None:
    model = _model(
        "datatype",
        "datatype-external",
        config={"nsMap": {"http://www.omg.org/spec/XMI/20131001": "xmi"}},
    )

    input_xml = (
        '<dt:root xmlns:dt="http://datatypes">'
        '<dt:xmiBounds xmlns:do="http://datatypes2" '
        'xmlns:foo="http://www.omg.org/spec/XMI/20131001" '
        'xmlns:f="http://foo" foo:type="do:Rect" '
        'x="100" f:bar="BAR" />'
        "</dt:root>"
    )

    output = _roundtrip(model, "dt:Root", input_xml)

    assert output == input_xml


@pytest.mark.upstream("moddle-xml/test/spec/rountrip.js", "should keep remapped generic prefix")
def test_014_keep_remapped_generic_prefix() -> None:
    model = _model("extensions", config={"nsMap": {"http://other": "o", "http://foo": "f"}})

    input_xml = (
        '<e:root xmlns:e="http://extensions">'
        '<bar:bar xmlns:bar="http://bar">'
        '<other:child xmlns:other="http://other" b="B" />'
        "</bar:bar>"
        '<foo xmlns="http://foo">'
        '<child a="A" />'
        "</foo>"
        "</e:root>"
    )

    output = _roundtrip(model, "e:Root", input_xml)

    assert output == input_xml
