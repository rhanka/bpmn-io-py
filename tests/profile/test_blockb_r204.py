"""Block-B R2-04: capability scope and occurrence-traversal typing.

Public ``load_profile`` + ``compile_profile`` with context and base on the
neutral lot-5 profile (``compiler-static.ts:54, :372, :151-195``).
"""

from __future__ import annotations

import copy
import json


def _neutral_profile() -> dict:
    """Load the neutral lot-5 profile document."""
    from tests.profile_commands import harness as h

    raw = (h.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
    return json.loads(raw.decode("utf-8"))


def _compile(profile: dict) -> object:
    """Compile one profile with metadata (real descriptors and base)."""
    from bpmn_io.profile import compile_profile, create_descriptor_context, load_profile
    from tests.profile_commands import harness as h

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


def _capability_profile(when: dict) -> dict:
    """Return neutral lot-5 with every capability ``when`` replaced."""
    profile = _neutral_profile()
    for export in profile.get("exports", []):
        for capability in export.get("capabilities", []):
            capability["when"] = copy.deepcopy(when)
    return profile


def _recipe_profile(recipe_id: str, when: dict) -> dict:
    """Return neutral lot-5 with one recipe ``when`` replaced."""
    profile = _neutral_profile()
    recipe = next(r for r in profile.get("recipes", []) if r.get("id") == recipe_id)
    recipe["when"] = copy.deepcopy(when)
    return profile


def _select(frm: str, via: str, prop: str | None = None, order: str = "id") -> dict:
    """Build one count predicate over a selector."""
    select: dict[str, object] = {"from": frm, "via": via, "where": {"op": "true"}, "order": order}
    if prop is not None:
        select["property"] = prop
    return {"op": "count", "min": 0, "select": select}


def test_r204_capability_page_reference_refuses_symbol() -> None:
    """A capability reading a page occurrence refuses profile-symbol."""
    when = _select("page", "reference", "sourceOccurrence", "id")
    out = _compile(_capability_profile(when))
    assert getattr(out, "status", None) == "refused", getattr(out, "to_json", lambda: out)()
    assert getattr(out, "code", None) == "profile-symbol"


def test_r204_capability_binding_owner_admitted() -> None:
    """A capability reading the owner id compiles ok."""
    when = {"op": "present", "value": {"op": "id", "binding": "bindingOwner"}}
    out = _compile(_capability_profile(when))
    assert getattr(out, "status", None) == "ok", getattr(out, "to_json", lambda: out)()


def test_r204_capability_occurrences_refuses_type() -> None:
    """A capability traversing occurrences refuses profile-type."""
    when = _select("self", "occurrences", None, "page-occurrence")
    out = _compile(_capability_profile(when))
    assert getattr(out, "status", None) == "refused", getattr(out, "to_json", lambda: out)()
    assert getattr(out, "code", None) == "profile-type"


def test_r204_capability_semantic_control_ok() -> None:
    """A capability reading semantic from a native binding compiles ok."""
    when = _select("self", "semantic", None, "id")
    select = when["select"]
    assert isinstance(select, dict)
    select["where"] = {"op": "typeIs", "binding": "self", "type": "bpmn:Task", "mode": "exact"}
    out = _compile(_capability_profile(when))
    assert getattr(out, "status", None) == "ok", getattr(out, "to_json", lambda: out)()


def test_r204_export_nodes_occurrence_order_refuses() -> None:
    """An occurrence reference with order id refuses selector-order."""
    when = _select("self", "reference", "sourceOccurrence", "id")
    out = _compile(_recipe_profile("export-nodes", when))
    assert getattr(out, "status", None) == "refused", getattr(out, "to_json", lambda: out)()
    assert getattr(out, "code", None) == "profile-selector-order"


def test_r204_export_pages_reference_refuses_property() -> None:
    """A page-typed reference refuses selector-property (order id)."""
    when = _select("self", "reference", "sourceOccurrence", "id")
    out = _compile(_recipe_profile("export-pages", when))
    assert getattr(out, "status", None) == "refused", getattr(out, "to_json", lambda: out)()
    assert getattr(out, "code", None) == "profile-selector-property"


def test_r204_export_pages_reference_order_still_property() -> None:
    """A page-typed reference refuses property even with page-occurrence order."""
    when = _select("self", "reference", "sourceOccurrence", "page-occurrence")
    out = _compile(_recipe_profile("export-pages", when))
    assert getattr(out, "status", None) == "refused", getattr(out, "to_json", lambda: out)()
    assert getattr(out, "code", None) == "profile-selector-property"


def test_r204_export_nodes_render_reference_refuses_property() -> None:
    """A render-domain reference refuses selector-property."""
    when = _select("render", "reference", "targetRef", "id")
    out = _compile(_recipe_profile("export-nodes", when))
    assert getattr(out, "status", None) == "refused", getattr(out, "to_json", lambda: out)()
    assert getattr(out, "code", None) == "profile-selector-property"


def test_r204_export_nodes_inverse_occurrence_refuses_type() -> None:
    """An inverse reference from an occurrence binding refuses profile-type."""
    when = _select("self", "inverseReference", "targetRef", "id")
    out = _compile(_recipe_profile("export-nodes", when))
    assert getattr(out, "status", None) == "refused", getattr(out, "to_json", lambda: out)()
    assert getattr(out, "code", None) == "profile-type"
