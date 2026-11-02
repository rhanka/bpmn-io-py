"""Block-B R8: export emitter transcription witnesses (PY-R6 ruling §5.4).

Public operations only on the neutral lot-5 profile. Every expected value
is the JS value at fec4dae (corpora E/IDP/N/D, PY-R6 ruling §5.4 and §3).
Red on 3f81202, green on the R8 tree.
"""

from __future__ import annotations

import copy
import json
from typing import Any


def _neutral_profile() -> dict[str, Any]:
    from tests.profile_commands import harness as h

    raw = (h.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
    return json.loads(raw.decode("utf-8"))


def _package() -> dict[str, Any]:
    from tests.profile_commands import harness as h

    package = dict(h.DEFAULT_DESCRIPTOR_PIN)
    package["descriptorBytes"] = h.DEFAULT_DESCRIPTOR_BYTES
    return package


def _compile(profile: dict[str, Any]) -> Any:  # noqa: ANN401
    from bpmn_io.profile import compile_profile, create_descriptor_context
    from tests.profile_commands import harness as h

    ctx = create_descriptor_context([_package()]).payload
    return compile_profile(
        _load(profile), descriptor_context=ctx, base=copy.deepcopy(h.BASE_DOCUMENT)
    )


def _load(profile: dict[str, Any]) -> Any:  # noqa: ANN401
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


def _tree_one() -> dict[str, Any]:
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


def _tree_named() -> dict[str, Any]:
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


def _layout_one() -> dict[str, Any]:
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
) -> Any:  # noqa: ANN401
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
        copy.deepcopy(layout or _layout_one()),
        "plain",
        {"semantic": [], "occurrence": []},
        {"native": [], "bioc": []},
    )
    assert render.status == "ok", render.to_json()
    fmt = profile["exports"][0]["format"]
    return map_export(result, envelope, copy.deepcopy(layout or _layout_one()), render.payload, fmt)


def test_r8_n1_planned_set_covers_every_planned_id() -> None:
    """N1: a parent planned via the page key is checked, not only id fields."""
    profile = _neutral_profile()
    pages = next(r for r in profile["recipes"] if r["id"] == "export-pages")
    nodes = next(r for r in profile["recipes"] if r["id"] == "export-nodes")
    pages["steps"][0]["fields"][0]["value"] = {"op": "literal", "value": "custom-page"}
    nodes["steps"][0]["fields"] = [
        {"name": "id", "value": {"op": "outputId", "binding": "self", "domain": "node"}},
        {"name": "name", "value": {"op": "literal", "value": "n"}},
    ]
    profile["exports"][0]["recipes"] = ["export-nodes", "export-pages"]
    mapped = _export_result(profile)
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "export-parent-order", mapped.to_json()


def test_r8_r602_no_outputid_resolved_during_interpretation() -> None:
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
    mapped = _export_result(profile)
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "profile-ambiguous-binding", mapped.to_json()


def test_r8_r601_id_duplicate_parent_before_kind_fields() -> None:
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
    mapped = _export_result(profile)
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "export-field-invalid", mapped.to_json()


def test_r8_n8_layout_page_order_is_numeric() -> None:
    """N8: page orders 2 and 10 are numeric, not UTF-16 text."""
    from bpmn_io.profile._layout import check_layout_record

    layout = _layout_one()
    layout["pages"] = [
        {
            "pageId": "p2",
            "name": "two",
            "order": 2,
            "semanticRootId": "P_1",
            "bounds": {"x": 0, "y": 0, "width": 10, "height": 10},
        },
        {
            "pageId": "p10",
            "name": "ten",
            "order": 10,
            "semanticRootId": "P_1",
            "bounds": {"x": 0, "y": 0, "width": 10, "height": 10},
        },
    ]
    layout["geometry"] = []
    assert check_layout_record(layout) is True


