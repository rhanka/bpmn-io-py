"""Block-B R1-10: inverse traversal admits descriptor references only.

A base-qualified ID scalar refers forward (DESIGN L119) but never counts
as a referrer for inverse traversal: only descriptor references do. The
synthetic ``x:Call`` declares ``targetRef`` as a scalar qualified by the
base, while the synthetic ``x:Flow`` declares it as a descriptor
reference.
"""

from __future__ import annotations

import copy
import json


def _packages() -> tuple[dict, dict, dict]:
    """Return the real package plus one synthetic descriptor package."""
    from bpmn_io.profile._c14n import digest_bytes
    from tests.profile_commands import harness as h

    x_doc = {
        "id": "x-blockb/1",
        "types": {
            "x:Call": {
                "id": True,
                "scalars": ["id", "targetRef"],
                "containment": {},
                "references": {},
            },
            "x:Flow": {
                "id": True,
                "scalars": ["id"],
                "containment": {},
                "references": {"targetRef": ["x:Call", "x:Flow"]},
            },
        },
    }
    x_raw = json.dumps(x_doc).encode("utf-8")
    x_pin = {"id": x_doc["id"], "version": "1.0.0", "sha256": digest_bytes(x_raw)}
    first = dict(h.DEFAULT_DESCRIPTOR_PIN)
    first_package = dict(first)
    first_package["descriptorBytes"] = h.DEFAULT_DESCRIPTOR_BYTES
    x_package = dict(x_pin)
    x_package["descriptorBytes"] = x_raw
    pins = [
        {
            "id": first["id"],
            "version": first["version"],
            "sha256": first["sha256"],
        },
        dict(x_pin),
    ]
    return first_package, x_package, pins


def _base_with_call_ref() -> bytes:
    """Return base bytes qualifying x:Call.targetRef as an ID scalar."""
    from tests.profile_commands import harness as h

    base = copy.deepcopy(h.BASE_DOCUMENT)
    base["fields"].append(
        {
            "type": "x:Call",
            "field": "targetRef",
            "kind": "reference",
            "producers": ["code", "editor", "import"],
        }
    )
    return json.dumps(base).encode("utf-8")


def _setup(entry_when: dict) -> tuple[object, object]:
    """Compile the neutral profile with the synthetic package and base."""
    from bpmn_io.profile import compile_profile, create_descriptor_context, load_profile
    from tests.profile_commands import harness as h

    first_package, x_package, pins = _packages()
    raw = (h.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
    profile = json.loads(raw.decode("utf-8"))
    for entry in profile.get("ui", []):
        if entry.get("id") == "task-create":
            entry["when"] = copy.deepcopy(entry_when)
    import hashlib

    base_bytes = _base_with_call_ref()
    profile["base"]["sha256"] = hashlib.sha256(base_bytes).hexdigest()
    profile["descriptors"] = pins
    load_result = load_profile(
        json.dumps(profile).encode("utf-8"),
        schema_bytes=h.SCHEMA_BYTES,
        base_bytes=base_bytes,
        descriptor_pins=copy.deepcopy(pins),
        asset_bag=dict(h.METRICS_BAG),
    )
    assert load_result.status == "ok", load_result.to_json()
    context_result = create_descriptor_context([first_package, x_package])
    assert context_result.status == "ok", context_result.to_json()
    compile_result = compile_profile(
        load_result.payload,  # type: ignore[arg-type]
        descriptor_context=context_result.payload,  # type: ignore[arg-type]
        base=json.loads(base_bytes.decode("utf-8")),
    )
    assert compile_result.status == "ok", compile_result.to_json()
    return context_result.payload, compile_result.payload  # type: ignore[return-value]


def _tree() -> dict:
    return {
        "$type": "bpmn:Definitions",
        "id": "D_1",
        "targetNamespace": "urn:x",
        "rootElements": [
            {
                "$type": "bpmn:Process",
                "id": "P_1",
                "flowElements": [
                    {"$type": "x:Call", "id": "c", "targetRef": "b"},
                    {"$type": "x:Flow", "id": "f", "targetRef": "b"},
                    {"$type": "x:Call", "id": "b"},
                ],
            },
        ],
    }


def _session(context: object, compiled: object) -> object:
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


def _when(via: str, min_count: int) -> dict:
    return {
        "op": "count",
        "select": {
            "from": "self",
            "via": via,
            "property": "targetRef",
            "where": {"op": "true"},
            "order": "id",
        },
        "min": min_count,
    }


def _entry_ids(out: object) -> list:
    return [record["id"] for group in out.payload["groups"] for record in group["entries"]]  # type: ignore[union-attr]


def test_r110_inverse_skips_qualified_scalar_referrer() -> None:
    """Inverse listing counts only the descriptor-reference referrer."""
    context, compiled = _setup(_when("inverseReference", 2))
    session = _session(context, compiled)
    revision = session.envelope.semantic_revision  # type: ignore[union-attr]
    out = session.list_entries(  # type: ignore[union-attr]
        base_revision=revision, surface="palette", subject="b", locale="en"
    )
    assert out.status == "ok"
    assert "task-create" not in _entry_ids(out)


def test_r110_forward_admits_qualified_scalar() -> None:
    """Forward listing through the qualified scalar still resolves."""
    context, compiled = _setup(_when("reference", 1))
    session = _session(context, compiled)
    revision = session.envelope.semantic_revision  # type: ignore[union-attr]
    out = session.list_entries(  # type: ignore[union-attr]
        base_revision=revision, surface="palette", subject="c", locale="en"
    )
    assert out.status == "ok"
    assert "task-create" in _entry_ids(out)
