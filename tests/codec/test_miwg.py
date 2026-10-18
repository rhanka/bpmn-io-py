"""MIWG originals: pinned bytes, foreign-attribute coverage and full round trips."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from bpmn_io.codec import hydrate, parse_xml, project, serialize_xml

MIWG = Path(__file__).resolve().parent.parent.parent / "contracts" / "f1-extensions" / "1" / "miwg"

PINNED = {
    "B.1.0.bpmn": "cf3764f7a15a7f3402eabcc0a90dd67c81d29a3512e3cf959792dd1d27fe77e2",
    "C.4.0.bpmn": "7edfadee4c488f7192bca9313613e2b3fb14634c073bc9d759823d0cc8a7faf7",
    "C.5.0.bpmn": "f8c125a7c492d218d1f6962fe03920bec4b1e4a9c2efae0746926667a67f44cc",
    "LICENSE.txt": "c2d2fd90db5f6fd71d942918bf935ab393d0826c3e354c7e32f065b902899755",
}


def test_miwg_bytes_match_pinned_hashes() -> None:
    """Raw bytes equal the F1 plan table before any decoding."""
    for name, digest in PINNED.items():
        assert hashlib.sha256((MIWG / name).read_bytes()).hexdigest() == digest, name


def _wire(name: str) -> dict:
    raw = (MIWG / f"{name}.bpmn").read_bytes()
    parsed = parse_xml(raw)
    assert parsed.ok, (name, parsed.diagnostics)
    projected = project(parsed.value)
    assert projected.ok, (name, projected.diagnostics)
    assert isinstance(projected.value, dict)
    return projected.value


def _count(node: object, type_name: str) -> int:
    if isinstance(node, dict):
        total = 1 if node.get("$type") == type_name else 0
        return total + sum(_count(v, type_name) for k, v in node.items() if k != "$type")
    if isinstance(node, list):
        return sum(_count(v, type_name) for v in node)
    return 0


def _non_empty_attrs(node: object) -> list[dict]:
    found: list[dict] = []
    if isinstance(node, dict):
        attrs = node.get("$attrs")
        if isinstance(attrs, dict) and attrs:
            found.append(attrs)
        for key, value in node.items():
            if key != "$attrs":
                found.extend(_non_empty_attrs(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_non_empty_attrs(value))
    return found


def test_miwg_has_no_extension_elements() -> None:
    """The pinned originals carry zero extensionElements (plan C5 addendum)."""
    for name in ("B.1.0", "C.4.0", "C.5.0"):
        assert _count(_wire(name), "bpmn:ExtensionElements") == 0, name


def test_miwg_foreign_attributes_preserved() -> None:
    """Declarations and vendor-namespace attributes survive the projection."""
    for name in ("B.1.0", "C.4.0", "C.5.0"):
        attrs = _non_empty_attrs(_wire(name))
        assert attrs, name
    c4 = _non_empty_attrs(_wire("C.4.0"))
    joined = json.dumps(c4)
    assert "trisobpmn:logoChoice" in joined
    assert "trisobpmn:diagramWidth" in joined


def test_miwg_expected_diagnostics() -> None:
    """B.1.0 warns once (ISO-8859-1 fallback); C.4.0/C.5.0 are silent."""
    b1 = parse_xml((MIWG / "B.1.0.bpmn").read_bytes())
    assert b1.ok
    assert [(d.code, d.path, d.target) for d in b1.diagnostics] == [("moddle-warning", None, None)]
    for name in ("C.4.0", "C.5.0"):
        result = parse_xml((MIWG / f"{name}.bpmn").read_bytes())
        assert result.ok
        assert result.diagnostics == (), name


def _first_by_type(node: object, type_name: str) -> dict | None:
    if isinstance(node, dict):
        if node.get("$type") == type_name:
            return node
        for key, value in node.items():
            if key != "$type":
                found = _first_by_type(value, type_name)
                if found is not None:
                    return found
    elif isinstance(node, list):
        for value in node:
            found = _first_by_type(value, type_name)
            if found is not None:
                return found
    return None


def test_miwg_round_trip_and_stabilization() -> None:
    """XML to native to JSON to native: fixed; F7 drops explicit defaults once, then stable."""
    for name in ("B.1.0", "C.4.0", "C.5.0"):
        raw = (MIWG / f"{name}.bpmn").read_bytes()
        first = project(parse_xml(raw).value)
        assert first.ok
        rehydrated = hydrate(first.value)
        assert rehydrated.ok, (name, rehydrated.diagnostics)
        second = project(rehydrated.value)
        assert second.ok, name
        assert second.value == first.value, name
        serialized = serialize_xml(rehydrated.value)
        assert serialized.ok, (name, serialized.diagnostics)
        restable = project(parse_xml(serialized.value).value)
        assert restable.ok, name
        reserialized = serialize_xml(hydrate(restable.value).value)
        assert reserialized.ok, name
        restable2 = project(parse_xml(reserialized.value).value)
        assert restable2.ok, name
        assert restable2.value == restable.value, name


def _native(node: object, wanted_id: str, seen: set[int]) -> object:
    """Find one native element by id, skipping links that loop upward."""
    if id(node) in seen or not hasattr(node, "__dict__"):
        return None
    seen.add(id(node))
    if hasattr(node, "descriptor_") and node.get("id") == wanted_id:
        return node
    for key, value in vars(node).items():
        if key in ("parent_", "model_", "descriptor_"):
            continue
        candidates = value if isinstance(value, list) else [value]
        for item in candidates:
            if hasattr(item, "__dict__"):
                found = _native(item, wanted_id, seen)
                if found is not None:
                    return found
    return None


def test_miwg_known_field_edit_changes_projection() -> None:
    """Comparator mutations fail: editing a retained field changes the wire."""
    raw = (MIWG / "C.4.0.bpmn").read_bytes()
    before = project(parse_xml(raw).value).value
    target = _first_by_type(before, "bpmn:Process")
    assert target is not None
    root = hydrate(before).value

    native = _native(root, target["id"], set())
    assert native is not None
    native.set("name", "mutated-process-name")
    after = project(root).value
    assert after != before
    assert _first_by_type(after, "bpmn:Process")["name"] == "mutated-process-name"


def test_miwg_parses_are_isolated() -> None:
    """Two parses of one original give equal wires on distinct objects."""
    raw = (MIWG / "C.5.0.bpmn").read_bytes()
    first = project(parse_xml(raw).value).value
    second = project(parse_xml(raw).value).value
    assert first == second
