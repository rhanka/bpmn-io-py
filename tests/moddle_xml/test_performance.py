"""Ported moddle-xml performance cases (Lot 6).

Transcribes ``moddle-xml/test/spec/performance.js`` (4 claims) at full
``DEPTH``/``NS_DEPTH`` with no timeout adaptation: the cases run within
default limits, so no runner-specific timeout is ported. Only the public
``bpmn_io.moddle_xml`` API plus model building via ``bpmn_io.moddle`` is
used.
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


# performance


DEPTH = 50000

NS_DEPTH = 1500


def _create_deep_xml(depth: int) -> str:
    """Build a deeply nested document, as the upstream helper does."""
    return (
        '<props:complexNesting xmlns:props="http://properties" id="root">'
        + "<props:complexNesting>" * (depth - 1)
        + "<props:complexNesting />"
        + "</props:complexNesting>" * (depth - 1)
        + "</props:complexNesting>"
    )


def _create_deep_moddle(model: Moddle, depth: int) -> object:
    """Build a deeply nested element tree, as the upstream helper does."""
    root = model.create("props:ComplexNesting", {"id": "root"})
    parent = root
    for _ in range(depth):
        child = model.create("props:ComplexNesting")
        parent.get("nested").append(child)
        parent = child
    return root


def _nesting_depth(element: object) -> int:
    """Count nesting levels by walking ``nested`` links iteratively."""
    depth = 0
    nested = element.get("nested")
    while len(nested):
        depth += 1
        nested = nested[0].get("nested")
    return depth


def _write(element: object) -> str:
    """Serialize without preamble, as the upstream helper does."""
    return Writer(preamble=False).to_xml(element)


def _create_deep_namespace_xml(depth: int) -> str:
    """Build a deeply nested-namespace document, as the upstream helper does."""
    open_xml = '<e:root xmlns:e="http://extensions">'
    close_xml = "</e:root>"
    for i in range(depth - 1):
        open_xml += f'<p{i}:e xmlns:p{i}="urn:{i}">'
        close_xml = f"</p{i}:e>" + close_xml
    open_xml += f'<p{depth - 1}:e xmlns:p{depth - 1}="urn:{depth - 1}" />'
    return open_xml + close_xml


@pytest.mark.upstream("moddle-xml/test/spec/performance.js", "should write deeply nested document")
def test_016_write_deeply_nested_document() -> None:
    model = _model("properties")
    root = _create_deep_moddle(model, DEPTH)

    xml = _write(root)

    element_count = xml.count("<props:complexNesting")

    assert element_count == DEPTH + 1


@pytest.mark.upstream("moddle-xml/test/spec/performance.js", "should read deeply nested document")
def test_017_read_deeply_nested_document() -> None:
    model = _model("properties")
    reader = Reader(model)

    result = reader.from_xml(_create_deep_xml(DEPTH), reader.handler("props:ComplexNesting"))

    assert result.root_element.get("id") == "root"
    assert _nesting_depth(result.root_element) == DEPTH


@pytest.mark.upstream(
    "moddle-xml/test/spec/performance.js", "should round-trip deeply nested document"
)
def test_018_round_trip_deeply_nested_document() -> None:
    model = _model("properties")
    reader = Reader(model)
    xml = _create_deep_xml(DEPTH)

    result = reader.from_xml(xml, reader.handler("props:ComplexNesting"))

    assert _write(result.root_element) == xml


@pytest.mark.upstream(
    "moddle-xml/test/spec/performance.js", "should round-trip deeply nested namespaces"
)
def test_019_round_trip_deeply_nested_namespaces() -> None:
    model = _model("extensions")
    reader = Reader(model)
    xml = _create_deep_namespace_xml(NS_DEPTH)

    result = reader.from_xml(xml, reader.handler("e:Root"))

    assert _write(result.root_element) == xml