def test_r8_r609_metadata_over_occurrence_is_operation_error() -> None:
    """R6-09: metadata emitted over a semantic occurrence refuses operation-error."""
    profile = _neutral_profile()
    nodes = next(r for r in profile["recipes"] if r["id"] == "export-nodes")
    nodes["steps"] = [
        {
            "op": "emit",
            "as": "x",
            "kind": "metadata",
            "fields": [
                {"name": "name", "value": {"op": "literal", "value": "m"}},
                {"name": "value", "value": {"op": "literal", "value": "v"}},
            ],
        }
    ]
    profile["exports"][0]["recipes"] = ["export-nodes"]
    mapped = _export_result(profile)
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "operation-error", mapped.to_json()


def test_r8_r602_own_key_always_planned() -> None:
    """R6-02 own key: a literal node id still plans its own key (native)."""
    profile = _neutral_profile()
    nodes = next(r for r in profile["recipes"] if r["id"] == "export-nodes")
    nodes["steps"] = [
        {
            "op": "emit",
            "as": "x",
            "kind": "node",
            "fields": [
                {"name": "id", "value": {"op": "literal", "value": "lit-node"}},
                {"name": "name", "value": {"op": "literal", "value": "n"}},
            ],
        }
    ]
    nodes["writes"] = [
        {"binding": "self", "mode": "artifact", "path": ""},
    ]
    profile["exports"][0]["idPolicy"] = "native"
    profile["exports"][0]["recipes"] = ["export-pages", "export-nodes"]
    mapped = _export_result(profile)
    assert mapped.status == "ok", mapped.to_json()
    payload = mapped.payload if isinstance(mapped.payload, dict) else {}
    id_map = payload.get("idMap", []) if isinstance(payload, dict) else []
    assert any(isinstance(row, dict) and row.get("resultId") == "lit-node" for row in id_map), (
        payload
    )


def test_r8_n3_undefined_member_is_profile_json() -> None:
    """N3: a self loss attached to a metadata record refuses profile-json."""
    profile = _neutral_profile()
    pages = next(r for r in profile["recipes"] if r["id"] == "export-pages")
    pages["steps"] = [
        {
            "op": "emit",
            "as": "x",
            "kind": "metadata",
            "fields": [
                {"name": "name", "value": {"op": "literal", "value": "m"}},
                {"name": "value", "value": {"op": "literal", "value": "v"}},
            ],
        },
        {"op": "loss", "target": "self", "code": "appearance"},
    ]
    pages["writes"] = [
        {"binding": "self", "mode": "artifact", "path": ""},
        {"binding": "self", "mode": "report", "path": ""},
    ]
    profile["exports"][0]["recipes"] = ["export-pages"]
    mapped = _export_result(profile)
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "profile-json", mapped.to_json()


def test_r8_n11_node_name_defaults_to_label_text() -> None:
    """N11: a node without a name takes the occurrence label text (Alpha)."""
    profile = _neutral_profile()
    nodes = next(r for r in profile["recipes"] if r["id"] == "export-nodes")
    nodes["steps"] = [
        {
            "op": "emit",
            "as": "node",
            "kind": "node",
            "fields": [
                {"name": "id", "value": {"op": "outputId", "binding": "self", "domain": "node"}},
            ],
        }
    ]
    profile["exports"][0]["recipes"] = ["export-pages", "export-nodes"]
    tree = {
        "$type": "bpmn:Definitions",
        "id": "D_1",
        "targetNamespace": "urn:x",
        "rootElements": [
            {
                "$type": "bpmn:Process",
                "id": "P_1",
                "flowElements": [{"$type": "bpmn:Task", "id": "Task_2", "name": "Alpha"}],
            }
        ],
    }
    layout = {
        "layoutVersion": "1",
        "pages": [
            {
                "pageId": "page-main",
                "name": "main",
                "order": 0,
                "semanticRootId": "P_1",
                "bounds": {"x": 0, "y": 0, "width": 8000000, "height": 4000000},
            }
        ],
        "geometry": [
            {
                "pageId": "page-main",
                "occurrenceKey": "occ:Task_2",
                "semanticId": "Task_2",
                "role": "content",
                "bounds": {"x": 1500000, "y": 200000, "width": 1000000, "height": 800000},
                "label": {
                    "text": "Alpha",
                    "bounds": {"x": 1500000, "y": 1000000, "width": 1000000, "height": 200000},
                    "lines": ["Alpha"],
                },
            }
        ],
    }
    mapped = _export_result(profile, tree=tree, layout=layout)
    assert mapped.status == "ok", mapped.to_json()
    payload = mapped.payload if isinstance(mapped.payload, dict) else {}
    ir = payload.get("ir", [])
    nodes_out = [r for r in ir if isinstance(r, dict) and r.get("kind") == "node"]
    assert nodes_out, payload
    assert nodes_out[0].get("name") == "Alpha", payload


