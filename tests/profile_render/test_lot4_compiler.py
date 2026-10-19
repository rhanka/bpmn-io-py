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
