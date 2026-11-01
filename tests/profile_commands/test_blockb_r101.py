"""Block-B R1-01: activation requires exact descriptor order."""

from __future__ import annotations

import copy
import json


def _setup_two_packages() -> tuple[object, object]:
    from bpmn_io.profile import create_descriptor_context, load_profile
    from bpmn_io.profile._c14n import digest_bytes
    from tests.profile_commands import harness as h

    raw = (h.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
    profile = json.loads(raw.decode("utf-8"))
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
    packages = [first_package, second_package]
    profile["descriptors"] = [
        {
            "id": first["id"],
            "version": first["version"],
            "sha256": first["sha256"],
        },
        dict(extra_pin),
    ]
    context_result = create_descriptor_context(packages)
    assert context_result.status == "ok", context_result.to_json()
    load_result = load_profile(
        json.dumps(profile).encode("utf-8"),
        schema_bytes=h.SCHEMA_BYTES,
        base_bytes=h.BASE_BYTES,
        descriptor_pins=copy.deepcopy(profile["descriptors"]),
        asset_bag=dict(h.METRICS_BAG),
    )
    assert load_result.status == "ok", load_result.to_json()
    return context_result.payload, load_result.payload


def test_r101_reordered_envelope_descriptors_refuse() -> None:
    """Reversing the envelope descriptor pins refuses descriptor-mismatch."""
    from bpmn_io.profile import (
        compile_profile,
        complete_envelope,
        create_bridge,
    )
    from bpmn_io.profile._ui import compiled_identity
    from tests.profile_commands import harness as h

    context, validated = _setup_two_packages()
    compile_result = compile_profile(
        validated,
        descriptor_context=context,  # type: ignore[arg-type]
        base=copy.deepcopy(h.BASE_DOCUMENT),
    )
    assert compile_result.status == "ok", compile_result.to_json()
    compiled = compile_result.payload
    identity = compiled_identity(compiled)
    reordered = copy.deepcopy(identity)
    descriptors = reordered.get("descriptors")
    assert isinstance(descriptors, list)
    assert len(descriptors) == 2
    reordered["descriptors"] = [descriptors[1], descriptors[0]]
    tree = {
        "$type": "bpmn:Definitions",
        "id": "D_1",
        "targetNamespace": "urn:x",
        "rootElements": [
            {"$type": "bpmn:Process", "id": "P_1", "flowElements": []},
        ],
    }
    bridge = create_bridge(context)  # type: ignore[arg-type]
    loaded = bridge.set_definitions(complete_envelope(reordered, copy.deepcopy(tree), []))
    assert getattr(loaded, "status", None) == "ok", getattr(loaded, "to_json", lambda: loaded)()
    out = bridge.activate_business_profile(compiled)  # type: ignore[arg-type]
    assert getattr(out, "status", None) == "refused"
    assert getattr(out, "code", None) == "descriptor-mismatch"