def test_r8_r605_self_loss_attaches_to_same_iteration_record() -> None:
    """R6-05: a second self loss after two records attaches to the earlier one."""
    profile = _neutral_profile()
    nodes = next(r for r in profile["recipes"] if r["id"] == "export-nodes")
    nodes["steps"] = [
        {
            "op": "emit",
            "as": "a",
            "kind": "node",
            "fields": [
                {"name": "id", "value": {"op": "outputId", "binding": "self", "domain": "node"}},
                {"name": "name", "value": {"op": "literal", "value": "n"}},
            ],
        },
        {"op": "loss", "target": "self", "code": "appearance"},
        {"op": "loss", "target": "self", "code": "navigation"},
    ]
    nodes["writes"] = [
        {"binding": "self", "mode": "artifact", "path": ""},
        {"binding": "self", "mode": "report", "path": ""},
    ]
    profile["exports"][0]["recipes"] = ["export-pages", "export-nodes"]
    mapped = _export_result(profile)
    assert mapped.status == "ok", mapped.to_json()
    payload = mapped.payload if isinstance(mapped.payload, dict) else {}
    report = payload.get("report", {}) if isinstance(payload, dict) else {}
    entries = report.get("entries", []) if isinstance(report, dict) else []
    codes = sorted(e.get("code") for e in entries if isinstance(e, dict))
    assert "export-loss/appearance" in codes, payload
    assert "export-loss/navigation" in codes, payload


def test_r8_r603_implicit_parent_is_planned_page_key() -> None:
    """R6-03: a custom page id leaves the node parent planned-but-unemitted."""
    profile = _neutral_profile()
    pages = next(r for r in profile["recipes"] if r["id"] == "export-pages")
    pages["steps"][0]["fields"][0]["value"] = {"op": "literal", "value": "custom-page"}
    mapped = _export_result(profile)
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "export-parent-order", mapped.to_json()


def test_r8_n10_crlf_writer_options_are_admitted() -> None:
    """N10: CRLF writer options serialize with export-format-unsupported only on violation."""
    from bpmn_io.profile._serialize import _check_writer_options

    assert (
        _check_writer_options(
            {
                "version": "1.0",
                "encoding": "UTF-8",
                "newline": "CRLF",
                "indent": 0,
                "compression": "none",
                "attributeOrder": ["id", "value"],
                "emptyElement": "short",
            }
        )
        is None
    )
    assert (
        _check_writer_options(
            {
                "version": "",
                "encoding": "UTF-8",
                "newline": "LF",
                "indent": 0,
                "compression": "none",
                "attributeOrder": [],
                "emptyElement": "short",
            }
        )
        == "export-format-unsupported"
    )


def test_r8_n10_sparx_has_no_serializer() -> None:
    """N10: the second adapter format refuses export-format-unsupported at serialize."""
    from bpmn_io.profile import complete_envelope
    from bpmn_io.profile._export import map_export
    from bpmn_io.profile._render import resolve_theme
    from bpmn_io.profile._serialize import serialize_prepared

    profile = _neutral_profile()
    profile["exports"][0]["format"] = "sparx"
    compiled = _compile(profile)
    assert compiled.status == "ok", compiled.to_json()
    result = compiled.payload
    envelope = complete_envelope(result.identity, _tree_one(), [])
    render = resolve_theme(
        result,
        envelope,
        copy.deepcopy(_layout_one()),
        "plain",
        {"semantic": [], "occurrence": []},
        {"native": [], "bioc": []},
    )
    assert render.status == "ok", render.to_json()
    mapped = map_export(result, envelope, copy.deepcopy(_layout_one()), render.payload, "sparx")
    assert mapped.status == "ok", mapped.to_json()
    writer = dict(profile["exports"][0]["serializer"])
    out = serialize_prepared(copy.deepcopy(mapped.payload), writer)
    assert out.status == "refused", out.to_json()
    assert out.code == "export-format-unsupported", out.to_json()


