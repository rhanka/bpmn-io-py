"""Block-B R5: static admission and evaluator-scope witnesses (PY-R4 ruling §9.1).

R4-01 through R4-06, the O-3 render-only part, C-1, C-2 and C-3 through
public operations only (``load_profile``, ``compile_profile``,
``create_descriptor_context``, ``create_bridge``, ``complete_envelope``,
``set_definitions``, ``activate_business_profile``, ``list_entries``,
``apply_commands``, ``resolve_theme``, ``map_export``) on the neutral
lot-5 profile. Every expected value is the JS value of ruling §4 (taken
from the ``probes-py-r4`` corpus).
"""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bpmn_io.profile import HeadlessBridge, ValidatedProfile
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


def _variant_package() -> tuple[dict[str, Any], str]:
    """Return the ServiceTask-extends-Task descriptor package and its pin.

    Built in-test from the vendored lot-5 descriptor JSON:
    ``ServiceTask.extends = ["bpmn:Task"]``,
    ``Task.scalarTypes = {name: string}``,
    ``SequenceFlow.scalarTypes = {name: string}``,
    ``Process.scalarTypes = {isExecutable: boolean}``.
    """
    from tests.profile_commands import harness as h

    raw = (h.EXPECTED / "artifacts/neutral-descriptors.lot5.json").read_bytes()
    document = json.loads(raw.decode("utf-8"))
    assert isinstance(document, dict)
    types = document["types"]
    assert isinstance(types, dict)
    service = types["bpmn:ServiceTask"]
    assert isinstance(service, dict)
    service["extends"] = ["bpmn:Task"]
    task = types["bpmn:Task"]
    assert isinstance(task, dict)
    task["scalarTypes"] = {"name": "string"}
    flow = types["bpmn:SequenceFlow"]
    assert isinstance(flow, dict)
    flow["scalarTypes"] = {"name": "string"}
    process = types["bpmn:Process"]
    assert isinstance(process, dict)
    process["scalarTypes"] = {"isExecutable": "boolean"}
    package = dict(h.DEFAULT_DESCRIPTOR_PIN)
    package["descriptorBytes"] = document
    from bpmn_io.profile._c14n import digest_bytes, jcs

    sha = digest_bytes(jcs(document).encode("utf-8"))
    package["sha256"] = sha
    return package, sha


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


def _load_variant(profile: dict[str, Any], package: dict[str, Any], sha: str) -> ValidatedProfile:
    """Load a profile document against the variant descriptor pin."""
    from bpmn_io.profile import load_profile
    from tests.profile_commands import harness as h

    pins = [{"id": package["id"], "version": package["version"], "sha256": sha}]
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


def _compile_variant(profile: dict[str, Any]) -> PureResult:
    """Compile a profile document with the variant descriptor package."""
    from bpmn_io.profile import compile_profile, create_descriptor_context
    from tests.profile_commands import harness as h

    package, sha = _variant_package()
    profile = copy.deepcopy(profile)
    descriptors = profile.get("descriptors")
    assert isinstance(descriptors, list)
    assert descriptors
    first = descriptors[0]
    assert isinstance(first, dict)
    first["sha256"] = sha
    ctx = create_descriptor_context([package]).payload
    return compile_profile(
        _load_variant(profile, package, sha),
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


def _with_capabilities(when: dict[str, Any]) -> dict[str, Any]:
    """Return the neutral profile with the [structural, unsupported] pair."""
    profile = _neutral_profile()
    profile["exports"][0]["capabilities"] = [
        {"when": {"op": "true"}, "class": "structural", "losses": []},
        {"when": copy.deepcopy(when), "class": "unsupported", "losses": []},
    ]
    return profile


def _with_emit_value(recipe_id: str, value: dict[str, Any]) -> dict[str, Any]:
    """Return the neutral profile with one emit field value replaced."""
    profile = _neutral_profile()
    recipe = next(r for r in profile["recipes"] if r["id"] == recipe_id)
    field = next(f for f in recipe["steps"][0]["fields"] if f["name"] == "name")
    field["value"] = copy.deepcopy(value)
    return profile


def _with_bind_root_all() -> dict[str, Any]:
    """Bind ``sem`` to ``root via all`` and read it in the node emit."""
    profile = _neutral_profile()
    recipe = next(r for r in profile["recipes"] if r["id"] == "export-nodes")
    select = {
        "from": "root",
        "via": "all",
        "where": {"op": "typeIs", "binding": "self", "type": "bpmn:Process", "mode": "exact"},
        "order": "id",
    }
    steps = [{"op": "bind", "as": "sem", "cardinality": "zeroOrOne", "select": select}]
    for step in recipe["steps"]:
        renamed = copy.deepcopy(step)
        for field in renamed.get("fields", []):
            if field.get("name") == "name":
                field["value"] = {"op": "id", "binding": "sem"}
        steps.append(renamed)
    recipe["steps"] = steps
    return profile


def _tree_two() -> dict[str, Any]:
    """Return the two-task semantic tree of the runtime probes."""
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
                    {"$type": "bpmn:Task", "id": "Task_2"},
                ],
            }
        ],
    }


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


