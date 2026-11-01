"""Block-B R2-03: every refusal at a recognition site is a non-match.

Public operations ``layout``, ``resolve_theme`` and ``compute_layout`` with
a task recognition extended by an owner-dependent refusal (no owner bound):
JS returns ``ok`` with exactly two ``render-unsupported`` diagnostics.
"""

from __future__ import annotations

import copy
import json


def _neutral_profile(extra: dict) -> dict:
    """Load neutral lot-5 with one task-recognition extension."""
    from tests.profile_commands import harness as h

    raw = (h.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
    profile = json.loads(raw.decode("utf-8"))
    task = next(n for n in profile.get("notions", []) if n.get("id") == "task")
    original = copy.deepcopy(task.get("recognition"))
    task["recognition"] = {"op": "all", "args": [original, copy.deepcopy(extra)]}
    return profile


def _compile(profile: dict) -> object:
    """Compile one profile with metadata (real descriptors and base)."""
    from bpmn_io.profile import compile_profile, create_descriptor_context, load_profile
    from tests.profile_commands import harness as h

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
    return compile_result.payload  # type: ignore[return-value]


def _tree() -> dict:
    """Return one envelope tree with an unnamed and a named task."""
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
    }


def _base_geometry() -> dict:
    """Return the p18 base geometry (one page, two content records)."""
    return {
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


def _di_tree() -> dict:
    """Return the DI tree matching the base geometry."""
    tree = _tree()
    tree["diagrams"] = [
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
    ]
    return tree


def _check(extra: dict) -> None:
    """Run layout, resolve_theme and compute_layout for one extension."""
    from bpmn_io.profile import complete_envelope
    from bpmn_io.profile._envelope import make_imported_di
    from bpmn_io.profile._layout import compute_layout, layout
    from bpmn_io.profile._render import resolve_theme
    from bpmn_io.profile._render_digest import descriptor_digest
    from bpmn_io.profile._ui import compiled_identity

    compiled = _compile(_neutral_profile(extra))
    identity = compiled_identity(compiled)  # type: ignore[arg-type]
    envelope = complete_envelope(identity, copy.deepcopy(_tree()), [])
    staged = layout(compiled, envelope, [], copy.deepcopy(_base_geometry()), theme_id="plain")
    assert getattr(staged, "status", None) == "ok", getattr(staged, "to_json", lambda: staged)()
    resolved = resolve_theme(
        compiled,
        envelope,
        staged.payload,  # type: ignore[union-attr]
        "plain",
        {"semantic": [], "occurrence": []},
        {"native": [], "bioc": []},
    )
    assert getattr(resolved, "status", None) == "ok", getattr(
        resolved, "to_json", lambda: resolved
    )()
    payload = resolved.payload  # type: ignore[union-attr]
    unsupported = [
        entry
        for entry in payload.get("diagnostics", [])
        if entry.get("code") == "render-unsupported"
    ]
    targets = sorted(
        (entry.get("source") or {}).get("targetId") or entry.get("targetId")
        for entry in unsupported
    )
    assert targets == ["Task_1", "Task_2"], payload.get("diagnostics")
    di_tree = _di_tree()
    envelope_di = complete_envelope(identity, copy.deepcopy(di_tree), [])
    imported = make_imported_di(di_tree, descriptor_digest(identity.get("descriptors")))  # type: ignore[arg-type]
    out = compute_layout(compiled, envelope_di, [], imported, theme_id="plain")
    assert getattr(out, "status", None) == "ok", getattr(out, "to_json", lambda: out)()


def test_r203_owner_id_refusal_is_non_match() -> None:
    """An owner-dependent recognition refusal is a non-match at every site."""
    _check(
        {
            "op": "equal",
            "left": {"op": "id", "binding": "bindingOwner"},
            "right": {"op": "id", "binding": "self"},
        }
    )


def test_r203_recognizes_unbound_owner_is_non_match() -> None:
    """A recognizes refusal on an unbound owner is a non-match at every site."""
    _check({"op": "recognizes", "binding": "bindingOwner", "notion": "aid"})
