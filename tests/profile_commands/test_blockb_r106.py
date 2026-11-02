"""Block-B R1-06 on the public surface: owner label without owner refuses.

Task render label ``id(bindingOwner)`` with no owner bound refuses
``profile-symbol`` through ``resolve_theme``.
"""

from __future__ import annotations

import copy
import json


def _resolve_with_owner_label() -> object:
    """Resolve neutral lot-5 with an owner-dependent task label."""
    from bpmn_io.profile import (
        compile_profile,
        complete_envelope,
        create_descriptor_context,
        load_profile,
    )
    from bpmn_io.profile._render import resolve_theme
    from tests.profile_commands import harness as h

    raw = (h.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
    profile = json.loads(raw.decode("utf-8"))
    task = next(n for n in profile.get("notions", []) if n.get("id") == "task")
    binding = next(b for b in task.get("renderBindings", []) if b.get("theme") == "plain")
    binding["label"] = {"op": "id", "binding": "bindingOwner"}
    package = dict(h.DEFAULT_DESCRIPTOR_PIN)
    package["descriptorBytes"] = h.DEFAULT_DESCRIPTOR_BYTES
    pins = [{"id": package["id"], "version": package["version"], "sha256": package["sha256"]}]
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
    compiled = compile_result.payload
    from bpmn_io.profile._ui import compiled_identity

    identity = compiled_identity(compiled)  # type: ignore[arg-type]
    tree = {
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
    }
    envelope = complete_envelope(identity, copy.deepcopy(tree), [])
    base_geometry = {
        "layoutVersion": "1",
        "pages": [
            {
                "pageId": "page-main",
                "name": "main",
                "order": 0,
                "semanticRootId": "P_1",
                "bounds": {"x": 0, "y": 0, "width": 2000000, "height": 1000000},
            }
        ],
        "geometry": [
            {
                "pageId": "page-main",
                "occurrenceKey": "occ:Task_1",
                "semanticId": "Task_1",
                "role": "content",
                "bounds": {"x": 100000, "y": 200000, "width": 1000000, "height": 800000},
            },
            {
                "pageId": "page-main",
                "occurrenceKey": "occ:Task_2",
                "semanticId": "Task_2",
                "role": "content",
                "bounds": {"x": 1500000, "y": 200000, "width": 1000000, "height": 800000},
            },
        ],
    }
    return resolve_theme(
        compiled,
        envelope,
        base_geometry,
        "plain",
        {"semantic": [], "occurrence": []},
        {"native": [], "bioc": []},
    )


def test_r106_owner_label_without_owner_refuses_symbol() -> None:
    """A task label reading an unbound owner refuses profile-symbol."""
    out = _resolve_with_owner_label()
    assert getattr(out, "status", None) == "refused", getattr(out, "to_json", lambda: out)()
    assert getattr(out, "code", None) == "profile-symbol"