def _bridge_over(compiled: ValidatedProfile, tree: dict[str, Any]) -> HeadlessBridge:
    """Return an activated bridge over one compiled profile and tree."""
    from bpmn_io.profile import (
        complete_envelope,
        create_bridge,
        create_descriptor_context,
    )

    ctx = create_descriptor_context([_package()]).payload
    bridge = create_bridge(ctx)
    envelope = complete_envelope(compiled.identity, copy.deepcopy(tree), [])
    assert bridge.set_definitions(envelope).status == "ok"
    activated = bridge.activate_business_profile(compiled)
    assert activated.status == "ok", activated.to_json()
    return bridge


def _ui_ids(profile: dict[str, Any]) -> PureResult:
    """List the palette entries of one profile over the two-task tree."""
    compiled = _compile(profile)
    assert compiled.status == "ok", compiled.to_json()
    bridge = _bridge_over(compiled.payload, _tree_two())
    return bridge.list_entries(
        base_revision=bridge.envelope.semantic_revision,
        surface="palette",
        subject="P_1",
        locale="en",
    )


def _surface_create(profile: dict[str, Any]) -> PureResult:
    """Apply the ``task-create`` surface command of one profile."""
    compiled = _compile(profile)
    assert compiled.status == "ok", compiled.to_json()
    bridge = _bridge_over(compiled.payload, _tree_two())
    snapshot = bridge.get_snapshot()
    return bridge.apply_commands(
        base_revision=bridge.envelope.semantic_revision,
        expected_view_revision=snapshot.payload["viewRevision"],
        transaction_id="tx-r5",
        commands=[
            {
                "command": "surface",
                "entry": "task-create",
                "context": {"owner": "P_1", "key": "r5", "value": "W"},
            }
        ],
    )


def _export_names(
    profile: dict[str, Any],
) -> tuple[ResultSuccess | ResultRefused, list[Any] | None]:
    """Map-export one profile over the shared layout (result, kind/name rows)."""
    from bpmn_io.profile._export import map_export
    from bpmn_io.profile._render import resolve_theme

    compiled = _compile(profile)
    assert compiled.status == "ok", compiled.to_json()
    result = compiled.payload
    from bpmn_io.profile import complete_envelope

    envelope = complete_envelope(result.identity, _tree_one(), [])
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


def _count(select: dict[str, Any], minimum: int = 0) -> dict[str, Any]:
    """Wrap a selector in ``count``."""
    return {"op": "count", "min": minimum, "select": select}


def _self_ref(prop: str, where: dict[str, Any]) -> dict[str, Any]:
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


def _ref_target(where: dict[str, Any]) -> dict[str, Any]:
    """Count ``self`` through the native ``targetRef`` reference."""
    return _count(
        {
            "from": "self",
            "via": "reference",
            "property": "targetRef",
            "where": where,
            "order": "id",
        }
    )


def test_r4_01_guard_intersection_narrows_domain() -> None:
    """JS compiler-static.ts:111-124: a later guard narrows an earlier sibling."""
    when = _count(
        {
            "from": "root",
            "via": "all",
            "where": {
                "op": "all",
                "args": [
                    {
                        "op": "typeIs",
                        "binding": "self",
                        "type": "bpmn:Task",
                        "mode": "assignable",
                    },
                    _ref_target({"op": "true"}),
                ],
            },
            "order": "id",
        }
    )
    compiled = _compile(_with_ui_when(when))
    assert compiled.status == "refused", compiled.to_json()
    assert compiled.code == "profile-selector-property"


