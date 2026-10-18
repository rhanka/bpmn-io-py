"""Regression tests for the fix round: reviewer probes, one test per finding."""

from __future__ import annotations

from bpmn_io.codec import parse_xml

MODEL_URI = "http://www.omg.org/spec/BPMN/20100524/MODEL"
VEN_URI = "http://example.com/vendor"


def _doc(inner: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<bpmn:definitions xmlns:bpmn="{MODEL_URI}" id="D">{inner}</bpmn:definitions>'
    )


def test_fix7_overlong_numeric_reference_refuses_typed() -> None:
    """A 5000-digit numeric reference refuses instead of raising ValueError."""
    xml = _doc(
        '<bpmn:process id="P"><bpmn:extensionElements>'
        f'<ven:n xmlns:ven="{VEN_URI}">a&#{"9" * 5000};b</ven:n>'
        "</bpmn:extensionElements></bpmn:process>"
    )
    result = parse_xml(xml)
    assert not result.ok
    assert [d.code for d in result.diagnostics] == ["xml-entity-reference-unsupported"]
