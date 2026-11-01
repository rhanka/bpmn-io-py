"""Block-B R1-03: unknown reference refuses once descriptors are known."""

from __future__ import annotations

import copy
import json


def test_r103_missing_metadata_bypass_refuses_on_activation() -> None:
    """Compiling without metadata then activating with real types refuses."""
    from bpmn_io.profile import (
        compile_profile,
        complete_envelope,
        create_bridge,
        create_descriptor_context,
        load_profile,
    )
    from tests.profile_commands import harness as h

    raw = (h.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
    profile = json.loads(raw.decode("utf-8"))
    profile["ui"][0]["when"] = {
        "op": "count",
        "select": {
            "from": "self",
            "via": "reference",
            "property": "nope",
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
    compiled_result = compile_profile(load_result.payload)  # type: ignore[arg-type]
    assert compiled_result.status == "ok", compiled_result.to_json()
    context_result = create_descriptor_context([package])
    assert context_result.status == "ok", context_result.to_json()
    bridge = create_bridge(context_result.payload)  # type: ignore[arg-type]
    tree = {
        "$type": "bpmn:Definitions",
        "id": "D_1",
        "targetNamespace": "urn:x",
        "rootElements": [
            {"$type": "bpmn:Process", "id": "P_1", "flowElements": []},
        ],
    }
    from bpmn_io.profile._ui import compiled_identity

    identity = compiled_identity(compiled_result.payload)  # type: ignore[arg-type]
    loaded = bridge.set_definitions(complete_envelope(identity, copy.deepcopy(tree), []))
    assert getattr(loaded, "status", None) == "ok"
    out = bridge.activate_business_profile(compiled_result.payload)  # type: ignore[arg-type]
    assert getattr(out, "status", None) == "refused"
    assert getattr(out, "code", None) == "profile-selector-property"
