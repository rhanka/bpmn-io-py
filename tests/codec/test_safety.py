"""F1 safety-boundary tests: every limit at limit-1, limit and limit+1."""

from __future__ import annotations

import pytest

from bpmn_io.codec import hydrate, parse_xml, project
from bpmn_io.codec._model import LIMITS, utf16_len
from bpmn_io.codec.xml_boundary import check_count_limits

MODEL_URI = "http://www.omg.org/spec/BPMN/20100524/MODEL"
VEN_URI = "http://example.com/vendor"


def _doc(inner: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<bpmn:definitions xmlns:bpmn="{MODEL_URI}" id="D">{inner}</bpmn:definitions>'
    )


def _nested_generics(depth_below_process: int) -> str:
    inner = '<ven:leaf xmlns:ven="http://example.com/vendor" />'
    for _ in range(depth_below_process):
        inner = f'<ven:l xmlns:ven="{VEN_URI}">{inner}</ven:l>'
    return _doc(
        '<bpmn:process id="P"><bpmn:extensionElements>'
        f"{inner}</bpmn:extensionElements></bpmn:process>"
    )


@pytest.mark.parametrize(("total", "ok"), [(255, True), (256, True), (257, False)])
def test_xml_depth_boundaries(total: int, *, ok: bool) -> None:
    """Depth counts the root as 1: 255/256 pass, 257 refuses."""
    xml = _nested_generics(total - 4)
    result = parse_xml(xml)
    assert result.ok == ok
    if ok:
        assert result.diagnostics == ()
    else:
        assert [d.code for d in result.diagnostics] == ["xml-depth-limit"]


def _many_attrs(count: int) -> str:
    attrs = " ".join(f'a{i}="v"' for i in range(count))
    return _doc(
        f'<bpmn:process id="P"><bpmn:extensionElements><ven:e xmlns:ven="{VEN_URI}" {attrs} />'
        "</bpmn:extensionElements></bpmn:process>"
    )


@pytest.mark.parametrize(("data", "ok"), [(1022, True), (1023, True), (1024, False)])
def test_xml_attribute_count_boundaries(data: int, *, ok: bool) -> None:
    """Attribute bounds count declarations: 1022+1 and 1023+1 pass, 1024+1 refuses."""
    result = parse_xml(_many_attrs(data))
    assert result.ok == ok
    if not ok:
        assert [d.code for d in result.diagnostics] == ["xml-attribute-count-limit"]


@pytest.mark.parametrize(("delta", "ok"), [(-1, True), (0, True), (1, False)])
def test_xml_attribute_value_length_boundaries(delta: int, *, ok: bool) -> None:
    """One attribute value at UTF-16 limit-1/limit/limit+1."""
    size = LIMITS["xml-attr-value-utf16"] + delta
    value = "x" * size
    xml = _doc(
        f'<bpmn:process id="P"><bpmn:extensionElements><ven:e xmlns:ven="{VEN_URI}"'
        f' k="{value}" /></bpmn:extensionElements></bpmn:process>'
    )
    result = parse_xml(xml)
    assert result.ok == ok
    if not ok:
        assert [d.code for d in result.diagnostics] == ["xml-attribute-length-limit"]


@pytest.mark.parametrize(("delta", "ok"), [(-1, True), (0, True), (1, False)])
def test_xml_attribute_name_length_boundaries(delta: int, *, ok: bool) -> None:
    """One attribute name at UTF-16 limit-1/limit/limit+1."""
    size = LIMITS["xml-attr-name-utf16"] + delta
    attr_name = "k" * size
    xml = _doc(
        f'<bpmn:process id="P"><bpmn:extensionElements><ven:e xmlns:ven="{VEN_URI}"'
        f' {attr_name}="v" /></bpmn:extensionElements></bpmn:process>'
    )
    result = parse_xml(xml)
    assert result.ok == ok
    if not ok:
        assert [d.code for d in result.diagnostics] == ["xml-attribute-length-limit"]


def test_xml_input_size_boundaries() -> None:
    """Raw input bytes at limit-1/limit/limit+1 (padded generic body)."""
    limit = LIMITS["xml-input-bytes"]
    template = (
        '<?xml version="1.0"?>'
        f'<bpmn:definitions xmlns:bpmn="{MODEL_URI}" id="D">'
        f'<bpmn:process id="P"><bpmn:extensionElements><ven:p xmlns:ven="{VEN_URI}">'
        "{pad}"
        "</ven:p></bpmn:extensionElements></bpmn:process></bpmn:definitions>"
    )
    overhead = len(template.replace("{pad}", "").encode("utf-8"))
    for delta, ok in ((-1, True), (0, True), (1, False)):
        raw = template.replace("{pad}", "x" * (limit - overhead + delta)).encode("utf-8")
        assert len(raw) == limit + delta, (len(raw), delta)
        result = parse_xml(raw)
        assert result.ok == ok, (delta, result.diagnostics)
        if not ok:
            assert [d.code for d in result.diagnostics] == ["xml-input-size-limit"]


