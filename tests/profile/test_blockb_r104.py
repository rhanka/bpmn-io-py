"""Block-B R1-04: occurrence names refuse on native handles.

Rewritten through the public compile/activate surface (neutral profile with
the real descriptor context), so the reds below are behavioural refusal
codes rather than API-signature failures.
"""

from __future__ import annotations

import copy
import json


def _compile_with_selector(prop: str, via: str = "reference") -> object:
    """Compile the neutral profile with one entry selector (metadata on)."""
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
    context_result = create_descriptor_context([package])
    assert context_result.status == "ok", context_result.to_json()
    return compile_profile(
        load_result.payload,  # type: ignore[arg-type]
        descriptor_context=context_result.payload,  # type: ignore[arg-type]
        base=copy.deepcopy(h.BASE_DOCUMENT),
    )


def test_r104_native_occurrence_name_refuses_compilation() -> None:
    """A native reference to an occurrence endpoint refuses compilation."""
    outcome = _compile_with_selector("sourceOccurrence")
    assert outcome.status == "refused"
    assert outcome.code == "profile-selector-property"  # type: ignore[union-attr]


def test_r104_occurrence_binding_endpoint_compiles() -> None:
    """An occurrence-typed reference to an endpoint compiles (JS-valid)."""
    from bpmn_io.profile import compile_profile, create_descriptor_context, load_profile
    from tests.profile_commands import harness as h

    raw = (h.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
    profile = json.loads(raw.decode("utf-8"))
    for recipe in profile.get("recipes", []):
        if recipe.get("id") == "export-nodes":
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
    context_result = create_descriptor_context([package])
    assert context_result.status == "ok", context_result.to_json()
    outcome = compile_profile(
        load_result.payload,  # type: ignore[arg-type]
        descriptor_context=context_result.payload,  # type: ignore[arg-type]
        base=copy.deepcopy(h.BASE_DOCUMENT),
    )
    assert outcome.status == "ok", outcome.to_json()