def test_r4_01_contradiction_refuses_on_empty_domain() -> None:
    """An exact contradiction leaves an empty domain: no reference admits."""
    when = {
        "op": "all",
        "args": [
            {"op": "typeIs", "binding": "self", "type": "bpmn:Task", "mode": "exact"},
            {
                "op": "typeIs",
                "binding": "self",
                "type": "bpmn:SequenceFlow",
                "mode": "exact",
            },
            _ref_target({"op": "true"}),
        ],
    }
    compiled = _compile(_with_ui_when(when))
    assert compiled.status == "refused", compiled.to_json()
    assert compiled.code == "profile-selector-property"


def test_r4_01_recognizes_narrows_domain() -> None:
    """JS compiler-static.ts:117-119: ``recognizes`` narrows to native types."""
    when = {
        "op": "all",
        "args": [
            {"op": "recognizes", "binding": "self", "notion": "task"},
            _ref_target({"op": "true"}),
        ],
    }
    compiled = _compile(_with_ui_when(when))
    assert compiled.status == "refused", compiled.to_json()
    assert compiled.code == "profile-selector-property"


def test_r4_01_control_sequence_flow_ok() -> None:
    """The un-narrowed ``SequenceFlow`` domain keeps ``targetRef``."""
    when = {
        "op": "all",
        "args": [
            {
                "op": "typeIs",
                "binding": "self",
                "type": "bpmn:SequenceFlow",
                "mode": "exact",
            },
            _ref_target({"op": "true"}),
        ],
    }
    compiled = _compile(_with_ui_when(when))
    assert compiled.status == "ok", compiled.to_json()


def _service_then_task(mode: str) -> dict[str, Any]:
    """Narrow ``ServiceTask`` then ``Task`` and read the narrowed id."""
    return {
        "op": "all",
        "args": [
            {
                "op": "typeIs",
                "binding": "self",
                "type": "bpmn:ServiceTask",
                "mode": "exact",
            },
            {"op": "typeIs", "binding": "self", "type": "bpmn:Task", "mode": mode},
            {"op": "present", "value": {"op": "id", "binding": "self"}},
        ],
    }


def test_r4_01_empty_domain_refuses_id() -> None:
    """Without ``extends`` the narrowed domain is empty and id-less."""
    compiled = _compile(_with_ui_when(_service_then_task("assignable")))
    assert compiled.status == "refused", compiled.to_json()
    assert compiled.code == "profile-type"


def test_r4_01_variant_extends_keeps_id_domain() -> None:
    """With ``ServiceTask extends Task`` the narrowed domain bears an id."""
    compiled = _compile_variant(_with_ui_when(_service_then_task("assignable")))
    assert compiled.status == "ok", compiled.to_json()


def test_r4_01_variant_exact_task_refuses_id() -> None:
    """An exact ``Task`` guard still empties the ``ServiceTask`` domain."""
    compiled = _compile_variant(_with_ui_when(_service_then_task("exact")))
    assert compiled.status == "refused", compiled.to_json()
    assert compiled.code == "profile-type"


def test_r4_01_variant_text_prefix_needs_string() -> None:
    """``textPrefix`` over the boolean ``isExecutable`` refuses."""
    when = {
        "op": "textPrefix",
        "value": {"op": "read", "binding": "self", "path": "/isExecutable"},
        "prefix": "x",
        "trim": "none",
    }
    compiled = _compile_variant(_with_ui_when(when))
    assert compiled.status == "refused", compiled.to_json()
    assert compiled.code == "profile-type"


def test_r4_01_activation_lane_rechecks_with_descriptors() -> None:
    """C-3: metadata-free compile admits; activation refuses with descriptors."""
    from bpmn_io.profile import (
        compile_profile,
        complete_envelope,
        create_bridge,
        create_descriptor_context,
    )

    profile = _with_ui_when(
        _count(
            {
                "from": "root",
                "via": "all",
                "where": {
                    "op": "all",
                    "args": [
                        {
                            "op": "typeIs",
                            "binding": "self",
                            "type": "bpmn:Task",
                            "mode": "assignable",
                        },
                        _ref_target({"op": "true"}),
                    ],
                },
                "order": "id",
            }
        )
    )
    free = compile_profile(_load(profile))
    assert free.status == "ok", free.to_json()
    ctx = create_descriptor_context([_package()]).payload
    bridge = create_bridge(ctx)
    envelope = complete_envelope(
        free.payload.identity,
        {
            "$type": "bpmn:Definitions",
            "id": "D_1",
            "targetNamespace": "urn:x",
            "rootElements": [
                {
                    "$type": "bpmn:Process",
                    "id": "P_1",
                    "flowElements": [{"$type": "bpmn:Task", "id": "Task_1"}],
                }
            ],
        },
        [],
    )
    assert bridge.set_definitions(envelope).status == "ok"
    activated = bridge.activate_business_profile(free.payload)
    assert activated.status == "refused", activated.to_json()
    assert activated.code == "profile-selector-property"


