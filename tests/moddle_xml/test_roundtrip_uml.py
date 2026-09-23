"""Ported moddle-xml UML roundtrip case (Lot 6).

Transcribes ``moddle-xml/test/spec/roundtrip.uml.js`` (1 claim):
``UML.xmi`` roundtrips after the upstream whitespace/entity normalization
(``"/>`` to ``" />"``, ``&#xD;`` stripped). Only the public
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


# Roundtrip - UML


@pytest.mark.upstream("moddle-xml/test/spec/roundtrip.uml.js", "should roundtrip UML")
def test_015_roundtrip_uml() -> None:
    model = _model("xmi")

    input_xml = (
        (XML_FIXTURES / "UML.xmi")
        .read_text(encoding="utf-8")
        .replace('"/>', '" />')
        .replace("&#xD;", "")
    )

    output = _roundtrip(model, "xmi:XMI", input_xml, format=True, preamble=True)

    assert output == input_xml