def test_r8_n7_exports_metadata_is_inert() -> None:
    """N7: exports[].metadata emits no record (owner item O-9)."""
    profile = _neutral_profile()
    profile["exports"][0]["metadata"] = [{"name": "m", "value": "v"}]
    mapped = _export_result(profile)
    assert mapped.status == "ok", mapped.to_json()
    payload = mapped.payload if isinstance(mapped.payload, dict) else {}
    ir = payload.get("ir", []) if isinstance(payload, dict) else []
    assert [r for r in ir if isinstance(r, dict) and r.get("kind") == "metadata"] == []


def test_r8_r606_label_needs_occurrence_geometry() -> None:
    """R6-06: a label record without occurrence label geometry refuses."""
    profile = _neutral_profile()
    nodes = next(r for r in profile["recipes"] if r["id"] == "export-nodes")
    nodes["steps"] = [
        {
            "op": "emit",
            "as": "x",
            "kind": "label",
            "fields": [
                {"name": "id", "value": {"op": "outputId", "binding": "self", "domain": "label"}},
                {"name": "text", "value": {"op": "literal", "value": "t"}},
            ],
        }
    ]
    profile["exports"][0]["recipes"] = ["export-pages", "export-nodes"]
    mapped = _export_result(profile)
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "export-field-invalid", mapped.to_json()


def test_r8_n2_metadata_parent_is_unvalidated() -> None:
    """N2: a metadata parent literal is kept when it is a string (missing)."""
    profile = _neutral_profile()
    pages = next(r for r in profile["recipes"] if r["id"] == "export-pages")
    pages["steps"] = [
        {
            "op": "emit",
            "as": "page",
            "kind": "page",
            "fields": [
                {"name": "id", "value": {"op": "outputId", "binding": "self", "domain": "page"}},
                {"name": "name", "value": {"op": "read", "binding": "self", "path": "/name"}},
            ],
        },
        {
            "op": "emit",
            "as": "meta",
            "kind": "metadata",
            "fields": [
                {"name": "name", "value": {"op": "literal", "value": "A"}},
                {"name": "value", "value": {"op": "literal", "value": "V"}},
            ],
            "parent": {"op": "literal", "value": "missing"},
        },
    ]
    pages["writes"] = [
        {"binding": "self", "mode": "artifact", "path": ""},
    ]
    profile["exports"][0]["recipes"] = ["export-pages", "export-nodes"]
    mapped = _export_result(profile)
    assert mapped.status == "ok", mapped.to_json()
    payload = mapped.payload if isinstance(mapped.payload, dict) else {}
    ir = payload.get("ir", []) if isinstance(payload, dict) else []
    metas = [r for r in ir if isinstance(r, dict) and r.get("kind") == "metadata"]
    assert metas, payload
    assert metas[0].get("parent") == "missing", payload


def test_r8_n4_non_object_self_is_operation_error() -> None:
    """N4: a recipe select over self via self refuses operation-error."""
    profile = _neutral_profile()
    nodes = next(r for r in profile["recipes"] if r["id"] == "export-nodes")
    nodes["select"] = {"from": "self", "via": "self", "where": {"op": "true"}, "order": "id"}
    profile["exports"][0]["recipes"] = ["export-nodes"]
    mapped = _export_result(profile)
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "operation-error", mapped.to_json()


