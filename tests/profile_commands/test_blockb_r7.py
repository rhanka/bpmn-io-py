"""Block-B R7: R6-01 through R6-08 witnesses (sol R6 REPORT.md).

Public operations only (``load_profile``, ``compile_profile``,
``create_descriptor_context``, ``create_bridge``, ``complete_envelope``,
``set_definitions``, ``activate_business_profile``, ``resolve_theme``,
``map_export``, ``list_entries``, ``apply_commands``) on the neutral lot-5
profile. Every expected value is the JS value of the sol R6 reverification
(``findings-runtime-js.json``, ``findings-compile-js.json``,
``more-runtime-js.json`` and friends under ``.h2a/sol-r6/``).
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
    pins = [{"id": package["id"], "version": package["version"], "sha256": package["sha256"]}]
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
        _load(profile), descriptor_context=ctx, base=copy.deepcopy(h.BASE_DOCUMENT)
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


def _tree_cycle() -> dict[str, Any]:
    """Return the two-task cycle tree of the reachable probes (sol R6)."""
    return {
        "$type": "bpmn:Definitions",
        "id": "D_1",
        "targetNamespace": "urn:x",
        "rootElements": [
            {
                "$type": "bpmn:Process",
                "id": "P_1",
                "flowElements": [
                    {"$type": "bpmn:Task", "id": "Task_2"},
                    {"$type": "bpmn:Task", "id": "Task_3"},
                    {
                        "$type": "bpmn:SequenceFlow",
                        "id": "F_1",
                        "sourceRef": "Task_2",
                        "targetRef": "Task_3",
                    },
                    {
                        "$type": "bpmn:SequenceFlow",
                        "id": "F_2",
                        "sourceRef": "Task_3",
                        "targetRef": "Task_2",
                    },
                ],
            }
        ],
    }


def _tree_named_task() -> dict[str, Any]:
    """Return the named-task tree of the label geometry control."""
    return {
        "$type": "bpmn:Definitions",
        "id": "D_1",
        "targetNamespace": "urn:x",
        "rootElements": [
            {
                "$type": "bpmn:Process",
                "id": "P_1",
                "flowElements": [{"$type": "bpmn:Task", "id": "Task_2", "name": "Task"}],
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


def _export_result(
    profile: dict[str, Any],
    tree: dict[str, Any] | None = None,
    layout: dict[str, Any] | None = None,
) -> ResultSuccess | ResultRefused:
    """Compile and map-export one profile (refused or success)."""
    from bpmn_io.profile import complete_envelope
    from bpmn_io.profile._export import map_export
    from bpmn_io.profile._render import resolve_theme

    compiled = _compile(profile)
    assert compiled.status == "ok", compiled.to_json()
    result = compiled.payload
    envelope = complete_envelope(result.identity, tree or _tree_one(), [])
    render = resolve_theme(
        result,
        envelope,
        copy.deepcopy(layout or _layout()),
        "plain",
        {"semantic": [], "occurrence": []},
        {"native": [], "bioc": []},
    )
    assert render.status == "ok", render.to_json()
    fmt = profile["exports"][0]["format"]
    return map_export(result, envelope, copy.deepcopy(layout or _layout()), render.payload, fmt)


def _export_names(
    profile: dict[str, Any], tree: dict[str, Any] | None = None
) -> tuple[Any, list[Any] | None]:
    """Map-export and return (result, kind/name rows)."""
    mapped = _export_result(profile, tree)
    names: list[Any] | None = None
    if mapped.status == "ok":
        payload = mapped.payload if isinstance(mapped.payload, dict) else {}
        records = payload.get("ir") or (payload.get("payload") or {}).get("ir") or []
        names = [[r.get("kind"), r.get("name")] for r in records]
    return mapped, names


def test_r7_01_id_before_parent_refuses_field_invalid() -> None:
    """R6-01: the id resolves before the parent, so a missing id wins."""
    profile = _neutral_profile()
    recipe = next(r for r in profile["recipes"] if r["id"] == "export-nodes")
    recipe["steps"] = [
        {
            "op": "emit",
            "as": "x",
            "kind": "node",
            "fields": [{"name": "id", "value": {"op": "id", "binding": "root"}}],
            "parent": {
                "op": "case",
                "value": {"op": "read", "binding": "self", "path": "/label/text"},
                "mode": "upper",
                "unicode": "15.0.0",
            },
        }
    ]
    mapped, _ = _export_names(profile)
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "export-field-invalid", mapped.to_json()


def test_r7_02_extra_domain_counter_refuses_ambiguous() -> None:
    """R6-02: an optional name outputId over an unplanned edge domain collects nothing."""
    profile = _neutral_profile()
    recipe = next(r for r in profile["recipes"] if r["id"] == "export-nodes")
    recipe["steps"] = [
        {
            "op": "emit",
            "as": "x",
            "kind": "node",
            "fields": [
                {"name": "id", "value": {"op": "outputId", "binding": "self", "domain": "node"}},
                {"name": "name", "value": {"op": "outputId", "binding": "self", "domain": "edge"}},
            ],
        }
    ]
    mapped, _ = _export_names(profile)
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "profile-ambiguous-binding", mapped.to_json()


def test_r7_03_implicit_parent_uses_planned_page_key() -> None:
    """R6-03: an omitted parent is the planned page-ID key, not the emitted id."""
    profile = _neutral_profile()
    pages = next(r for r in profile["recipes"] if r["id"] == "export-pages")
    pages["steps"][0]["fields"][0]["value"] = {"op": "literal", "value": "custom-page"}
    mapped, _ = _export_names(profile)
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "export-parent-order", mapped.to_json()


def test_r7_04_reachable_cycle_two_hops_gates_render_unsupported() -> None:
    """R6-04: hop-state traversal reaches the source again on a bounded cycle."""
    from bpmn_io.profile import complete_envelope
    from bpmn_io.profile._export import map_export
    from bpmn_io.profile._render import resolve_theme

    profile = _neutral_profile()
    profile["exports"][0]["capabilities"] = [
        {"when": {"op": "true"}, "class": "structural", "losses": []},
        {
            "when": {
                "op": "count",
                "min": 1,
                "select": {
                    "from": "root",
                    "via": "self",
                    "where": {
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
                                    {
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
                                                        "type": "bpmn:Task",
                                                        "mode": "exact",
                                                    },
                                                    {
                                                        "op": "reachable",
                                                        "from": {
                                                            "from": "self",
                                                            "via": "self",
                                                            "where": {"op": "true"},
                                                            "order": "id",
                                                        },
                                                        "to": {
                                                            "from": "self",
                                                            "via": "self",
                                                            "where": {"op": "true"},
                                                            "order": "id",
                                                        },
                                                        "edgeTypes": ["bpmn:SequenceFlow"],
                                                        "minHops": 2,
                                                        "maxHops": 2,
                                                    },
                                                ],
                                            },
                                            "order": "id",
                                            "property": "flowElements",
                                        },
                                    },
                                ],
                            },
                            "order": "id",
                            "property": "rootElements",
                        },
                    },
                    "order": "id",
                },
            },
            "class": "unsupported",
            "losses": [],
        },
    ]
    compiled = _compile(profile)
    assert compiled.status == "ok", compiled.to_json()
    result = compiled.payload
    envelope = complete_envelope(result.identity, _tree_cycle(), [])
    render = resolve_theme(
        result,
        envelope,
        copy.deepcopy(_layout()),
        "plain",
        {"semantic": [], "occurrence": []},
        {"native": [], "bioc": []},
    )
    assert render.status == "ok", render.to_json()
    mapped = map_export(
        result, envelope, copy.deepcopy(_layout()), render.payload, profile["exports"][0]["format"]
    )
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "render-unsupported", mapped.to_json()


def test_r7_05_sem_loss_after_emit_stays_unavailable() -> None:
    """R6-05: a non-self loss after an emit keeps the unavailable result."""
    profile = _neutral_profile()
    recipe = next(r for r in profile["recipes"] if r["id"] == "export-nodes")
    recipe["steps"] = [
        {
            "op": "bind",
            "as": "sem",
            "cardinality": "one",
            "select": {"from": "self", "via": "semantic", "where": {"op": "true"}, "order": "id"},
        },
        {
            "op": "emit",
            "kind": "node",
            "as": "n",
            "fields": [
                {"name": "id", "value": {"op": "outputId", "binding": "self", "domain": "node"}},
                {"name": "name", "value": {"op": "literal", "value": "A"}},
            ],
        },
        {"op": "loss", "target": "sem", "code": "appearance"},
    ]
    recipe["writes"] = [
        {"binding": "self", "mode": "artifact", "path": ""},
        {"binding": "sem", "mode": "report", "path": ""},
    ]
    mapped = _export_result(profile)
    assert mapped.status == "ok", mapped.to_json()
    payload = mapped.payload if isinstance(mapped.payload, dict) else {}
    report = payload.get("report") or {}
    entries = report.get("entries") if isinstance(report, dict) else None
    assert isinstance(entries, list), mapped.to_json()
    assert entries, mapped.to_json()
    loss = next(e for e in entries if e.get("code") == "export-loss/appearance")
    assert loss["result"]["domain"] == "none", mapped.to_json()
    assert loss["result"]["provenance"] == "unavailable", mapped.to_json()


def test_r7_06_label_emit_without_geometry_refuses_field_invalid() -> None:
    """R6-06: a label emit refuses when the occurrence has no label geometry."""
    profile = _neutral_profile()
    recipe = next(r for r in profile["recipes"] if r["id"] == "export-nodes")
    recipe["steps"] = [
        {
            "op": "emit",
            "as": "x",
            "kind": "label",
            "fields": [
                {"name": "id", "value": {"op": "outputId", "binding": "self", "domain": "node"}},
                {"name": "text", "value": {"op": "literal", "value": "Task"}},
            ],
        }
    ]
    mapped, _ = _export_names(profile)
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "export-field-invalid", mapped.to_json()


def test_r7_07_native_same_path_reads_are_not_equal() -> None:
    """R6-07: the native read clones, so two reads of one path are unequal."""
    from bpmn_io.profile import complete_envelope, create_bridge, create_descriptor_context

    profile = _neutral_profile()
    tree = {
        "$type": "bpmn:Definitions",
        "id": "D_1",
        "targetNamespace": "urn:x",
        "rootElements": [
            {
                "$type": "bpmn:Process",
                "id": "P_1",
                "flowElements": [
                    {"$type": "bpmn:Task", "id": "Task_2"},
                    {"$type": "bpmn:ExclusiveGateway", "id": "G_1", "incoming": [], "outgoing": []},
                ],
            }
        ],
    }
    task_entry = next(e for e in profile["ui"] if e.get("id") == "task-create")
    task_entry["when"] = {
        "op": "count",
        "min": 1,
        "select": {
            "from": "root",
            "via": "self",
            "where": {
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
                            {
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
                                                "type": "bpmn:ExclusiveGateway",
                                                "mode": "exact",
                                            },
                                            {
                                                "op": "equal",
                                                "left": {
                                                    "op": "read",
                                                    "binding": "self",
                                                    "path": "/incoming",
                                                },
                                                "right": {
                                                    "op": "read",
                                                    "binding": "self",
                                                    "path": "/outgoing",
                                                },
                                            },
                                        ],
                                    },
                                    "order": "id",
                                    "property": "flowElements",
                                },
                            },
                        ],
                    },
                    "order": "id",
                    "property": "rootElements",
                },
            },
            "order": "id",
        },
    }
    compiled = _compile(profile)
    assert compiled.status == "ok", compiled.to_json()
    ctx = create_descriptor_context([_package()]).payload
    bridge = create_bridge(ctx)
    bridge.set_definitions(complete_envelope(compiled.payload.identity, copy.deepcopy(tree), []))
    act = bridge.activate_business_profile(compiled.payload)
    assert act.status == "ok", act.to_json()
    listed = bridge.list_entries(
        base_revision=bridge.envelope.semantic_revision,
        surface="palette",
        subject="P_1",
        locale="en",
    )
    assert listed.status == "ok", listed.to_json()
    ids = sorted(e["id"] for g in listed.payload.get("groups", []) for e in g["entries"])
    assert "task-create" not in ids, listed.to_json()


def test_r7_08_duplicate_theme_tokens_refuse_symbol() -> None:
    """R6-08: a duplicated plain theme token refuses profile-symbol in both lanes."""
    from bpmn_io.profile import complete_envelope, create_bridge, create_descriptor_context

    profile = _neutral_profile()
    plain = next(t for t in profile["themes"] if t["id"] == "plain")
    plain["tokens"] = [*plain["tokens"], {"name": "fill", "value": "#ffffff"}]
    compiled = _compile(profile)
    assert compiled.status == "refused", compiled.to_json()
    assert compiled.code == "profile-symbol", compiled.to_json()
    free = compiled
    assert free.status == "refused"
    assert free.code == "profile-symbol"
    # Activation lane: metadata-free compile refuses the same way before activation.
    from bpmn_io.profile import compile_profile, load_profile
    from tests.profile_commands import harness as h

    package = _package()
    pins = [{"id": package["id"], "version": package["version"], "sha256": package["sha256"]}]
    loaded = load_profile(
        json.dumps(profile).encode(),
        schema_bytes=h.SCHEMA_BYTES,
        base_bytes=h.BASE_BYTES,
        descriptor_pins=pins,
        asset_bag=dict(h.METRICS_BAG),
    )
    assert loaded.status == "ok", loaded.to_json()
    ctx = create_descriptor_context([package]).payload
    meta_free = compile_profile(loaded.payload)
    assert meta_free.status == "refused", meta_free.to_json()
    assert meta_free.code == "profile-symbol", meta_free.to_json()
    _ = (complete_envelope, create_bridge, ctx)


def test_r7_control_attached_self_loss_uses_artifact_pointer() -> None:
    """Positive control: a self loss after an emit attaches with artifact coordinates."""
    profile = _neutral_profile()
    recipe = next(r for r in profile["recipes"] if r["id"] == "export-nodes")
    recipe["steps"] = [
        {
            "op": "emit",
            "kind": "node",
            "as": "n",
            "fields": [
                {"name": "id", "value": {"op": "outputId", "binding": "self", "domain": "node"}},
                {"name": "name", "value": {"op": "literal", "value": "A"}},
            ],
        },
        {"op": "loss", "target": "self", "code": "appearance"},
    ]
    recipe["writes"] = [
        {"binding": "self", "mode": "artifact", "path": ""},
        {"binding": "self", "mode": "report", "path": ""},
    ]
    mapped = _export_result(profile)
    assert mapped.status == "ok", mapped.to_json()
    payload = mapped.payload if isinstance(mapped.payload, dict) else {}
    report = payload.get("report") or {}
    entries = report.get("entries") if isinstance(report, dict) else None
    assert isinstance(entries, list), mapped.to_json()
    assert entries, mapped.to_json()
    loss = next(e for e in entries if e.get("code") == "export-loss/appearance")
    assert loss["result"]["domain"] == "artifact", mapped.to_json()
    assert loss["result"]["pointer"] == "/ir/1", mapped.to_json()


def test_r7_control_label_with_geometry_emits_names() -> None:
    """Positive control: a label emit with geometry emits page and label rows."""
    from bpmn_io.profile import complete_envelope
    from bpmn_io.profile._export import map_export
    from bpmn_io.profile._render import resolve_theme

    profile = _neutral_profile()
    recipe = next(r for r in profile["recipes"] if r["id"] == "export-nodes")
    recipe["steps"] = [
        {
            "op": "emit",
            "as": "x",
            "kind": "label",
            "fields": [
                {"name": "id", "value": {"op": "outputId", "binding": "self", "domain": "node"}},
                {"name": "text", "value": {"op": "read", "binding": "self", "path": "/label/text"}},
            ],
        }
    ]
    layout = _layout()
    layout["geometry"][0]["label"] = {
        "text": "Task",
        "bounds": {"x": 1500000, "y": 200000, "width": 1000000, "height": 800000},
        "lines": ["Task"],
    }
    compiled = _compile(profile)
    assert compiled.status == "ok", compiled.to_json()
    result = compiled.payload
    envelope = complete_envelope(result.identity, _tree_named_task(), [])
    render = resolve_theme(
        result,
        envelope,
        copy.deepcopy(layout),
        "plain",
        {"semantic": [], "occurrence": []},
        {"native": [], "bioc": []},
    )
    assert render.status == "ok", render.to_json()
    good = map_export(
        result, envelope, copy.deepcopy(layout), render.payload, profile["exports"][0]["format"]
    )
    assert good.status == "ok", good.to_json()
    payload = good.payload if isinstance(good.payload, dict) else {}
    records = payload.get("ir") or (payload.get("payload") or {}).get("ir") or []
    kinds = [[r.get("kind"), r.get("name") if "name" in r else r.get("text")] for r in records]
    assert ["page", "main"] in kinds, good.to_json()
    assert ["label", "Task"] in kinds, good.to_json()