def test_r4_02_unbound_read_refuses_symbol_in_ui() -> None:
    """JS compiler.ts:690-699: an unbound ``read`` is ``profile-symbol``."""
    when = {
        "op": "present",
        "value": {"op": "read", "binding": "bindingOwner", "path": "/name"},
    }
    result = _ui_ids(_with_ui_when(when))
    assert result.status == "refused", result.to_json()
    assert result.code == "profile-symbol"


def test_r4_02_unbound_read_refuses_symbol_on_command() -> None:
    """The same unbound ``read`` refuses through the surface command."""
    profile = _neutral_profile()
    recipe = next(r for r in profile["recipes"] if r["id"] == "create-task")
    recipe["when"] = {
        "op": "present",
        "value": {"op": "read", "binding": "bindingOwner", "path": "/name"},
    }
    result = _surface_create(profile)
    assert result.status == "refused", result.to_json()
    assert result.code == "profile-symbol"


def test_r4_02_unbound_type_is_refuses_symbol() -> None:
    """JS compiler.ts:1024-1027: an unbound ``typeIs`` is ``profile-symbol``."""
    when = {
        "op": "typeIs",
        "binding": "bindingOwner",
        "type": "bpmn:Task",
        "mode": "exact",
    }
    result = _ui_ids(_with_ui_when(when))
    assert result.status == "refused", result.to_json()
    assert result.code == "profile-symbol"


def test_r4_03_semantic_owner_id_ok() -> None:
    """The bound owner id reads through ``semantic`` (occurrence scope)."""
    when = _count(
        {
            "from": "self",
            "via": "semantic",
            "where": {
                "op": "present",
                "value": {"op": "id", "binding": "bindingOwner"},
            },
            "order": "id",
        },
        minimum=1,
    )
    mapped, names = _export_names(_with_capabilities(when))
    assert mapped.status == "ok", mapped.to_json()
    assert names == [["page", "main"], ["node", None]]


def test_r4_03_root_id_present_false_ok() -> None:
    """``root`` is not a bound name: its id reads missing, ``present`` false."""
    when = {"op": "present", "value": {"op": "id", "binding": "root"}}
    mapped, names = _export_names(_with_capabilities(when))
    assert mapped.status == "ok", mapped.to_json()
    assert names == [["page", "main"], ["node", None]]


def test_r4_03_type_is_self_unsupported() -> None:
    """The occurrence target is not a native task: the class is unsupported."""
    when = {"op": "typeIs", "binding": "self", "type": "bpmn:Task", "mode": "exact"}
    mapped, _ = _export_names(_with_capabilities(when))
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "render-unsupported"


def test_r4_03_false_first_short_circuits_ok() -> None:
    """``all(false, ...)`` short-circuits: the capability never holds."""
    when = {
        "op": "all",
        "args": [
            {"op": "false"},
            {
                "op": "typeIs",
                "binding": "bindingOwner",
                "type": "bpmn:Task",
                "mode": "exact",
            },
        ],
    }
    mapped, names = _export_names(_with_capabilities(when))
    assert mapped.status == "ok", mapped.to_json()
    assert names == [["page", "main"], ["node", None]]


def test_r4_03_root_all_is_operation_error() -> None:
    """Only ``self`` selects from ``root`` in occurrence scope."""
    when = _count({"from": "root", "via": "all", "where": {"op": "true"}, "order": "id"})
    mapped, _ = _export_names(_with_capabilities(when))
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "operation-error"


def test_r4_03_emit_unbound_owner_id_invalid() -> None:
    """An emit over an unbound name refuses ``export-field-invalid``."""
    value = {"op": "id", "binding": "bindingOwner"}
    mapped, _ = _export_names(_with_emit_value("export-pages", value))
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "export-field-invalid"