def test_r8_n13_record_copies_come_from_emission_self() -> None:
    """N13: a page emitted over an occurrence takes the occurrence bounds."""
    profile = _neutral_profile()
    profile["recipes"].append(
        {
            "id": "export-kx",
            "phase": "export",
            "parameters": [],
            "select": {
                "from": "render",
                "via": "occurrences",
                "where": {
                    "op": "equal",
                    "left": {"op": "read", "binding": "self", "path": "/emittedType"},
                    "right": {"op": "literal", "value": "node"},
                },
                "order": "page-occurrence",
            },
            "when": {"op": "true"},
            "writes": [{"binding": "self", "mode": "artifact", "path": ""}],
            "steps": [
                {
                    "op": "emit",
                    "as": "k",
                    "kind": "page",
                    "fields": [
                        {"name": "id", "value": {"op": "literal", "value": "kx"}},
                        {"name": "name", "value": {"op": "literal", "value": "P"}},
                    ],
                }
            ],
        }
    )
    profile["exports"][0]["recipes"] = ["export-pages", "export-nodes", "export-kx"]
    mapped = _export_result(profile)
    assert mapped.status == "ok", mapped.to_json()
    payload = mapped.payload if isinstance(mapped.payload, dict) else {}
    ir = payload.get("ir", []) if isinstance(payload, dict) else []
    kx = next((r for r in ir if isinstance(r, dict) and r.get("id") == "kx"), {})
    want = {"x": 1500000, "y": 200000, "width": 1000000, "height": 800000}
    assert kx.get("bounds") == want, payload


def test_r8_n6_capability_scan_stops_at_first_unsupported() -> None:
    """N6: first unsupported occurrence wins before a later throwing one."""
    profile = _neutral_profile()
    profile["exports"][0]["capabilities"] = [
        {
            "when": {
                "op": "count",
                "min": 1,
                "select": {
                    "from": "self",
                    "via": "semantic",
                    "where": {
                        "op": "present",
                        "value": {"op": "read", "binding": "self", "path": "/name"},
                    },
                    "order": "id",
                },
            },
            "class": "unsupported",
            "losses": [],
        },
        {
            "when": {
                "op": "count",
                "min": 1,
                "select": {
                    "from": "self",
                    "via": "semantic",
                    "where": {
                        "op": "present",
                        "value": {
                            "op": "case",
                            "value": {"op": "read", "binding": "self", "path": "/name"},
                            "mode": "upper",
                            "unicode": "15.0.0",
                        },
                    },
                    "order": "id",
                },
            },
            "class": "structural",
            "losses": [],
        },
    ]
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
                    {"$type": "bpmn:Task", "id": "Task_3", "name": "Beta"},
                ],
            }
        ],
    }
    layout = {
        "layoutVersion": "1",
        "pages": [
            {
                "pageId": "page-main",
                "name": "main",
                "order": 0,
                "semanticRootId": "P_1",
                "bounds": {"x": 0, "y": 0, "width": 8000000, "height": 4000000},
            }
        ],
        "geometry": [
            {
                "pageId": "page-main",
                "occurrenceKey": "k1",
                "semanticId": "Task_3",
                "role": "content",
                "bounds": {"x": 1000000, "y": 200000, "width": 1000000, "height": 800000},
                "label": {
                    "text": "Beta",
                    "bounds": {"x": 1000000, "y": 1000000, "width": 1000000, "height": 200000},
                    "lines": ["Beta"],
                },
            },
            {
                "pageId": "page-main",
                "occurrenceKey": "k2",
                "semanticId": "Task_2",
                "role": "content",
                "bounds": {"x": 3000000, "y": 200000, "width": 1000000, "height": 800000},
            },
        ],
    }
    mapped = _export_result(profile, tree=tree, layout=layout)
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "render-unsupported", mapped.to_json()


