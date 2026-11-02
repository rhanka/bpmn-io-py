"""Block-B R6: R5-01 through R5-05 witnesses (sol R5 REPORT.md).

Public operations only (``load_profile``, ``compile_profile``,
``create_descriptor_context``, ``create_bridge``, ``complete_envelope``,
``set_definitions``, ``activate_business_profile``, ``resolve_theme``,
``map_export``) on the neutral lot-5 profile. Every expected value is the JS
value of the sol R5 reverification (``compile-extra-js.json`` and
``runtime-extra-js.json`` under ``.h2a/sol-r5/``).
"""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bpmn_io.profile import ValidatedProfile
    from bpmn_io.profile._results import PureResult, ResultRefused, ResultSuccess


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


def _tree_one() -> dict[str, Any]:
    """Return the one-unnamed-task semantic tree of the export probes."""
    return {
        "$type": "bpmn:Definitions",
        "id": "D_1",
        "targetNamespace": "urn:x",
        "rootElements": [
            {
                "$type": "bpmn:Process",
                "id": "P_1",
                "flowElements": [{"$type": "bpmn:Task", "id": "Task_2"}],
            }
        ],
    }


def _tree_gateway() -> dict[str, Any]:
    """Return the export tree with an id-less-reference gateway beside Task_2."""
    tree = _tree_one()
    flow = tree["rootElements"][0]["flowElements"]
    flow.append(
        {
            "$type": "bpmn:ExclusiveGateway",
            "id": "G_1",
            "incoming": [],
            "outgoing": [],
        }
    )
    return tree


def _layout() -> dict[str, Any]:
    """Return the shared one-page, one-occurrence layout."""
    return {
        "layoutVersion": "1",
        "pages": [
            {
                "pageId": "page-main",
                "name": "main",
                "order": 0,
                "semanticRootId": "P_1",
                "bounds": {"x": 0, "y": 0, "width": 2000000, "height": 1000000},
            }
        ],
        "geometry": [
            {
                "pageId": "page-main",
                "occurrenceKey": "occ:Task_2",
                "semanticId": "Task_2",
                "role": "content",
                "bounds": {"x": 1500000, "y": 200000, "width": 1000000, "height": 800000},
            }
        ],
    }


def _export_names(
    profile: dict[str, Any], tree: dict[str, Any] | None = None
) -> tuple[ResultSuccess | ResultRefused, list[Any] | None]:
    """Map-export one profile over the shared layout (result, kind/name rows)."""
    from bpmn_io.profile._export import map_export
    from bpmn_io.profile._render import resolve_theme

    compiled = _compile(profile)
    assert compiled.status == "ok", compiled.to_json()
    result = compiled.payload
    from bpmn_io.profile import complete_envelope

    envelope = complete_envelope(result.identity, tree or _tree_one(), [])
    render = resolve_theme(
        result,
        envelope,
        copy.deepcopy(_layout()),
        "plain",
        {"semantic": [], "occurrence": []},
        {"native": [], "bioc": []},
    )
    assert render.status == "ok", render.to_json()
    fmt = profile["exports"][0]["format"]
    mapped = map_export(result, envelope, copy.deepcopy(_layout()), render.payload, fmt)
    names: list[Any] | None = None
    if mapped.status == "ok":
        payload = mapped.payload if isinstance(mapped.payload, dict) else {}
        records = payload.get("ir") or (payload.get("payload") or {}).get("ir") or []
        names = [[record.get("kind"), record.get("name")] for record in records]
    return mapped, names


