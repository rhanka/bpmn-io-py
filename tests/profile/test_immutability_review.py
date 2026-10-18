"""Immutability boundary regressions (finding #6).

Inputs, compilation products and reads are isolated by deep copies (or
fresh immutable structures): mutating caller objects or returned payloads
must never change committed or compiled state.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
MECHANISM = ROOT / "contracts" / "profile-mechanism" / "1"


def _identity() -> dict[str, Any]:
    return {
        "mechanismVersion": "1",
        "schemaVersion": "1.0.0",
        "profile": "neutral/1",
        "version": "1.0.0",
        "sha256": "00" * 32,
        "base": {"id": "neutral-base/1", "version": "1.0.0", "sha256": "11" * 32},
        "descriptors": [{"id": "neutral-descriptors/1", "version": "1.0.0", "sha256": "22" * 32}],
    }


def _tree() -> dict[str, Any]:
    return {
        "$type": "bpmn:Definitions",
        "id": "D1",
        "rootElements": [{"$type": "bpmn:Process", "id": "P1", "name": "n"}],
    }


def test_complete_envelope_is_input_isolated() -> None:
    """Mutating the caller's tree after completing changes nothing."""
    from bpmn_io.profile import complete_envelope

    tree = _tree()
    envelope = complete_envelope(_identity(), tree, [])
    revision = envelope.semantic_revision
    tree["id"] = "MUT"
    tree["rootElements"][0]["name"] = "MUT"  # type: ignore[index]
    tree["rootElements"].append({"$type": "bpmn:Task", "id": "MUT"})  # type: ignore[attr-defined]
    assert envelope.tree["id"] == "D1"
    assert envelope.semantic_revision == revision


def test_compile_is_input_isolated() -> None:
    """Mutating the loaded profile after compiling changes nothing."""
    from bpmn_io.profile import compile_profile, load_profile

    schema = (MECHANISM / "profile-mechanism-1.schema.json").read_bytes()
    data = (MECHANISM / "neutral-profile.json").read_bytes()
    loaded = load_profile(data, schema_bytes=schema)
    assert loaded.status == "ok", loaded
    compiled = compile_profile(loaded.payload)  # type: ignore[arg-type]
    assert compiled.status == "ok", compiled
    rules_before = json.dumps(compiled.payload.rules, sort_keys=True)  # type: ignore[union-attr]
    profile = loaded.payload.profile  # type: ignore[union-attr]
    assert isinstance(profile, dict)
    rules = profile["rules"]
    assert isinstance(rules, list)
    first = rules[0]
    assert isinstance(first, dict)
    first["assert"] = {"op": "false"}
    profile["recipes"] = []
    assert json.dumps(compiled.payload.rules, sort_keys=True) == rules_before  # type: ignore[union-attr]


def test_descriptor_context_is_input_isolated() -> None:
    """Mutating packages after building the context changes nothing."""
    from bpmn_io.profile import create_descriptor_context

    profile = json.loads((MECHANISM / "neutral-profile.json").read_bytes())
    assert isinstance(profile, dict)
    raw = (MECHANISM / "neutral-descriptors.json").read_bytes()
    packages = [{**entry, "descriptorBytes": raw} for entry in profile["descriptors"]]
    context = create_descriptor_context(packages)  # type: ignore[arg-type]
    assert context.status == "ok", context
    snapshot = copy.deepcopy(context.payload.types)  # type: ignore[union-attr]
    packages[0]["id"] = "MUT"
    assert context.payload.types == snapshot  # type: ignore[union-attr]


def test_bridge_reads_are_copies() -> None:
    """Mutating a returned payload leaves the session untouched."""
    from bpmn_io.profile import HeadlessBridge, complete_envelope

    bridge = HeadlessBridge()
    loaded = bridge.set_definitions(complete_envelope(_identity(), _tree(), []))
    assert loaded.status == "ok", loaded
    first = bridge.get_definitions()
    assert first.status == "ok", first
    payload = first.payload  # type: ignore[union-attr]
    payload["tree"]["id"] = "MUT"
    payload["tree"]["rootElements"].append({"$type": "bpmn:Task", "id": "MUT"})
    second = bridge.get_definitions()
    assert second.status == "ok", second
    again = second.payload  # type: ignore[union-attr]
    assert again["tree"]["id"] == "D1"
    assert len(again["tree"]["rootElements"]) == 1


def test_bridge_writes_are_copies() -> None:
    """Mutating the supplied envelope after loading changes nothing."""
    from bpmn_io.profile import HeadlessBridge, complete_envelope

    bridge = HeadlessBridge()
    envelope = complete_envelope(_identity(), _tree(), [])
    loaded = bridge.set_definitions(envelope)
    assert loaded.status == "ok", loaded
    revision = envelope.semantic_revision
    stored = bridge.get_definitions()
    assert stored.status == "ok", stored
    assert stored.payload["semanticRevision"] == revision  # type: ignore[union-attr]


def test_read_context_notions_are_copies() -> None:
    """Mutating notions after building the context changes evaluation."""
    from bpmn_io.profile import evaluate_predicate
    from bpmn_io.profile._evaluate import make_read_context

    notions = {
        "aid": {
            "recognition": {
                "op": "typeIs",
                "binding": "self",
                "type": "bpmn:TextAnnotation",
                "mode": "exact",
            }
        }
    }
    note = {"$type": "bpmn:TextAnnotation", "id": "N1"}
    root = {"$type": "bpmn:Definitions", "rootElements": [note]}
    context = make_read_context(root, notions=notions)
    notions["aid"] = {"recognition": {"op": "false"}}
    predicate = {"op": "recognizes", "binding": "item", "notion": "aid"}
    result = evaluate_predicate(predicate, context, {"item": note})
    assert result.status == "ok", result
    assert result.payload is True  # type: ignore[union-attr]
