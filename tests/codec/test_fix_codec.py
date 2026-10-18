"""Regression tests for the fix round: reviewer probes, one test per finding."""

from __future__ import annotations

import pytest

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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1e-6, '{"v":0.000001}'),
        (1e21, '{"v":1e+21}'),
        (-0.0, '{"v":0}'),
        (5e-324, '{"v":5e-324}'),
        (0.1 + 0.2, '{"v":0.30000000000000004}'),
        (1e-7, '{"v":1e-7}'),
        (1e20, '{"v":100000000000000000000}'),
        (100000.0, '{"v":100000}'),
    ],
)
def test_fix12_jcs_number_rendering(value: float, expected: str) -> None:
    """Codec JCS renders numbers like the Node canonicalize reference."""
    from bpmn_io.codec._model import c14n_bytes

    assert c14n_bytes({"v": value}).decode("utf-8") == expected


def test_fix12_jcs_key_order_astral_before_bmp() -> None:
    """UTF-16 order puts U+10000 before U+E000 (code-point order would not)."""
    from bpmn_io.codec._model import c14n_bytes

    assert c14n_bytes({"": 1, "𐀀": 2}).decode("utf-8") == '{"𐀀":2,"":1}'


def test_fix12_object_size_uses_true_jcs_length() -> None:
    """Hydrate enforces the Node-established JCS size, not the short rendering."""
    from bpmn_io.codec import hydrate
    from bpmn_io.codec._model import c14n_bytes

    wire = {"$type": "dc:Bounds", "x": 1e-6, "$attrs": {}}
    assert c14n_bytes(wire).decode("utf-8") == '{"$attrs":{},"$type":"dc:Bounds","x":0.000001}'
    size = len(c14n_bytes(wire))
    refused = hydrate(wire, limits={"json-object-bytes": size - 1})
    assert not refused.ok
    assert [d.code for d in refused.diagnostics] == ["xml-input-size-limit"]
    assert hydrate(wire, limits={"json-object-bytes": size}).ok
