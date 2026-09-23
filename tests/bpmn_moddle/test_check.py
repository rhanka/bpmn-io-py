"""Tests for the ``check`` integrity helper (Lot 7, L0 item).

``check`` lives in ``src/bpmn_io/check.py``; these tests sit next to it under
``tests/bpmn_moddle/`` (the only writable test tree for this lot) and cover
its contract: XML-string input, model-element input and invalid input. Only
the public ``bpmn_io`` API is used.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from bpmn_io import check, create_moddle

FIXTURES = (
    Path(__file__).resolve().parent.parent
    / "upstream"
    / "bpmn-moddle"
    / "test"
    / "fixtures"
    / "bpmn"
)


def test_valid_xml_is_ok_and_indexed() -> None:
    xml = (FIXTURES / "simple.bpmn").read_text(encoding="utf-8")

    report = check(xml)

    assert report.ok is True
    assert report.errors == []
    assert report.warnings == []
    assert report.elements_by_id["Process_1"].get("id") == "Process_1"


def test_xml_warnings_keep_ok() -> None:
    xml = (FIXTURES / "error" / "duplicate-ids.bpmn").read_text(encoding="utf-8")

    report = check(xml)

    assert report.ok is True
    assert report.errors == []
    assert len(report.warnings) == 1
    assert "duplicate ID <test>" in report.warnings[0].message


def test_unparsable_xml_is_not_ok() -> None:
    report = check("this is no xml")

    assert report.ok is False
    assert len(report.errors) == 1
    assert report.elements_by_id == {}


def test_xml_parse_error_message_surfaced() -> None:
    xml = (FIXTURES / "error" / "not-bpmn.bpmn").read_text(encoding="utf-8")

    report = check(xml)

    assert report.ok is False
    assert any("failed to parse document" in error for error in report.errors)


def test_custom_root_type() -> None:
    xml = '<bpmn:process xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="P" />'

    report = check(xml, "bpmn:Process")

    assert report.ok is True
    assert sorted(report.elements_by_id) == ["P"]


def test_element_with_unresolved_reference_is_not_ok() -> None:
    moddle = create_moddle()
    task = moddle.create("bpmn:Task", {"id": "Task_1"})
    flow = moddle.create("bpmn:SequenceFlow", {"id": "Flow_1"})
    flow.set("sourceRef", "Missing_1")
    process = moddle.create("bpmn:Process", {"id": "Process_1", "flowElements": [task, flow]})
    definitions = moddle.create(
        "bpmn:Definitions", {"id": "Definitions_1", "rootElements": [process]}
    )

    report = check(definitions)

    assert report.ok is False
    assert report.errors == ["unresolved reference <Missing_1>"]
    assert report.elements_by_id["Flow_1"] is flow


def test_element_with_unknown_attribute_is_not_ok() -> None:
    moddle = create_moddle()
    xml = (
        '<bpmn:process xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'id="P" bpmn:unknownAttr="BAR" />'
    )
    process = moddle.from_xml(xml, "bpmn:Process").root_element

    report = check(process)

    assert report.ok is False
    assert report.errors == ["unknown attribute <bpmn:unknownAttr>"]
    assert len(report.warnings) == 1
    assert report.warnings[0].property == "bpmn:unknownAttr"


def test_invalid_input_type_raises() -> None:
    with pytest.raises(TypeError, match="requires an XML string"):
        check(42)


def test_report_is_frozen() -> None:
    xml = (FIXTURES / "simple.bpmn").read_text(encoding="utf-8")

    report = check(xml)

    with pytest.raises(dataclasses.FrozenInstanceError):
        report.ok = False  # type: ignore[misc]
