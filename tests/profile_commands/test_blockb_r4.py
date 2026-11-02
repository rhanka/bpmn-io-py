"""Block-B R4: occurrence-domain / compiler-static parity with JS fec4dae.

Witnesses for R3-01 and O-2, O-4, O-5, O-6 of the PY-R2 ruling, through
public operations (``load_profile``, ``compile_profile``,
``create_descriptor_context``, ``create_bridge``, ``complete_envelope``,
``set_definitions``, ``activate_business_profile``, ``evaluate_predicate``)
on the neutral lot-5 profile.
"""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bpmn_io.profile import ValidatedProfile
    from bpmn_io.profile._results import PureResult


def _neutral_profile() -> dict[str, Any]:
    """Load the neutral lot-5 profile document."""
    from tests.profile_commands import harness as h

    raw = (h.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
    return json.loads(raw.decode("utf-8"))


def _package() -> dict[str, Any]:
    """Return the default descriptor package with its bytes."""
    from tests.profile_commands import harness as h

    package = dict(h.DEFAULT_DESCRIPTOR_PIN)
    package["descriptorBytes"] = h.DEFAULT_DESCRIPTOR_BYTES
    return package


def _load(profile: dict[str, Any]) -> ValidatedProfile:
    """Load a profile document against the default descriptor pin."""
    from bpmn_io.profile import load_profile
    from tests.profile_commands import harness as h

    package = _package()
    pins = [
        {
            "id": package["id"],
            "version": package["version"],
            "sha256": package["sha256"],
        }
    ]
    loaded = load_profile(
        json.dumps(profile).encode(),
        schema_bytes=h.SCHEMA_BYTES,
        base_bytes=h.BASE_BYTES,
        descriptor_pins=pins,
        asset_bag=dict(h.METRICS_BAG),
    )
    assert loaded.status == "ok", loaded.to_json()
    return loaded.payload


def _compile(profile: dict[str, Any]) -> PureResult:
    """Compile a profile document with descriptor metadata and base."""
    from bpmn_io.profile import compile_profile, create_descriptor_context
    from tests.profile_commands import harness as h

    ctx = create_descriptor_context([_package()]).payload
    return compile_profile(
        _load(profile),
        descriptor_context=ctx,
        base=copy.deepcopy(h.BASE_DOCUMENT),
    )


def _with_ui_when(when: dict[str, Any]) -> dict[str, Any]:
    """Return the neutral profile with ``task-create.when`` replaced."""
    profile = _neutral_profile()
    entry = next(e for e in profile["ui"] if e["id"] == "task-create")
    entry["when"] = copy.deepcopy(when)
    return profile


def _with_recipe_when(recipe_id: str, when: dict[str, Any]) -> dict[str, Any]:
    """Return the neutral profile with one recipe ``when`` replaced."""
    profile = _neutral_profile()
    recipe = next(r for r in profile["recipes"] if r["id"] == recipe_id)
    recipe["when"] = copy.deepcopy(when)
    return profile


def _count(select: dict[str, Any]) -> dict[str, Any]:
    """Wrap a selector in ``count(min=0)``."""
    return {"op": "count", "min": 0, "select": select}


def _true() -> dict[str, Any]:
    return {"op": "true"}


def _occurrence_ref(prop: str, where: dict[str, Any]) -> dict[str, Any]:
    """Count ``self`` through an occurrence endpoint reference."""
    return _count(
        {
            "from": "self",
            "via": "reference",
            "property": prop,
            "where": where,
            "order": "page-occurrence",
        }
    )


def _tree() -> dict[str, Any]:
    return {
        "$type": "bpmn:Definitions",
        "id": "D_1",
        "targetNamespace": "urn:x",
        "rootElements": [
            {
                "$type": "bpmn:Process",
                "id": "P_1",
                "flowElements": [{"$type": "bpmn:Task", "id": "Task_1", "name": "Fixed"}],
            }
        ],
    }


def test_r3_01_nested_occurrence_reference_keeps_domain() -> None:
    """JS compiler-static.ts:179/:197: nested ``where`` sees an occurrence."""
    from bpmn_io.profile import (
        compile_profile,
        complete_envelope,
        create_bridge,
        create_descriptor_context,
    )

    nested = _occurrence_ref("sourceOccurrence", _occurrence_ref("targetOccurrence", _true()))
    profile = _with_recipe_when("export-nodes", nested)

    compiled = _compile(profile)
    assert compiled.status == "ok", compiled.to_json()
    free = compile_profile(_load(profile))
    assert free.status == "ok", free.to_json()

    ctx = create_descriptor_context([_package()]).payload
    bridge = create_bridge(ctx)
    envelope = complete_envelope(compiled.payload.identity, _tree(), [])
    assert bridge.set_definitions(envelope).status == "ok"
    activated = bridge.activate_business_profile(compiled.payload)
    assert activated.status == "ok", activated.to_json()


def _narrowed(prop: str, type_name: str) -> dict[str, Any]:
    """Reference from ``self`` narrowed by an exact ``typeIs`` sibling."""
    return _count(
        {
            "from": "root",
            "via": "all",
            "order": "id",
            "where": {
                "op": "all",
                "args": [
                    {
                        "op": "typeIs",
                        "binding": "self",
                        "type": type_name,
                        "mode": "exact",
                    },
                    _count(
                        {
                            "from": "self",
                            "via": "reference",
                            "property": prop,
                            "where": _true(),
                            "order": "id",
                        }
                    ),
                ],
            },
        }
    )


def test_o2_narrowed_reference_checks_narrowed_types() -> None:
    """JS compiler-static.ts:181-189: a narrowed ``from`` checks its types."""
    task = _compile(_with_ui_when(_narrowed("targetRef", "bpmn:Task")))
    assert task.status == "refused"
    assert task.code == "profile-selector-property"

    flow = _compile(_with_ui_when(_narrowed("targetRef", "bpmn:SequenceFlow")))
    assert flow.status == "ok", flow.to_json()


def test_o4_render_via_outside_export_refuses_type() -> None:
    """JS compiler-static.ts:158-166: render vias and ``semantic`` domain."""
    ui_pages = _compile(
        _with_ui_when(
            _count(
                {
                    "from": "self",
                    "via": "pages",
                    "where": _true(),
                    "order": "page-occurrence",
                }
            )
        )
    )
    assert ui_pages.status == "refused"
    assert ui_pages.code == "profile-type"

    root_semantic = _compile(
        _with_recipe_when(
            "export-pages",
            _count({"from": "root", "via": "semantic", "where": _true(), "order": "id"}),
        )
    )
    assert root_semantic.status == "refused"
    assert root_semantic.code == "profile-type"

    occurrence_semantic = _compile(
        _with_recipe_when(
            "export-nodes",
            _count({"from": "self", "via": "semantic", "where": _true(), "order": "id"}),
        )
    )
    assert occurrence_semantic.status == "ok", occurrence_semantic.to_json()


def test_o5_binding_owner_bound_in_ui_and_recipes() -> None:
    """JS compiler-static.ts:54, :240, :369: baseEnv binds ``bindingOwner``."""
    owner_id = {"op": "id", "binding": "bindingOwner"}
    ui = _compile(_with_ui_when({"op": "present", "value": owner_id}))
    assert ui.status == "ok", ui.to_json()

    profile = _neutral_profile()
    recipe = next(r for r in profile["recipes"] if r["id"] == "export-nodes")
    recipe["steps"][0]["fields"] = [
        {
            "name": "id",
            "value": {"op": "outputId", "binding": "self", "domain": "node"},
        },
        {"name": "name", "value": copy.deepcopy(owner_id)},
    ]
    emitted = _compile(profile)
    assert emitted.status == "ok", emitted.to_json()


def test_o6_unbound_native_evaluator_name_is_symbol() -> None:
    """Unbound native evaluator names refuse ``profile-symbol`` (R4-02 fix).

    The occurrence-scope MISSING rule this used to witness moved to the
    export map flow: ``test_blockb_r5.py`` exercises it through
    ``map_export`` (R4-03 rows).
    """
    from bpmn_io.profile import evaluate_predicate
    from bpmn_io.profile._evaluate import make_read_context

    tree = {
        "$type": "bpmn:Definitions",
        "id": "D_1",
        "rootElements": [
            {
                "$type": "bpmn:Process",
                "id": "P_1",
                "flowElements": [{"$type": "bpmn:Task", "id": "Task_1"}],
            }
        ],
    }
    ctx = make_read_context(tree)
    occurrence = {
        "pageId": "page-main",
        "occurrenceKey": "occ:Task_1",
        "semanticId": "Task_1",
        "role": "content",
    }
    bindings = {"root": tree, "self": occurrence}
    for value in (
        {"op": "id", "binding": "bindingOwner"},
        {"op": "read", "binding": "bindingOwner", "path": "/id"},
    ):
        result = evaluate_predicate({"op": "present", "value": value}, ctx, bindings)
        assert result.status == "refused", result.to_json()
        assert result.code == "profile-symbol", result.to_json()