def _with_create_fields(fields: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the neutral profile with ``create-task`` step fields replaced."""
    profile = _neutral_profile()
    recipe = next(r for r in profile["recipes"] if r["id"] == "create-task")
    recipe["steps"][0]["fields"] = copy.deepcopy(fields)
    return profile


def _with_capabilities(when: dict[str, Any]) -> dict[str, Any]:
    """Return the neutral profile with the [structural, unsupported] pair."""
    profile = _neutral_profile()
    profile["exports"][0]["capabilities"] = [
        {"when": {"op": "true"}, "class": "structural", "losses": []},
        {"when": copy.deepcopy(when), "class": "unsupported", "losses": []},
    ]
    return profile


def _with_emit_steps(steps: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the neutral profile with ``export-nodes`` steps replaced."""
    profile = _neutral_profile()
    recipe = next(r for r in profile["recipes"] if r["id"] == "export-nodes")
    recipe["steps"] = copy.deepcopy(steps)
    return profile


def _node_emit(name_value: dict[str, Any], parent: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the neutral node emit with one name value and one parent."""
    return [
        {
            "as": "node",
            "fields": [
                {
                    "name": "id",
                    "value": {"binding": "self", "domain": "node", "op": "outputId"},
                },
                {"name": "name", "value": copy.deepcopy(name_value)},
            ],
            "kind": "node",
            "op": "emit",
            "parent": copy.deepcopy(parent),
        }
    ]


def _case_name() -> dict[str, Any]:
    """Return the ``case`` over the missing label of the R5-05 input."""
    return {
        "op": "case",
        "value": {"op": "read", "binding": "self", "path": "/label/text"},
        "mode": "upper",
        "unicode": "15.0.0",
    }


def _reachable_capability(source: str) -> dict[str, Any]:
    """Return the R5-02/R5-03 delegated ``reachable`` capability predicate."""
    leg = {"from": source, "via": "self", "where": {"op": "true"}, "order": "id"}
    return {
        "op": "reachable",
        "from": copy.deepcopy(leg),
        "to": copy.deepcopy(leg),
        "edgeTypes": ["bpmn:SequenceFlow"],
        "minHops": 0,
    }


def _gateway_equal_capability(right_path: str) -> dict[str, Any]:
    """Return the R5-04 gateway ``equal`` capability predicate."""
    inner = {
        "op": "all",
        "args": [
            {
                "op": "typeIs",
                "binding": "self",
                "type": "bpmn:ExclusiveGateway",
                "mode": "exact",
            },
            {
                "op": "equal",
                "left": {"op": "read", "binding": "self", "path": "/incoming"},
                "right": {"op": "read", "binding": "self", "path": right_path},
            },
        ],
    }
    flow = {
        "op": "count",
        "min": 1,
        "select": {
            "from": "self",
            "via": "children",
            "where": inner,
            "order": "id",
            "property": "flowElements",
        },
    }
    process = {
        "op": "count",
        "min": 1,
        "select": {
            "from": "self",
            "via": "children",
            "where": {
                "op": "all",
                "args": [
                    {
                        "op": "typeIs",
                        "binding": "self",
                        "type": "bpmn:Process",
                        "mode": "exact",
                    },
                    flow,
                ],
            },
            "order": "id",
            "property": "rootElements",
        },
    }
    return {
        "op": "count",
        "min": 1,
        "select": {"from": "root", "via": "self", "where": process, "order": "id"},
    }


def test_r6_01_duplicate_create_fields_refuse_symbol() -> None:
    """JS compiler-static.ts:273: duplicate create fields refuse admission."""
    fields = [
        {"name": "name", "value": {"op": "literal", "value": "A"}},
        {"name": "name", "value": {"op": "literal", "value": "B"}},
    ]
    compiled = _compile(_with_create_fields(fields))
    assert compiled.status == "refused", compiled.to_json()
    assert compiled.code == "profile-symbol"


def test_r6_01_duplicate_create_fields_refuse_symbol_free() -> None:
    """The duplicate check is descriptor-independent: free compile refuses."""
    from bpmn_io.profile import compile_profile

    fields = [
        {"name": "name", "value": {"op": "literal", "value": "A"}},
        {"name": "name", "value": {"op": "literal", "value": "B"}},
    ]
    free = compile_profile(_load(_with_create_fields(fields)))
    assert free.status == "refused", free.to_json()
    assert free.code == "profile-symbol"


def test_r6_01_single_create_field_ok() -> None:
    """Positive control: one create field still compiles."""
    compiled = _compile(_neutral_profile())
    assert compiled.status == "ok", compiled.to_json()


def test_r6_02_delegated_reachable_root_refuses_symbol() -> None:
    """JS lot4-query.ts:242-244: no unbound root is invented for delegation."""
    for source in ("root", "bindingOwner"):
        mapped, _ = _export_names(_with_capabilities(_reachable_capability(source)))
        assert mapped.status == "refused", mapped.to_json()
        assert mapped.code == "profile-symbol"


def test_r6_02_reachable_short_circuit_controls() -> None:
    """``all(false, X)`` and ``any(true, X)`` match JS around the refusal."""
    probe = _reachable_capability("root")
    mapped, names = _export_names(
        _with_capabilities({"op": "all", "args": [{"op": "false"}, probe]})
    )
    assert mapped.status == "ok", mapped.to_json()
    assert names == [["page", "main"], ["node", None]]
    mapped, _ = _export_names(_with_capabilities({"op": "any", "args": [{"op": "true"}, probe]}))
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "render-unsupported"


def test_r6_03_delegated_reachable_self_ok() -> None:
    """JS compiler.ts:1114: the id-less occurrence is no graph vertex."""
    mapped, names = _export_names(_with_capabilities(_reachable_capability("self")))
    assert mapped.status == "ok", mapped.to_json()
    assert names == [["page", "main"], ["node", None]]


def test_r6_04_equal_reference_arrays_ok() -> None:
    """JS lot4-query.ts:220-224: distinct arrays are not identical."""
    mapped, names = _export_names(
        _with_capabilities(_gateway_equal_capability("/outgoing")), _tree_gateway()
    )
    assert mapped.status == "ok", mapped.to_json()
    assert names == [["page", "main"], ["node", None]]


def test_r6_04_equal_same_array_selects_unsupported() -> None:
    """Positive control: the same array object is identical to itself."""
    mapped, _ = _export_names(
        _with_capabilities(_gateway_equal_capability("/incoming")), _tree_gateway()
    )
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "render-unsupported"


def test_r6_05_invalid_parent_before_case_name() -> None:
    """JS lot4-export.ts:560-608: the parent refusal comes first."""
    parent = {"op": "literal", "value": "missing-id"}
    mapped, _ = _export_names(_with_emit_steps(_node_emit(_case_name(), parent)))
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "export-parent-invalid"


def test_r6_05_missing_or_root_parent_field_invalid() -> None:
    """``id`` of an unbound parent name is ``export-field-invalid``, as JS."""
    for binding in ("bindingOwner", "root"):
        parent = {"op": "id", "binding": binding}
        mapped, _ = _export_names(_with_emit_steps(_node_emit(_case_name(), parent)))
        assert mapped.status == "refused", mapped.to_json()
        assert mapped.code == "export-field-invalid"


def test_r6_05_invalid_parent_good_name_control() -> None:
    """With a valid literal name the parent error still matches JS."""
    parent = {"op": "literal", "value": "missing-id"}
    name = {"op": "literal", "value": "x"}
    mapped, _ = _export_names(_with_emit_steps(_node_emit(name, parent)))
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "export-parent-invalid"