def test_xml_element_count_limit_plus_one_refuses_before_construction() -> None:
    """1,000,001 elements refuse in the pre-pass without building the tree."""
    count = LIMITS["xml-elements"]
    xml = "<r>" + '<i a="v"/>' * count + "</r>"
    diagnostics = check_count_limits(xml, dict(LIMITS))
    assert [d.code for d in diagnostics] == ["xml-element-count-limit"]


@pytest.mark.parametrize("delta", [-1, 0])
def test_xml_element_count_boundaries(delta: int) -> None:
    """Limit-1/limit element counts pass the pre-pass counter (unit level)."""
    count = LIMITS["xml-elements"] + delta - 1
    xml = "<r>" + '<i a="v"/>' * count + "</r>"
    assert check_count_limits(xml, dict(LIMITS)) == []


def test_json_object_size_boundaries() -> None:
    """Projected JCS object bytes at limit-1/limit/limit+1 refuse on hydrate.

    Bodies stay at the UTF-16 string limit so only the object-size bound trips.
    """
    from bpmn_io.codec._model import c14n_bytes

    limit = LIMITS["json-object-bytes"]
    string_limit = LIMITS["xml-attr-value-utf16"]

    def note_with(body_len: int) -> dict:
        return {
            "$type": "$any",
            "$name": {"qname": "ven:pad", "uri": VEN_URI},
            "$attrs": {},
            "$body": "x" * body_len,
        }

    def doc_with(body_len: int, count: int = 64) -> dict:
        return {
            "$type": "$any",
            "$name": {"qname": "ven:root", "uri": VEN_URI},
            "$attrs": {},
            "$children": [note_with(body_len) for _ in range(count)],
        }

    probe = doc_with(0)
    per_unit = (len(c14n_bytes(doc_with(1))) - len(c14n_bytes(probe))) // 64
    assert per_unit == 1
    overhead = len(c14n_bytes(probe))
    for delta, ok in ((-1, True), (0, True), (1, False)):
        total = limit + delta - overhead
        base, rest = divmod(total, 64)
        assert base < string_limit, base
        data = {
            "$type": "$any",
            "$name": {"qname": "ven:root", "uri": VEN_URI},
            "$attrs": {},
            "$children": [note_with(base + (1 if i < rest else 0)) for i in range(64)],
        }
        assert len(c14n_bytes(data)) == limit + delta, delta
        result = hydrate(data)
        assert result.ok == ok, (delta, result.diagnostics)
        if not ok:
            assert [d.code for d in result.diagnostics] == ["xml-input-size-limit"]


def test_warning_cap_1001() -> None:
    """1001 unknown registered-namespace attributes cap at 1000 + truncation."""
    attrs = " ".join(f'bpmn:bogus{i}="v"' for i in range(1001))
    xml = _doc(f'<bpmn:process id="P" {attrs} />')
    result = parse_xml(xml)
    assert result.ok
    codes = [d.code for d in result.diagnostics]
    assert codes[:1000] == ["moddle-warning"] * 1000
    assert codes[1000:] == ["moddle-warning-truncated"]
    assert len(result.diagnostics) == 1001
    assert result.diagnostics[1000].path == "/rootElements/0/bpmn:bogus1000"


def test_duplicate_expanded_attribute_refuses() -> None:
    """Same {URI, local} twice via aliases refuses before construction."""
    xml = _doc(f'<bpmn:process id="P" v:k="1" w:k="2" xmlns:v="{VEN_URI}" xmlns:w="{VEN_URI}" />')
    result = parse_xml(xml)
    assert not result.ok
    assert [d.code for d in result.diagnostics] == ["duplicate-attribute"]


def test_duplicate_namespace_refuses() -> None:
    """Same prefix declared twice refuses before construction."""
    xml = _doc(f'<bpmn:process id="P" xmlns:v="{VEN_URI}" xmlns:v="http://example.com/other" />')
    result = parse_xml(xml)
    assert not result.ok
    assert [d.code for d in result.diagnostics] == ["duplicate-namespace"]


def test_unbound_prefix_refuses() -> None:
    """Prefixed attribute without a binding refuses before construction."""
    xml = _doc('<bpmn:process id="P" nosuch:k="1" />')
    result = parse_xml(xml)
    assert not result.ok
    assert [d.code for d in result.diagnostics] == ["unbound-prefix"]


def test_malformed_qname_refuses() -> None:
    """A three-segment name refuses before construction."""
    xml = _doc(
        '<bpmn:process id="P"><bpmn:extensionElements>'
        '<a:b:c xmlns:a="http://example.com/a" /></bpmn:extensionElements></bpmn:process>'
    )
    result = parse_xml(xml)
    assert not result.ok
    assert [d.code for d in result.diagnostics] == ["malformed-qname"]


def test_garbage_input_is_xml_invalid() -> None:
    """A document without a root element fails the native reader as xml-invalid."""
    result = parse_xml("<!-- only a comment -->")
    assert not result.ok
    assert [d.code for d in result.diagnostics] == ["xml-invalid"]


