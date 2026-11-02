"""Block-B R2-02: occurrence traversal activates metadata-free (regression guard).

Public operations only: ``load_profile`` + ``compile_profile`` without
context/base, ``create_descriptor_context``, ``create_bridge``,
``complete_envelope``, ``set_definitions``, ``activate_business_profile``.
Envelope identity equals the compiled identity; tree ``D_1/P_1/Task_1``.
"""

from __future__ import annotations

import copy
import json


def _neutral_profile() -> dict:
    """Load the neutral lot-5 profile document."""
    from tests.profile_commands import harness as h

    raw = (h.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
    return json.loads(raw.decode("utf-8"))


def _tree() -> dict:
    """Return one envelope tree with a single named task."""
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


def test_r202_occurrence_traversal_activates_metadata_free() -> None:
    """An occurrence-typed reference activates after metadata-free compile."""
    from bpmn_io.profile import (
        compile_profile,
        complete_envelope,
        create_bridge,
        create_descriptor_context,
        load_profile,
    )
    from tests.profile_commands import harness as h

    profile = _neutral_profile()
    recipe = next(r for r in profile.get("recipes", []) if r.get("id") == "export-nodes")
    recipe["when"] = {
        "op": "count",
        "select": {
            "from": "self",
            "via": "reference",
            "property": "sourceOccurrence",
            "where": {"op": "true"},
            "order": "page-occurrence",
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
    session = create_bridge(context_result.payload)  # type: ignore[arg-type]
    envelope = complete_envelope(
        compile_result.payload.identity,  # type: ignore[union-attr]
        copy.deepcopy(_tree()),
        [],
    )
    loaded = session.set_definitions(envelope)
    assert getattr(loaded, "status", None) == "ok", getattr(loaded, "to_json", lambda: loaded)()
    activated = session.activate_business_profile(compile_result.payload)  # type: ignore[arg-type]
    assert getattr(activated, "status", None) == "ok", getattr(
        activated, "to_json", lambda: activated
    )()