def test_r4_03_emit_root_id_invalid() -> None:
    """``root`` is not bound in occurrence scope: emit refuses as well."""
    value = {"op": "id", "binding": "root"}
    mapped, _ = _export_names(_with_emit_value("export-pages", value))
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "export-field-invalid"


def test_r4_03_emit_case_of_missing_label_invalid() -> None:
    """``case`` over the missing label refuses ``profile-type``."""
    value = {
        "op": "case",
        "value": {"op": "read", "binding": "self", "path": "/label/text"},
        "mode": "upper",
        "unicode": "15.0.0",
    }
    mapped, _ = _export_names(_with_emit_value("export-nodes", value))
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "profile-type"


def test_r4_03_bind_root_all_is_operation_error() -> None:
    """Bind aliases consult the occurrence select only: ``root`` errors."""
    mapped, _ = _export_names(_with_bind_root_all())
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "operation-error"


def test_r4_04_pages_from_occurrence_refuses() -> None:
    """JS :158-159: ``pages`` needs ``RenderData`` even in export."""
    when = _count(
        {"from": "self", "via": "pages", "where": {"op": "true"}, "order": "page-occurrence"}
    )
    compiled = _compile(_with_recipe_when("export-nodes", when))
    assert compiled.status == "refused", compiled.to_json()
    assert compiled.code == "profile-type"


def test_r4_04_occurrences_from_occurrence_refuses() -> None:
    """``occurrences`` from an occurrence handle refuses as well."""
    when = _count(
        {"from": "self", "via": "occurrences", "where": {"op": "true"}, "order": "page-occurrence"}
    )
    compiled = _compile(_with_recipe_when("export-nodes", when))
    assert compiled.status == "refused", compiled.to_json()
    assert compiled.code == "profile-type"


def test_r4_04_occurrences_from_root_refuses() -> None:
    """``occurrences`` from the native root refuses outside render data."""
    when = _count(
        {"from": "root", "via": "occurrences", "where": {"op": "true"}, "order": "page-occurrence"}
    )
    compiled = _compile(_with_recipe_when("export-nodes", when))
    assert compiled.status == "refused", compiled.to_json()
    assert compiled.code == "profile-type"


def test_r4_04_control_pages_recipe_occurrences_ok() -> None:
    """``export-pages`` selects occurrences from its page handle."""
    when = _count(
        {"from": "self", "via": "occurrences", "where": {"op": "true"}, "order": "page-occurrence"}
    )
    compiled = _compile(_with_recipe_when("export-pages", when))
    assert compiled.status == "ok", compiled.to_json()


def test_r4_05_nested_reference_refuses_property() -> None:
    """A reference result domain re-checks the reference property."""
    when = _ref_target(_ref_target({"op": "true"}))
    compiled = _compile(_with_ui_when(when))
    assert compiled.status == "refused", compiled.to_json()
    assert compiled.code == "profile-selector-property"


def test_r4_05_root_reference_refuses_property() -> None:
    """``root via reference`` is a native reference without a result."""
    when = _count(
        {
            "from": "root",
            "via": "reference",
            "property": "targetRef",
            "where": {"op": "true"},
            "order": "id",
        }
    )
    compiled = _compile(_with_ui_when(when))
    assert compiled.status == "refused", compiled.to_json()
    assert compiled.code == "profile-selector-property"


def test_r4_05_reference_result_without_name_refuses() -> None:
    """A target type lacking ``name`` fails the ``read`` on the union."""
    where = {
        "op": "present",
        "value": {"op": "read", "binding": "self", "path": "/name"},
    }
    compiled = _compile(_with_ui_when(_ref_target(where)))
    assert compiled.status == "refused", compiled.to_json()
    assert compiled.code == "profile-type"


def test_r4_05_control_reference_result_id_ok() -> None:
    """Every reference target bears an id: the nested ``where`` admits."""
    where = {"op": "present", "value": {"op": "id", "binding": "self"}}
    compiled = _compile(_with_ui_when(_ref_target(where)))
    assert compiled.status == "ok", compiled.to_json()


def test_r4_06_occurrence_id_refuses_in_export_nodes() -> None:
    """JS :89-95: an occurrence domain never bears an id."""
    when = {"op": "present", "value": {"op": "id", "binding": "self"}}
    compiled = _compile(_with_recipe_when("export-nodes", when))
    assert compiled.status == "refused", compiled.to_json()
    assert compiled.code == "profile-type"