def test_hydrate_unknown_type_refuses() -> None:
    """Unknown registered-type names refuse hydration."""
    result = hydrate({"$type": "bpmn:Nope", "$attrs": {}})
    assert not result.ok
    assert [d.code for d in result.diagnostics] == ["descriptor-mismatch"]


def test_hydrate_shared_child_refuses() -> None:
    """One dict object used as two children refuses (shared children)."""
    child = {
        "$type": "$any",
        "$name": {"qname": "ven:c", "uri": VEN_URI},
        "$attrs": {},
    }
    data = {
        "$type": "$any",
        "$name": {"qname": "ven:r", "uri": VEN_URI},
        "$attrs": {},
        "$children": [child, child],
    }
    result = hydrate(data)
    assert not result.ok
    assert [d.code for d in result.diagnostics] == ["descriptor-mismatch"]


def test_hydrate_recursive_input_refuses_without_hanging() -> None:
    """Cyclic Python input refuses instead of recursing forever."""
    data: dict = {
        "$type": "$any",
        "$name": {"qname": "ven:r", "uri": VEN_URI},
        "$attrs": {},
    }
    data["$children"] = [data]
    result = hydrate(data)
    assert not result.ok
    assert [d.code for d in result.diagnostics] == ["descriptor-mismatch"]


def test_hydrate_generic_name_validations() -> None:
    """Malformed qnames, empty-URI prefixes and bad shapes refuse."""
    base = {"$type": "$any", "$attrs": {}}
    cases = [
        ({**base, "$name": {"qname": "a:b:c", "uri": "http://example.com/x"}}, "malformed-qname"),
        ({**base, "$name": {"qname": "v:x", "uri": ""}}, "invalid-namespace"),
        ({**base, "$name": {"qname": "v:x", "uri": VEN_URI}, "$body": 3}, "invalid-any"),
        ({**base, "$name": {"qname": "v:x", "uri": VEN_URI}, "$children": {}}, "invalid-any"),
        ({**base}, "invalid-any"),
    ]
    for data, code in cases:
        result = hydrate(data)
        assert not result.ok, data
        assert [d.code for d in result.diagnostics] == [code], data


def test_reference_to_generic_id_warns() -> None:
    """Generic ids never enter the typed index: the reference just warns."""
    data = {
        "$type": "bpmn:Definitions",
        "id": "D",
        "$attrs": {},
        "rootElements": [
            {
                "$type": "bpmn:Process",
                "id": "P",
                "$attrs": {},
                "flowElements": [
                    {"$type": "bpmn:Task", "id": "T", "$attrs": {}},
                    {
                        "$type": "bpmn:SequenceFlow",
                        "id": "F",
                        "$attrs": {},
                        "sourceRef": {"$ref": "G"},
                        "targetRef": {"$ref": "T"},
                    },
                ],
                "extensionElements": {
                    "$type": "bpmn:ExtensionElements",
                    "$attrs": {},
                    "values": [
                        {
                            "$type": "$any",
                            "$name": {"qname": "ven:g", "uri": VEN_URI},
                            "$attrs": {"id": "G"},
                        },
                    ],
                },
            }
        ],
    }
    result = hydrate(data)
    assert result.ok
    assert [(d.code, d.path) for d in result.diagnostics] == [
        ("moddle-warning", "/rootElements/0/flowElements/1/sourceRef")
    ]
    flow = result.value.get("rootElements")[0].get("flowElements")[1]
    assert flow.get("targetRef").get("id") == "T"


def test_limits_override_and_validation() -> None:
    """Caller limits tighten enforcement; unknown names raise."""
    xml = _nested_generics(10)
    result = parse_xml(xml, limits={"xml-depth": 5})
    assert not result.ok
    assert [d.code for d in result.diagnostics] == ["xml-depth-limit"]
    with pytest.raises(ValueError, match="unknown limit"):
        parse_xml(xml, limits={"nope": 3})
    with pytest.raises(ValueError, match="non-negative int"):
        parse_xml(xml, limits={"xml-depth": -1})


def test_calls_are_isolated() -> None:
    """Per-call models share nothing: mutating one tree spares the next."""
    xml = _doc('<bpmn:process id="P" />')
    first = parse_xml(xml)
    second = parse_xml(xml)
    assert first.ok
    assert second.ok
    assert first.value is not second.value
    assert first.value.model_ is not second.value.model_
    first.value.set("name", "mutated")
    from bpmn_io._js import UNDEFINED

    assert second.value.get("name") is UNDEFINED


def test_utf16_counts_astral_as_two() -> None:
    """String limits count UTF-16 code units, not code points."""
    assert utf16_len("e") == 1
    assert utf16_len(chr(0x10000)) == 2
    assert utf16_len(chr(0xE000)) == 1


def test_project_rejects_shared_native_children() -> None:
    """A native tree with one child attached twice refuses projection."""
    from bpmn_io.bpmn_moddle.simple import create_moddle

    model = create_moddle()
    child = model.create_any("ven:c", VEN_URI)
    parent = model.create_any("ven:p", VEN_URI)
    parent["$children"] = [child, child]
    result = project(parent)
    assert not result.ok
    assert [d.code for d in result.diagnostics] == ["descriptor-mismatch"]
