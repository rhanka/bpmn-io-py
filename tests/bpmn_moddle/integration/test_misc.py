"""Ported bpmn-moddle drools integration cases (Lot 7).

Transcribes every ``bpmn-moddle/test/integration/misc.js`` ``it()`` title:
one test per claim (2 claims: importing and exporting ``drools:Import``).
Only the public ``bpmn_io`` API plus the ``tests._matchers`` helper is used.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from bpmn_io import create_moddle
from tests._matchers import json_equal

if TYPE_CHECKING:
    from bpmn_io.bpmn_moddle import BpmnModdle

FIXTURES = (
    Path(__file__).resolve().parent.parent.parent / "upstream" / "bpmn-moddle" / "test" / "fixtures"
)


def _moddle() -> BpmnModdle:
    """Create the model with the ``drools`` extension package, as upstream."""
    descriptor: dict[str, Any] = json.loads(
        (FIXTURES / "json" / "model" / "drools.json").read_text(encoding="utf-8")
    )
    return create_moddle({"drools": descriptor})


@pytest.mark.upstream("bpmn-moddle/test/integration/misc.js", "should import")
def test_001_drools_import() -> None:
    moddle = _moddle()
    xml = (FIXTURES / "bpmn" / "extension" / "drools.part.bpmn").read_text(encoding="utf-8")

    result = moddle.from_xml(xml, "bpmn:Process")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:Process",
            "id": "Evaluation",
            "isExecutable": False,
            "extensionElements": {
                "$type": "bpmn:ExtensionElements",
                "values": [{"$type": "drools:Import", "name": "com.example.model.User"}],
            },
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/integration/misc.js", "should export")
def test_002_drools_export() -> None:
    moddle = _moddle()
    import_element = moddle.create("drools:Import", {"name": "com.example.model.User"})
    process_element = moddle.create(
        "bpmn:Process",
        {
            "extensionElements": moddle.create(
                "bpmn:ExtensionElements", {"values": [import_element]}
            )
        },
    )

    expected_xml = (
        '<bpmn:process xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:drools="http://www.jboss.org/drools">'
        "<bpmn:extensionElements>"
        '<drools:import name="com.example.model.User" />'
        "</bpmn:extensionElements>"
        "</bpmn:process>"
    )

    assert moddle.to_xml(process_element, {"preamble": False}).xml == expected_xml
