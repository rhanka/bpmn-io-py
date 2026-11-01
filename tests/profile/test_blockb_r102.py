"""Block-B R1-02: reference traversal decides per handle type.

Rewritten through the public compile/activate/list surface (neutral profile
plus one synthetic descriptor package), so the reds below are behavioural
refusal codes rather than API-signature failures: the synthetic ``x:Task``
declares ``targetRef`` as a scalar while the synthetic ``x:Flow`` (and the
real ``bpmn:SequenceFlow``) declares it as a reference.
"""

from __future__ import annotations

import copy
import json


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


def _setup(entry_when: dict) -> tuple[object, object]:
    """Compile the neutral profile with the synthetic package (context ok)."""
    from bpmn_io.profile import compile_profile, create_descriptor_context, load_profile
    from tests.profile_commands import harness as h

    raw = (h.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
    profile = json.loads(raw.decode("utf-8"))
    for entry in profile.get("ui", []):
        if entry.get("id") == "task-create":
            entry["when"] = copy.deepcopy(entry_when)
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
    context_result = create_descriptor_context([first_package, x_package])
    assert context_result.status == "ok", context_result.to_json()
    load_result = load_profile(
        json.dumps(profile).encode("utf-8"),
        schema_bytes=h.SCHEMA_BYTES,
        base_bytes=h.BASE_BYTES,
        descriptor_pins=copy.deepcopy(profile["descriptors"]),
        asset_bag=dict(h.METRICS_BAG),
    )
    assert load_result.status == "ok", load_result.to_json()
    compile_result = compile_profile(
        load_result.payload,  # type: ignore[arg-type]
        descriptor_context=context_result.payload,  # type: ignore[arg-type]
        base=copy.deepcopy(h.BASE_DOCUMENT),
    )
    assert compile_result.status == "ok", compile_result.to_json()
    return context_result.payload, compile_result.payload  # type: ignore[return-value]


def _tree() -> dict:
    """Return one envelope tree with scalar and reference referrers."""
    return {
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
                    {"$type": "x:Flow", "id": "f", "targetRef": "b"},
                ],
            },
        ],
    }


def _session(context: object, compiled: object) -> object:
    """Return one loaded bridge with an active business profile."""
    from bpmn_io.profile import complete_envelope, create_bridge
    from bpmn_io.profile._ui import compiled_identity

    session = create_bridge(context)  # type: ignore[arg-type]
    loaded = session.set_definitions(
        complete_envelope(compiled_identity(compiled), _tree(), [])  # type: ignore[arg-type]
    )
    assert getattr(loaded, "status", None) == "ok", getattr(loaded, "to_json", lambda: loaded)()
    activated = session.activate_business_profile(compiled)  # type: ignore[arg-type]
    assert getattr(activated, "status", None) == "ok", getattr(
        activated, "to_json", lambda: activated
    )()
    return session


def _forward_when(min_count: int) -> dict:
    return {
        "op": "count",
        "select": {
            "from": "self",
            "via": "reference",
            "property": "targetRef",
            "where": {"op": "true"},
            "order": "id",
        },
        "min": min_count,
    }


def test_r102_forward_scalar_handle_refuses() -> None:
    """Listing on a scalar-declaring subject refuses selector-property."""
    context, compiled = _setup(_forward_when(0))
    session = _session(context, compiled)
    revision = session.envelope.semantic_revision  # type: ignore[union-attr]
    out = session.list_entries(  # type: ignore[union-attr]
        base_revision=revision, surface="palette", subject="a", locale="en"
    )
    assert out.status == "refused"
    assert out.code == "profile-selector-property"


def test_r102_forward_reference_handle_resolves() -> None:
    """Listing on a reference-declaring subject still lists the entry."""
    context, compiled = _setup(_forward_when(1))
    session = _session(context, compiled)
    revision = session.envelope.semantic_revision  # type: ignore[union-attr]
    out = session.list_entries(  # type: ignore[union-attr]
        base_revision=revision, surface="palette", subject="f", locale="en"
    )
    assert out.status == "ok"
    assert "task-create" in [
        record["id"] for group in out.payload["groups"] for record in group["entries"]
    ]


def test_r102_inverse_skips_scalar_referrer() -> None:
    """Inverse listing counts only the descriptor-reference referrer."""
    context, compiled = _setup(
        {
            "op": "count",
            "select": {
                "from": "self",
                "via": "inverseReference",
                "property": "targetRef",
                "where": {"op": "true"},
                "order": "id",
            },
            "min": 2,
        }
    )
    session = _session(context, compiled)
    revision = session.envelope.semantic_revision  # type: ignore[union-attr]
    out = session.list_entries(  # type: ignore[union-attr]
        base_revision=revision, surface="palette", subject="b", locale="en"
    )
    assert out.status == "ok"
    assert "task-create" not in [
        record["id"] for group in out.payload["groups"] for record in group["entries"]
    ]
