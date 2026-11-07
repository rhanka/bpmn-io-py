"""Block-B R1-09: layout recognition refusals are non-match.

An inner recognition refusal (here a name read on an unnamed task) is a
non-match exactly as through the `recognizes` boundary, so public theme
resolution keeps returning `ok` with a `render-unsupported` diagnostic for
that task instead of raising; any refusal of a recognition body is a
non-match (R2-03).
"""

from __future__ import annotations

import copy
import json


def _compile_extended() -> tuple[object, object]:
    """Compile the neutral profile with an extended task recognition."""
    from bpmn_io.profile import compile_profile, create_descriptor_context, load_profile
    from tests.profile_commands import harness as h

    raw = (h.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
    profile = json.loads(raw.decode("utf-8"))
    task = next(n for n in profile.get("notions", []) if n.get("id") == "task")
    original = copy.deepcopy(task.get("recognition"))
    task["recognition"] = {
        "op": "all",
        "args": [
            original,
            {
                "op": "present",
                "value": {
                    "op": "concat",
                    "values": [
                        {"op": "literal", "value": "v:"},
                        {"op": "read", "binding": "self", "path": "/name"},
                    ],
                },
            },
        ],
    }
    package = dict(h.DEFAULT_DESCRIPTOR_PIN)
    package["descriptorBytes"] = h.DEFAULT_DESCRIPTOR_BYTES
    pins = [
        {
            "id": package["id"],
            "version": package["version"],
            "sha256": package["sha256"],
        }
    ]
    load_result = load_profile(
        json.dumps(profile).encode("utf-8"),
        schema_bytes=h.SCHEMA_BYTES,
        base_bytes=h.BASE_BYTES,
        descriptor_pins=pins,
        asset_bag=dict(h.METRICS_BAG),
    )
    assert load_result.status == "ok", load_result.to_json()
    context_result = create_descriptor_context([package])
    assert context_result.status == "ok", context_result.to_json()
    compile_result = compile_profile(
        load_result.payload,  # type: ignore[arg-type]
        descriptor_context=context_result.payload,  # type: ignore[arg-type]
        base=copy.deepcopy(h.BASE_DOCUMENT),
    )
    assert compile_result.status == "ok", compile_result.to_json()
    return context_result.payload, compile_result.payload  # type: ignore[return-value]


def _tree() -> dict:
    """Return one envelope tree with an unnamed task and valid geometry."""
    return {
        "$type": "bpmn:Definitions",
        "id": "D_1",
        "targetNamespace": "urn:x",
        "rootElements": [
            {
                "$type": "bpmn:Process",
                "id": "P_1",
                "flowElements": [
                    {"$type": "bpmn:Task", "id": "Task_1"},
                    {"$type": "bpmn:Task", "id": "Task_2", "name": "Fixed"},
                ],
            },
        ],
        "diagrams": [
            {
                "$type": "bpmndi:BPMNDiagram",
                "id": "d1",
                "plane": {
                    "$type": "bpmndi:BPMNPlane",
                    "bpmnElement": "P_1",
                    "planeElement": [
                        {
                            "$type": "bpmndi:BPMNShape",
                            "id": "s1",
                            "bpmnElement": "Task_1",
                            "bounds": {"x": 10, "y": 20, "width": 100, "height": 80},
                        },
                        {
                            "$type": "bpmndi:BPMNShape",
                            "id": "s2",
                            "bpmnElement": "Task_2",
                            "bounds": {"x": 150, "y": 20, "width": 100, "height": 80},
                        },
                    ],
                },
            }
        ],
    }


def _resolve(compiled: object) -> object:
    """Run compute_layout then resolve_theme over the unnamed-task tree."""
    from bpmn_io.profile import complete_envelope
    from bpmn_io.profile._envelope import make_imported_di
    from bpmn_io.profile._layout import compute_layout
    from bpmn_io.profile._render import resolve_theme
    from bpmn_io.profile._render_digest import descriptor_digest
    from bpmn_io.profile._ui import compiled_identity

    identity = compiled_identity(compiled)  # type: ignore[arg-type]
    tree = _tree()
    envelope = complete_envelope(identity, copy.deepcopy(tree), [])
    imported = make_imported_di(tree, descriptor_digest(identity.get("descriptors")))  # type: ignore[arg-type]
    staged = compute_layout(compiled, envelope, [], imported, theme_id="plain")
    assert getattr(staged, "status", None) == "ok", getattr(staged, "to_json", lambda: staged)()
    return resolve_theme(
        compiled,
        envelope,
        staged.payload,  # type: ignore[union-attr]
        "plain",
        {"semantic": [], "occurrence": []},
        {"native": [], "bioc": []},
    )


def test_r109_inner_recognition_refusal_is_non_match() -> None:
    """An unnamed task with a refusing recognition still resolves ok."""
    _, compiled = _compile_extended()
    out = _resolve(compiled)
    assert getattr(out, "status", None) == "ok", getattr(out, "to_json", lambda: out)()
    payload = out.payload  # type: ignore[union-attr]
    unsupported = [
        entry
        for entry in payload.get("diagnostics", [])
        if entry.get("code") == "render-unsupported"
    ]
    assert any(
        entry.get("targetId") == "Task_1" or "Task_1" in json.dumps(entry) for entry in unsupported
    ), payload.get("diagnostics")


def test_r109_outer_binding_refusal_is_non_match() -> None:
    """An owner-dependent recognition refusal is a non-match (R2-03)."""
    from bpmn_io.profile import compile_profile, create_descriptor_context, load_profile
    from tests.profile_commands import harness as h

    raw = (h.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
    profile = json.loads(raw.decode("utf-8"))
    task = next(n for n in profile.get("notions", []) if n.get("id") == "task")
    original = copy.deepcopy(task.get("recognition"))
    task["recognition"] = {
        "op": "all",
        "args": [
            original,
            {
                "op": "equal",
                "left": {"op": "id", "binding": "bindingOwner"},
                "right": {"op": "id", "binding": "self"},
            },
        ],
    }
    package = dict(h.DEFAULT_DESCRIPTOR_PIN)
    package["descriptorBytes"] = h.DEFAULT_DESCRIPTOR_BYTES
    pins = [
        {
            "id": package["id"],
            "version": package["version"],
            "sha256": package["sha256"],
        }
    ]
    load_result = load_profile(
        json.dumps(profile).encode("utf-8"),
        schema_bytes=h.SCHEMA_BYTES,
        base_bytes=h.BASE_BYTES,
        descriptor_pins=pins,
        asset_bag=dict(h.METRICS_BAG),
    )
    assert load_result.status == "ok", load_result.to_json()
    context_result = create_descriptor_context([package])
    assert context_result.status == "ok", context_result.to_json()
    compile_result = compile_profile(
        load_result.payload,  # type: ignore[arg-type]
        descriptor_context=context_result.payload,  # type: ignore[arg-type]
        base=copy.deepcopy(h.BASE_DOCUMENT),
    )
    assert compile_result.status == "ok", compile_result.to_json()
    from bpmn_io.profile import complete_envelope
    from bpmn_io.profile._envelope import make_imported_di
    from bpmn_io.profile._layout import compute_layout
    from bpmn_io.profile._render_digest import descriptor_digest
    from bpmn_io.profile._ui import compiled_identity

    compiled = compile_result.payload
    identity = compiled_identity(compiled)  # type: ignore[arg-type]
    tree = _tree()
    envelope = complete_envelope(identity, copy.deepcopy(tree), [])
    imported = make_imported_di(tree, descriptor_digest(identity.get("descriptors")))  # type: ignore[arg-type]
    out = compute_layout(compiled, envelope, [], imported, theme_id="plain")
    assert getattr(out, "status", None) == "ok", getattr(out, "to_json", lambda: out)()