def test_r8_n12_entry_order_includes_result_coordinates() -> None:
    """N12: entries sort /ir/10 before /ir/8 (result.pointer text order)."""
    from bpmn_io.profile._export import _map_entry_sort_key, _short_entry_sort_key
    from bpmn_io.profile._results import ReportEntry, make_coordinate

    def _entry(pointer: str) -> ReportEntry:
        return ReportEntry(
            code="export-loss/metadata",
            severity="warn",
            classification="loss",
            stage="export",
            rule_id="adapter",
            message_key="export.loss.metadata",
            disposition="mapped",
            source=make_coordinate("none", None, None, "unavailable"),
            result=make_coordinate("artifact", pointer, None, "exact"),
            before_present=False,
            after_present=False,
            page_id="p",
            occurrence_key=None,
            emitted_type=None,
            loss_class="metadata",
        )

    ordered = sorted([_entry("/ir/8"), _entry("/ir/10")], key=_map_entry_sort_key)
    assert [e.result.pointer for e in ordered] == ["/ir/10", "/ir/8"]
    stable = sorted(ordered, key=_short_entry_sort_key)
    assert [e.result.pointer for e in stable] == ["/ir/10", "/ir/8"]


def test_r8_n9_counter_page_order_is_numeric() -> None:
    """N9: counter ids sort pages 2 before 10 (numeric, not text)."""
    from bpmn_io.profile._export_ir import plan_ids

    plan = {
        "policy": "counter",
        "counterOrigin": 0,
        "pages": [
            {"pageId": "p10", "order": 10},
            {"pageId": "p2", "order": 2},
            {"pageId": "p3", "order": 3},
        ],
        "requests": [
            {"pageId": "p10", "domain": "page"},
            {"pageId": "p2", "domain": "page"},
            {"pageId": "p3", "domain": "page"},
        ],
    }
    out = plan_ids(plan)
    assert out.status == "ok", out.to_json()
    ids = out.payload["ids"] if isinstance(out.payload, dict) else []
    assert [(r["pageId"], r["id"]) for r in ids] == [
        ("p2", "e_0"),
        ("p3", "e_1"),
        ("p10", "e_2"),
    ], out.to_json()


def test_r8_n14_plan_ids_seam_transcription() -> None:
    """N14: page requests need no key; malformed inputs refuse export-id-ambiguous."""
    from bpmn_io.profile._export_ir import plan_ids

    ok_page = plan_ids(
        {"policy": "counter", "counterOrigin": 0, "requests": [{"pageId": "p1", "domain": "page"}]}
    )
    assert ok_page.status == "ok", ok_page.to_json()
    bad_origin = plan_ids({"policy": "counter", "counterOrigin": -1, "requests": []})
    # Negative safe integers are accepted (JS allows any safe integer).
    assert bad_origin.status == "ok", bad_origin.to_json()
    bad_request = plan_ids(
        {"policy": "counter", "counterOrigin": 0, "requests": [{"pageId": "p1", "domain": "nope"}]}
    )
    assert bad_request.status == "refused", bad_request.to_json()
    assert bad_request.code == "export-id-ambiguous", bad_request.to_json()
    bad_shape = plan_ids({"policy": "counter", "counterOrigin": 0, "requests": {}})
    assert bad_shape.status == "refused", bad_shape.to_json()
    assert bad_shape.code == "operation-error", bad_shape.to_json()


def _tree_cycle() -> dict[str, Any]:
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


def test_r8_r604_reachable_uses_hop_states() -> None:
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
        copy.deepcopy(_layout_one()),
        "plain",
        {"semantic": [], "occurrence": []},
        {"native": [], "bioc": []},
    )
    assert render.status == "ok", render.to_json()
    fmt = profile["exports"][0]["format"]
    mapped = map_export(result, envelope, copy.deepcopy(_layout_one()), render.payload, fmt)
    assert mapped.status == "refused", mapped.to_json()
    assert mapped.code == "render-unsupported", mapped.to_json()


def test_r8_r607_native_equal_rejects_structured_values() -> None:
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


def test_r8_r608_duplicate_theme_tokens_refuse_symbol() -> None:
    """R6-08: duplicate theme token names refuse profile-symbol at the theme position."""
    profile = _neutral_profile()
    plain = next(t for t in profile["themes"] if t["id"] == "plain")
    plain["tokens"] = [*plain["tokens"], {"name": "fill", "value": "#ffffff"}]
    compiled = _compile(profile)
    assert compiled.status == "refused", compiled.to_json()
    assert compiled.code == "profile-symbol", compiled.to_json()
