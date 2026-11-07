"""Block-B mirror G6: reference traversal refuses scalar/unknown properties.

Rewritten through the public compile surface (load/compile with the real
descriptor context), which exists at the base revision, so the reds are
behavioural (refusal codes) rather than API-signature failures.
"""

from __future__ import annotations

import copy
import json


def _compile_with_selector(prop: str, via: str = "reference") -> object:
    from bpmn_io.profile import compile_profile, create_descriptor_context, load_profile
    from tests.profile_commands import harness as h

    raw = (h.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
    profile = json.loads(raw.decode("utf-8"))
    profile["ui"][0]["when"] = {
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


def test_g6_reference_scalar_property_refuses() -> None:
    """A scalar property refuses profile-selector-property, not an empty selection."""
    outcome = _compile_with_selector("name")
    assert outcome.status == "refused"
    assert outcome.code == "profile-selector-property"  # type: ignore[union-attr]


def test_g6_reference_unknown_property_refuses() -> None:
    """An unknown property refuses profile-selector-property."""
    outcome = _compile_with_selector("nope")
    assert outcome.status == "refused"
    assert outcome.code == "profile-selector-property"  # type: ignore[union-attr]


def test_g6_inverse_scalar_refuses() -> None:
    """Inverse traversal refuses a scalar property."""
    outcome = _compile_with_selector("name", via="inverseReference")
    assert outcome.status == "refused"
    assert outcome.code == "profile-selector-property"  # type: ignore[union-attr]


def test_g6_inverse_unknown_refuses() -> None:
    """Inverse traversal refuses an unknown property."""
    outcome = _compile_with_selector("nope", via="inverseReference")
    assert outcome.status == "refused"
    assert outcome.code == "profile-selector-property"  # type: ignore[union-attr]


def test_g6_declared_references_resolve() -> None:
    """Declared references still compile."""
    from bpmn_io.profile import compile_profile, create_descriptor_context, load_profile
    from tests.profile_commands import harness as h

    raw = (h.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
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
        raw,
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


def test_g6_heterogeneous_reference_admitted() -> None:
    """A reference declared elsewhere compiles (per-handle skip at runtime)."""
    outcome = _compile_with_selector("sourceRef")
    assert outcome.status == "ok", outcome.to_json()
