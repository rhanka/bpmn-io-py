"""Block-B mirror G6c on the public compile surface (R2-06).

Compile the neutral lot-5 profile with one ``ui[task-create].when``
traversal; scalar and unknown properties refuse
``profile-selector-property``, declared references admit.
"""

from __future__ import annotations

import copy
import json


def _compile_with_when(when: dict) -> object:
    """Compile neutral lot-5 with one UI entry predicate."""
    from bpmn_io.profile import compile_profile, create_descriptor_context, load_profile
    from tests.profile_commands import harness as h

    raw = (h.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
    profile = json.loads(raw.decode("utf-8"))
    entry = next(e for e in profile.get("ui", []) if e.get("id") == "task-create")
    entry["when"] = copy.deepcopy(when)
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


def _when(via: str, prop: str) -> dict:
    """Build one count predicate over a reference-family selector."""
    return {
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


def test_g6c_reference_scalar_property_refuses() -> None:
    """A scalar reference traversal refuses profile-selector-property."""
    out = _compile_with_when(_when("reference", "name"))
    assert getattr(out, "status", None) == "refused", getattr(out, "to_json", lambda: out)()
    assert getattr(out, "code", None) == "profile-selector-property"


def test_g6c_reference_unknown_property_refuses() -> None:
    """An unknown reference traversal refuses profile-selector-property."""
    out = _compile_with_when(_when("reference", "nope"))
    assert getattr(out, "status", None) == "refused", getattr(out, "to_json", lambda: out)()
    assert getattr(out, "code", None) == "profile-selector-property"


def test_g6c_inverse_scalar_property_refuses() -> None:
    """An inverse scalar traversal refuses profile-selector-property."""
    out = _compile_with_when(_when("inverseReference", "name"))
    assert getattr(out, "status", None) == "refused", getattr(out, "to_json", lambda: out)()
    assert getattr(out, "code", None) == "profile-selector-property"


def test_g6c_inverse_unknown_property_refuses() -> None:
    """An inverse unknown traversal refuses profile-selector-property."""
    out = _compile_with_when(_when("inverseReference", "nope"))
    assert getattr(out, "status", None) == "refused", getattr(out, "to_json", lambda: out)()
    assert getattr(out, "code", None) == "profile-selector-property"


def test_g6c_reference_declared_property_admitted() -> None:
    """A declared reference traversal compiles ok (control)."""
    out = _compile_with_when(_when("reference", "targetRef"))
    assert getattr(out, "status", None) == "ok", getattr(out, "to_json", lambda: out)()


def test_g6c_inverse_declared_property_admitted() -> None:
    """A declared inverse traversal compiles ok (control)."""
    out = _compile_with_when(_when("inverseReference", "targetRef"))
    assert getattr(out, "status", None) == "ok", getattr(out, "to_json", lambda: out)()
