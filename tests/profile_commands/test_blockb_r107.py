"""Block-B R1-07: descriptor order wins over version and digest rows.

The JS activation gate compares descriptor pins before the digest and
version rows, so a reversed descriptor list refuses `descriptor-mismatch`
even when a version bump or a profile digest change is also present.
"""

from __future__ import annotations

import copy
import json


def _compile_two_packages(version: str) -> tuple[object, object]:
    """Compile the two-package profile at one business version."""
    from bpmn_io.profile import compile_profile, create_descriptor_context, load_profile
    from bpmn_io.profile._c14n import digest_bytes
    from tests.profile_commands import harness as h

    raw = (h.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
    profile = json.loads(raw.decode("utf-8"))
    profile["version"] = version
    extra_doc = {
        "id": "extra/1",
        "version": "1.0.0",
        "types": {
            "x:Extra": {
                "id": True,
                "scalars": ["id"],
                "containment": {},
                "references": {},
            }
        },
    }
    extra_bytes = json.dumps(extra_doc).encode("utf-8")
    extra_pin = {
        "id": "extra/1",
        "version": "1.0.0",
        "sha256": digest_bytes(extra_bytes),
    }
    first = dict(h.DEFAULT_DESCRIPTOR_PIN)
    first_package = dict(first)
    first_package["descriptorBytes"] = h.DEFAULT_DESCRIPTOR_BYTES
    second_package = dict(extra_pin)
    second_package["descriptorBytes"] = extra_bytes
    profile["descriptors"] = [
        {
            "id": first["id"],
            "version": first["version"],
            "sha256": first["sha256"],
        },
        dict(extra_pin),
    ]
    context_result = create_descriptor_context([first_package, second_package])
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


def _activate_mixed(context: object, compiled: object, mutate: object) -> object:
    """Load one mixed envelope identity and activate the compiled profile."""
    from bpmn_io.profile import complete_envelope, create_bridge
    from bpmn_io.profile._ui import compiled_identity

    identity = compiled_identity(compiled)  # type: ignore[arg-type]
    assert identity.get("version") == "1.6.0"
    descriptors = identity.get("descriptors")
    assert isinstance(descriptors, list)
    assert len(descriptors) == 2
    mixed = copy.deepcopy(identity)
    mixed["descriptors"] = [descriptors[1], descriptors[0]]
    mutate(mixed)  # type: ignore[operator]
    tree = {
        "$type": "bpmn:Definitions",
        "id": "D_1",
        "targetNamespace": "urn:x",
        "rootElements": [
            {"$type": "bpmn:Process", "id": "P_1", "flowElements": []},
        ],
    }
    bridge = create_bridge(context)  # type: ignore[arg-type]
    loaded = bridge.set_definitions(complete_envelope(mixed, copy.deepcopy(tree), []))
    assert getattr(loaded, "status", None) == "ok", getattr(loaded, "to_json", lambda: loaded)()
    return bridge.activate_business_profile(compiled)  # type: ignore[arg-type]


def test_r107_reversed_plus_patch_refuses_descriptor_mismatch() -> None:
    """Reversed pins with a patch bump refuse descriptor-mismatch first."""
    context, compiled = _compile_two_packages("1.6.0")
    out = _activate_mixed(context, compiled, lambda mixed: mixed.update({"version": "1.6.1"}))
    assert getattr(out, "status", None) == "refused"
    assert getattr(out, "code", None) == "descriptor-mismatch"


def test_r107_reversed_plus_digest_refuses_descriptor_mismatch() -> None:
    """Reversed pins with a changed digest refuse descriptor-mismatch first."""
    context, compiled = _compile_two_packages("1.6.0")
    out = _activate_mixed(context, compiled, lambda mixed: mixed.update({"sha256": "0" * 64}))
    assert getattr(out, "status", None) == "refused"
    assert getattr(out, "code", None) == "descriptor-mismatch"
