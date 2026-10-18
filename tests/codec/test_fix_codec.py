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


def test_fix10_generic_in_typed_slot_refuses() -> None:
    """A generic node in `documentation` refuses with descriptor-mismatch."""
    from bpmn_io.codec import hydrate

    wire = {
        "$type": "bpmn:Task",
        "id": "T1",
        "documentation": [
            {
                "$type": "$any",
                "$name": {"qname": "ven:note", "uri": VEN_URI},
                "$attrs": {},
            }
        ],
        "$attrs": {},
    }
    result = hydrate(wire)
    assert not result.ok
    assert [d.code for d in result.diagnostics] == ["descriptor-mismatch"]


def test_fix10_reference_target_type_checked() -> None:
    """A Process as SequenceFlow.sourceRef refuses with descriptor-mismatch."""
    from bpmn_io.codec import hydrate

    wire = {
        "$type": "bpmn:Definitions",
        "id": "D",
        "targetNamespace": "http://example.com/x",
        "rootElements": [
            {
                "$type": "bpmn:Process",
                "id": "P",
                "flowElements": [
                    {
                        "$type": "bpmn:SequenceFlow",
                        "id": "F1",
                        "sourceRef": {"$ref": "P"},
                        "targetRef": {"$ref": "T1"},
                    },
                    {"$type": "bpmn:Task", "id": "T1"},
                ],
            }
        ],
        "$attrs": {},
    }
    result = hydrate(wire)
    assert not result.ok
    assert [d.code for d in result.diagnostics] == ["descriptor-mismatch"]


def test_fix10_reference_valid_target_resolves() -> None:
    """A Task as SequenceFlow.sourceRef still resolves with identity."""
    from bpmn_io.codec import hydrate

    wire = {
        "$type": "bpmn:Definitions",
        "id": "D",
        "targetNamespace": "http://example.com/x",
        "rootElements": [
            {
                "$type": "bpmn:Process",
                "id": "P",
                "flowElements": [
                    {
                        "$type": "bpmn:SequenceFlow",
                        "id": "F1",
                        "sourceRef": {"$ref": "T1"},
                        "targetRef": {"$ref": "T1"},
                    },
                    {"$type": "bpmn:Task", "id": "T1"},
                ],
            }
        ],
        "$attrs": {},
    }
    result = hydrate(wire)
    assert result.ok, result.diagnostics
    flow = result.value.get("rootElements")[0].get("flowElements")[0]
    task = result.value.get("rootElements")[0].get("flowElements")[1]
    assert flow.get("sourceRef") is task


def test_fix10_empty_collection_survives_round_trip() -> None:
    """An explicit flowElements:[] is still present after hydrate->project."""
    from bpmn_io.codec import hydrate, project

    wire = {"$type": "bpmn:Process", "id": "P", "flowElements": [], "$attrs": {}}
    hydrated = hydrate(wire)
    assert hydrated.ok, hydrated.diagnostics
    projected = project(hydrated.value)
    assert projected.ok, projected.diagnostics
    assert projected.value == wire


def _generic_chain(count: int) -> dict:
    """A root generic wrapping `count` nested generics through $children."""
    node = {"$type": "$any", "$name": {"qname": "ven:leaf", "uri": VEN_URI}, "$attrs": {}}
    for _ in range(count):
        node = {
            "$type": "$any",
            "$name": {"qname": "ven:l", "uri": VEN_URI},
            "$attrs": {},
            "$children": [node],
        }
    return node


@pytest.mark.parametrize(
    ("depth", "ok"),
    [(255, True), (256, True), (257, False)],
)
def test_fix11_depth_counts_agree(depth: int, *, ok: bool) -> None:
    """Hydrate and project share one depth: both pass or both refuse."""
    from bpmn_io.codec import hydrate, project

    hydrated = hydrate(_generic_chain(depth - 1))
    assert hydrated.ok == ok, hydrated.diagnostics
    if not ok:
        assert [d.code for d in hydrated.diagnostics] == ["xml-depth-limit"]
        return
    projected = project(hydrated.value)
    assert projected.ok, projected.diagnostics


def _many_attr_generic(count: int) -> object:
    """A native generic element carrying `count` string attributes."""
    from bpmn_io.codec._model import build_model

    model, _ = build_model(None)
    element = model.create_any("ven:e", VEN_URI)
    for index in range(count):
        element[f"a{index}"] = "v"
    return element


def test_fix11_project_enforces_attribute_count() -> None:
    """1025 generic attributes refuse project, like they refuse hydrate."""
    from bpmn_io.codec import project

    result = project(_many_attr_generic(1025))
    assert not result.ok
    assert [d.code for d in result.diagnostics] == ["xml-attribute-count-limit"]
    assert project(_many_attr_generic(1024)).ok


def test_fix11_serialize_enforces_attribute_count() -> None:
    """1025 generic attributes refuse F7 with the same count code."""
    from bpmn_io.codec import serialize_xml

    result = serialize_xml(_many_attr_generic(1025))
    assert not result.ok
    assert [d.code for d in result.diagnostics] == ["xml-attribute-count-limit"]


def test_fix11_size_engine_agrees_with_bytes() -> None:
    """canonical_size equals len(canonical_bytes) on nested mixed data."""
    from bpmn_io.codec._jcs import canonical_bytes, canonical_size

    data = {
        "$type": "dc:Bounds",
        "x": 1e-6,
        "y": [1, 2.5, -0.0, {"k": "v", "n": None, "t": True}],
        "$attrs": {"a": "é"},
    }
    assert canonical_size(data) == len(canonical_bytes(data))


def test_fix11_hydrate_enforces_name_length_limit() -> None:
    """A name-length limit of 1 refuses a 10-char $attrs key on hydrate."""
    from bpmn_io.codec import hydrate

    wire = {
        "$type": "$any",
        "$name": {"qname": "ven:root", "uri": VEN_URI},
        "$attrs": {"k" * 10: "v"},
    }
    result = hydrate(wire, limits={"xml-attr-name-utf16": 1})
    assert not result.ok
    assert [d.code for d in result.diagnostics] == ["xml-attribute-length-limit"]