def test_r4_06_page_id_refuses_in_export_pages() -> None:
    """A page domain never bears an id either."""
    when = {"op": "present", "value": {"op": "id", "binding": "self"}}
    compiled = _compile(_with_recipe_when("export-pages", when))
    assert compiled.status == "refused", compiled.to_json()
    assert compiled.code == "profile-type"


def test_r4_06_render_id_refuses() -> None:
    """``render`` is not id-bearing in any export position."""
    when = {"op": "present", "value": {"op": "id", "binding": "render"}}
    compiled = _compile(_with_recipe_when("export-nodes", when))
    assert compiled.status == "refused", compiled.to_json()
    assert compiled.code == "profile-type"


def test_r4_06_control_owner_id_ok() -> None:
    """The native owner domain keeps its id."""
    when = {"op": "present", "value": {"op": "id", "binding": "bindingOwner"}}
    compiled = _compile(_with_recipe_when("export-nodes", when))
    assert compiled.status == "ok", compiled.to_json()


def test_o3_render_read_always_refuses() -> None:
    """JS compiler-static.ts:12: every ``read`` on ``RenderData`` refuses."""
    for path in ("/x", "/pageId"):
        when = {
            "op": "present",
            "value": {"op": "read", "binding": "render", "path": path},
        }
        compiled = _compile(_with_recipe_when("export-nodes", when))
        assert compiled.status == "refused", compiled.to_json()
        assert compiled.code == "profile-type"


def test_c1_occurrence_bounds_admitted() -> None:
    """``OccurrenceHandle`` admits ``/bounds/x`` (C-1)."""
    when = {
        "op": "present",
        "value": {"op": "read", "binding": "self", "path": "/bounds/x"},
    }
    compiled = _compile(_with_recipe_when("export-nodes", when))
    assert compiled.status == "ok", compiled.to_json()


def test_c1_occurrence_label_lines_refuses() -> None:
    """Only ``/label/text`` is admitted on an occurrence label."""
    when = {
        "op": "present",
        "value": {"op": "read", "binding": "self", "path": "/label/lines"},
    }
    compiled = _compile(_with_recipe_when("export-nodes", when))
    assert compiled.status == "refused", compiled.to_json()
    assert compiled.code == "profile-type"


def test_c2_recognizes_two_tasks_lists_task_create() -> None:
    """The raw recognition table decides ``recognizes`` in UI contexts."""
    when = _count(
        {
            "from": "root",
            "via": "all",
            "where": {"op": "recognizes", "binding": "self", "notion": "task"},
            "order": "id",
        },
        minimum=2,
    )
    result = _ui_ids(_with_ui_when(when))
    assert result.status == "ok", result.to_json()
    ids = sorted(
        entry["id"] for group in result.payload.get("groups", []) for entry in group["entries"]
    )
    assert "task-create" in ids


def _with_emit_parent(parent: dict[str, Any], *, bind_semantic: bool) -> dict[str, Any]:
    """Return the neutral profile with an export-nodes emit parent."""
    profile = _neutral_profile()
    recipe = next(r for r in profile["recipes"] if r["id"] == "export-nodes")
    emit = copy.deepcopy(recipe["steps"][0])
    emit["parent"] = copy.deepcopy(parent)
    steps: list[dict[str, Any]] = []
    if bind_semantic:
        select = {"from": "self", "via": "semantic", "where": {"op": "true"}, "order": "id"}
        steps.append({"op": "bind", "as": "sem", "cardinality": "one", "select": select})
    recipe["steps"] = [*steps, emit]
    return profile


def test_emit_parent_alias_is_unbound_in_parent_scope() -> None:
    """JS lot4-export.ts:591-599: a non-outputId parent sees only self."""
    parent = {"op": "id", "binding": "sem"}
    mapped, _ = _export_names(_with_emit_parent(parent, bind_semantic=True))
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "export-field-invalid"


def test_emit_parent_self_read_reaches_parent_check() -> None:
    """Control: a self parent value is evaluated, then not a planned id."""
    parent = {"op": "read", "binding": "self", "path": "/pageId"}
    mapped, _ = _export_names(_with_emit_parent(parent, bind_semantic=False))
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "export-parent-invalid"
