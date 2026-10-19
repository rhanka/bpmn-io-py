"""Lot-4 compiler first-items: reference order and capability scope (DESIGN R3.3).

Tests-first for the two block-A defects the lot-4 seals found:
- ``via: reference`` with ``order: page-occurrence`` from an occurrence
  binding must compile (DESIGN §2.2).
- capability ``when`` predicates must see ``render``, ``page`` and
  ``semantic`` bindings (DESIGN §10.2).
"""

from __future__ import annotations

import copy

from tests.profile_render._lot4_harness import compile_profile_doc, profile_from_ref


def test_reference_from_occurrence_accepts_page_occurrence_order() -> None:
    """A reference traversal from an occurrence binding takes page-occurrence order."""
    profile = profile_from_ref({"base": "neutral-profile.json", "patch": []})
    recipe = {
        "id": "export-occ-refs",
        "phase": "export",
        "parameters": [],
        "select": {
            "from": "render",
            "via": "occurrences",
            "where": {"op": "true"},
            "order": "page-occurrence",
        },
        "when": {"op": "true"},
        "writes": [{"binding": "self", "path": "", "mode": "artifact"}],
        "steps": [
            {
                "op": "bind",
                "select": {
                    "from": "self",
                    "via": "reference",
                    "property": "targetOccurrence",
                    "where": {"op": "true"},
                    "order": "page-occurrence",
                },
                "as": "target",
                "cardinality": "one",
            },
            {
                "op": "emit",
                "as": "node",
                "kind": "node",
                "fields": [
                    {
                        "name": "id",
                        "value": {"op": "outputId", "binding": "self", "domain": "node"},
                    }
                ],
            },
        ],
    }
    profile["recipes"].append(recipe)
    profile["exports"][0]["recipes"].append("export-occ-refs")
    result, _, _ = compile_profile_doc(copy.deepcopy(profile))
    assert result.status == "ok", result.to_json()


def test_count_reads_select_like_schema_and_evaluator() -> None:
    """A `count` predicate carries its selector under `select` (lot-3 B1).

    The schema and the evaluator read `select`; the compiler must accept
    it too, otherwise every neutral-lot4 `count` refuses `profile-type`.
    """
    from bpmn_io.profile._evaluate import evaluate_predicate, make_read_context

    profile = profile_from_ref({"base": "neutral-profile.json", "patch": []})
    count = {
        "op": "count",
        "min": 0,
        "max": 0,
        "select": {
            "from": "self",
            "via": "children",
            "property": "flowElements",
            "where": {"op": "true"},
            "order": "id",
        },
    }
    profile["exports"][0]["capabilities"].append(
        {"when": count, "class": "structural", "losses": []}
    )
    result, _, _ = compile_profile_doc(copy.deepcopy(profile))
    assert result.status == "ok", result.to_json()
    tree = {
        "$type": "bpmn:Definitions",
        "id": "Definitions_1",
        "rootElements": [
            {
                "$type": "bpmn:Process",
                "id": "Process_1",
                "flowElements": [{"$type": "bpmn:Task", "id": "Task_1"}],
            }
        ],
    }
    context = make_read_context(tree)
    process = tree["rootElements"][0]
    assert evaluate_predicate(count, context, {"root": tree, "self": process}).payload is False
    assert (
        evaluate_predicate(
            count, context, {"root": tree, "self": {"$type": "bpmn:Process", "id": "Empty"}}
        ).payload
        is True
    )


def test_ensure_registers_its_alias_for_later_steps() -> None:
    """An `ensure ... as:` alias scopes later steps (lot-3 B3/B4).

    The neutral-lot4 `ensure-supports` recipe binds `main` in an
    `ensure` step and writes it in a later `assignRef`; the compiler
    must scope the alias instead of refusing `profile-symbol`. Full
    `ensure` field checks stay with lot 3.
    """
    profile = profile_from_ref({"base": "neutral-profile.json", "patch": []})
    recipe = {
        "id": "export-ensure-alias",
        "phase": "normalize",
        "parameters": [],
        "select": {
            "from": "root",
            "via": "all",
            "where": {"op": "true"},
            "order": "id",
        },
        "when": {"op": "true"},
        # CR-06: declared writes equal the step demands exactly (each
        # ensure demands its create plus the envelope bindings channel).
        "writes": [
            {"binding": "envelope", "path": "/bindings", "mode": "binding"},
            {"binding": "root", "path": "/rootElements", "mode": "create"},
            {"binding": "collaboration", "path": "/participants", "mode": "create"},
        ],
        "steps": [
            {
                "op": "ensure",
                "as": "collaboration",
                "type": "bpmn:Collaboration",
                "parent": "root",
                "property": "rootElements",
                "owner": "self",
                "role": "collaboration",
                "ownerId": {"op": "id", "binding": "root"},
                "slot": "collaboration",
                "key": {"op": "id", "binding": "self"},
                "fields": [{"name": "name", "value": {"op": "literal", "value": "collaboration"}}],
            },
            {
                "op": "ensure",
                "as": "main",
                "type": "bpmn:Participant",
                "parent": "collaboration",
                "property": "participants",
                "owner": "self",
                "role": "main-participant",
                "ownerId": {"op": "id", "binding": "self"},
                "slot": "main-participant",
                "key": {"op": "literal", "value": "main-participant"},
                "fields": [
                    {"name": "name", "value": {"op": "literal", "value": "main-participant"}}
                ],
            },
            {
                "op": "bind",
                "as": "head",
                "select": {
                    "from": "main",
                    "via": "self",
                    "where": {"op": "true"},
                    "order": "id",
                },
                "cardinality": "one",
            },
        ],
    }
    profile["recipes"].append(recipe)
    result, _, _ = compile_profile_doc(copy.deepcopy(profile))
    assert result.status == "ok", result.to_json()


def test_capability_when_sees_render_page_and_semantic() -> None:
    """A capability predicate may read the render, page and semantic bindings."""
    profile = profile_from_ref({"base": "neutral-profile.json", "patch": []})
    capability = {
        "when": {
            "op": "all",
            "args": [
                {"op": "present", "value": {"op": "read", "binding": "render", "path": "/name"}},
                {"op": "present", "value": {"op": "read", "binding": "page", "path": "/name"}},
                {
                    "op": "present",
                    "value": {"op": "read", "binding": "semantic", "path": "/name"},
                },
            ],
        },
        "class": "structural",
        "losses": [],
    }
    profile["exports"][0]["capabilities"].append(capability)
    result, _, _ = compile_profile_doc(copy.deepcopy(profile))
    assert result.status == "ok", result.to_json()
