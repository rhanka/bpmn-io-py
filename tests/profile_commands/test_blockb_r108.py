"""Block-B R1-08: metadata-free profiles meet the G6 gate at activation.

Compiling without descriptor metadata fails open, but activation against a
bridge that knows the descriptor types applies the full G6 qualification
(scalar, unknown and occurrence-name-on-native properties refuse with
`profile-selector-property`), and runtime contexts receive the bridge index
so per-handle qualification keeps working after activation.
"""

from __future__ import annotations

import copy
import json


def _metadata_free_compile(prop: str, via: str = "reference") -> tuple[object, object]:
    """Compile the neutral profile with no descriptor metadata and no base."""
    from bpmn_io.profile import compile_profile, create_descriptor_context, load_profile
    from tests.profile_commands import harness as h

    raw = (h.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
    profile = json.loads(raw.decode("utf-8"))
    for entry in profile.get("ui", []):
        if entry.get("id") == "task-create":
            entry["when"] = {
                "op": "count",
                "select": {
                    "from": "self",
                    "via": via,
                    "property": prop,
                    "where": {"op": "true"},
                    "order": "id",
                },
                "min": 0,
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
    compile_result = compile_profile(load_result.payload)  # type: ignore[arg-type]
    assert compile_result.status == "ok", compile_result.to_json()
    context_result = create_descriptor_context([package])
    assert context_result.status == "ok", context_result.to_json()
    return context_result.payload, compile_result.payload  # type: ignore[return-value]


def _activate(context: object, compiled: object, tree: dict) -> tuple[object, object]:
    """Load one envelope tree and activate the compiled profile."""
    from bpmn_io.profile import complete_envelope, create_bridge
    from bpmn_io.profile._ui import compiled_identity

    session = create_bridge(context)  # type: ignore[arg-type]
    loaded = session.set_definitions(
        complete_envelope(compiled_identity(compiled), tree, [])  # type: ignore[arg-type]
    )
    assert getattr(loaded, "status", None) == "ok", getattr(loaded, "to_json", lambda: loaded)()
    return session, session.activate_business_profile(compiled)  # type: ignore[arg-type]


def _neutral_tree() -> dict:
    return {
        "$type": "bpmn:Definitions",
        "id": "D_1",
        "targetNamespace": "urn:x",
        "rootElements": [
            {
                "$type": "bpmn:Process",
                "id": "P_1",
                "flowElements": [
                    {"$type": "bpmn:Task", "id": "Task_1", "name": "Fixed"},
                ],
            },
        ],
    }


def test_r108_scalar_property_refuses_activation() -> None:
    """A scalar traversal compiled metadata-free refuses at activation."""
    context, compiled = _metadata_free_compile("name")
    _, out = _activate(context, compiled, _neutral_tree())
    assert getattr(out, "status", None) == "refused"
    assert getattr(out, "code", None) == "profile-selector-property"


def test_r108_native_occurrence_name_refuses_activation() -> None:
    """A native occurrence-endpoint traversal refuses at activation."""
    context, compiled = _metadata_free_compile("sourceOccurrence")
    _, out = _activate(context, compiled, _neutral_tree())
    assert getattr(out, "status", None) == "refused"
    assert getattr(out, "code", None) == "profile-selector-property"


def _x_package() -> tuple[dict, dict]:
    """Return one synthetic descriptor document and its pin (neutral data)."""
    from bpmn_io.profile._c14n import digest_bytes

    doc = {
        "id": "x-blockb/1",
        "types": {
            "x:Task": {
                "id": True,
                "scalars": ["id", "targetRef"],
                "containment": {},
                "references": {},
            },
            "x:Flow": {
                "id": True,
                "scalars": ["id"],
                "containment": {},
                "references": {"targetRef": ["x:Task"]},
            },
        },
    }
    raw = json.dumps(doc).encode("utf-8")
    return doc, {"id": doc["id"], "version": "1.0.0", "sha256": digest_bytes(raw)}


def test_r108_runtime_contexts_receive_bridge_index() -> None:
    """An admitted traversal still refuses per handle once activated."""
    from bpmn_io.profile import compile_profile, load_profile
    from tests.profile_commands import harness as h

    raw = (h.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
    profile = json.loads(raw.decode("utf-8"))
    for entry in profile.get("ui", []):
        if entry.get("id") == "task-create":
            entry["when"] = {
                "op": "count",
                "select": {
                    "from": "self",
                    "via": "reference",
                    "property": "targetRef",
                    "where": {"op": "true"},
                    "order": "id",
                },
                "min": 0,
            }
    x_doc, x_pin = _x_package()
    first = dict(h.DEFAULT_DESCRIPTOR_PIN)
    first_package = dict(first)
    first_package["descriptorBytes"] = h.DEFAULT_DESCRIPTOR_BYTES
    x_package = dict(x_pin)
    x_package["descriptorBytes"] = json.dumps(x_doc).encode("utf-8")
    profile["descriptors"] = [
        {
            "id": first["id"],
            "version": first["version"],
            "sha256": first["sha256"],
        },
        dict(x_pin),
    ]
    load_result = load_profile(
        json.dumps(profile).encode("utf-8"),
        schema_bytes=h.SCHEMA_BYTES,
        base_bytes=h.BASE_BYTES,
        descriptor_pins=copy.deepcopy(profile["descriptors"]),
        asset_bag=dict(h.METRICS_BAG),
    )
    assert load_result.status == "ok", load_result.to_json()
    # Metadata-free compile: no descriptor context and no base.
    compile_result = compile_profile(load_result.payload)  # type: ignore[arg-type]
    assert compile_result.status == "ok", compile_result.to_json()
    from bpmn_io.profile import create_descriptor_context

    context_result = create_descriptor_context([first_package, x_package])
    assert context_result.status == "ok", context_result.to_json()
    tree = {
        "$type": "bpmn:Definitions",
        "id": "D_1",
        "targetNamespace": "urn:x",
        "rootElements": [
            {
                "$type": "bpmn:Process",
                "id": "P_1",
                "flowElements": [
                    {"$type": "x:Task", "id": "a", "targetRef": "b"},
                    {"$type": "x:Task", "id": "b"},
                ],
            },
        ],
    }
    session, out = _activate(
        context_result.payload,
        compile_result.payload,
        tree,  # type: ignore[arg-type]
    )
    # targetRef is a descriptor reference elsewhere, so activation admits
    # the profile; the bridge index must then reach the runtime contexts.
    assert getattr(out, "status", None) == "ok", getattr(out, "to_json", lambda: out)()
    revision = session.envelope.semantic_revision  # type: ignore[union-attr]
    listed = session.list_entries(  # type: ignore[union-attr]
        base_revision=revision, surface="palette", subject="a", locale="en"
    )
    assert listed.status == "refused"
    assert listed.code == "profile-selector-property"
