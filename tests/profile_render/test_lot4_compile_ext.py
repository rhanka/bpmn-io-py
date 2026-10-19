"""Lot-4 compile extension: glyphs, token signatures, export fields (spec §8.1).

Each case mirrors one sealed ``render.compile.*`` / ``export.compile.*``
expectation: a single-patch profile variant refuses with the sealed code,
and the valid counterparts compile.
"""

from __future__ import annotations

import copy
import json

from tests.profile_render._lot4_harness import (
    MECHANISM,
    compile_case_profile,
    compile_profile_doc,
    profile_from_ref,
)


def _patched(base: str, patch: list[dict]) -> dict:
    """Materialize one sealed ``{base, patch}`` profile reference."""
    return profile_from_ref({"base": base, "patch": patch})


def _code_of(profile: dict) -> str:
    """Compile one profile and return ``ok`` or the refusal code."""
    result, _, _ = compile_profile_doc(copy.deepcopy(profile))
    if result.status == "ok":
        return "ok"
    return result.code  # type: ignore[union-attr]


def test_glyph_shape_cases() -> None:
    """Glyph viewBox and template parameter violations refuse profile-glyph-shape."""
    cases = {
        "viewbox-zero-width": (
            [{"op": "replace", "path": "/themes/0/glyphs/0/viewBox", "value": [0, 0, 0, 80]}],
            "profile-glyph-shape",
        ),
        "template-param-missing": (
            [
                {
                    "op": "add",
                    "path": "/themes/0/glyphs/-",
                    "value": {
                        "id": "band",
                        "kind": "template",
                        "viewBox": [0, 0, 100, 80],
                        "commands": [],
                        "template": "header-band",
                        "parameters": [],
                    },
                }
            ],
            "profile-glyph-shape",
        ),
        "template-param-duplicate": (
            [
                {
                    "op": "add",
                    "path": "/themes/0/glyphs/-",
                    "value": {
                        "id": "badge",
                        "kind": "template",
                        "viewBox": [0, 0, 100, 80],
                        "commands": [],
                        "template": "attached-badge",
                        "parameters": [
                            {"name": "offsetX", "value": 0},
                            {"name": "offsetX", "value": 1},
                            {"name": "offsetY", "value": 0},
                            {"name": "hideSource", "value": False},
                            {"name": "markerShift", "value": 0},
                        ],
                    },
                }
            ],
            "profile-glyph-shape",
        ),
        "template-param-type": (
            [
                {
                    "op": "add",
                    "path": "/themes/0/glyphs/-",
                    "value": {
                        "id": "fold",
                        "kind": "template",
                        "viewBox": [0, 0, 100, 80],
                        "commands": [],
                        "template": "corner-fold",
                        "parameters": [
                            {"name": "foldRatio", "value": 0.25},
                            {"name": "headerRotation", "value": "90"},
                        ],
                    },
                }
            ],
            "profile-glyph-shape",
        ),
    }
    for name, (patch, want) in cases.items():
        got = _code_of(_patched("neutral-profile.json", patch))
        assert got == want, name


def test_token_signature_cases() -> None:
    """Token violations (duplicate, unknown, mistyped) refuse profile-type."""
    cases = [
        (
            [{"op": "replace", "path": "/themes/0/tokens/0/value", "value": 12}],
            "profile-type",
        ),
        (
            [
                {
                    "op": "add",
                    "path": "/themes/0/tokens/-",
                    "value": {"name": "opacity", "value": 0.5},
                }
            ],
            "profile-type",
        ),
        (
            [{"op": "replace", "path": "/themes/0/tokens/3/value", "value": 1.5}],
            "profile-type",
        ),
        (
            [
                {
                    "op": "add",
                    "path": "/notions/0/renderBindings/0/tokens/-",
                    "value": {"name": "fill", "value": "#ffffff"},
                }
            ],
            "profile-type",
        ),
    ]
    for patch, want in cases:
        got = _code_of(_patched("neutral-profile.json", patch))
        assert got == want, json.dumps(patch)


def test_export_field_cases() -> None:
    """Export-ir/1 field violations refuse profile-export-field."""
    edge_recipe = {
        "id": "export-edges",
        "phase": "export",
        "parameters": [],
        "select": {
            "from": "render",
            "via": "occurrences",
            "where": {
                "op": "equal",
                "left": {"op": "read", "binding": "self", "path": "/emittedType"},
                "right": {"op": "literal", "value": "edge"},
            },
            "order": "page-occurrence",
        },
        "when": {"op": "true"},
        "writes": [{"binding": "self", "path": "", "mode": "artifact"}],
        "steps": [
            {
                "op": "emit",
                "as": "out",
                "kind": "edge",
                "fields": [
                    {
                        "name": "id",
                        "value": {"op": "outputId", "binding": "self", "domain": "edge"},
                    },
                    {"name": "source", "value": {"op": "literal", "value": "e_1"}},
                    {"name": "target", "value": {"op": "literal", "value": "e_2"}},
                    {"name": "fill", "value": {"op": "literal", "value": "#ffffff"}},
                ],
            }
        ],
    }

    def _with_edge(fields: list[dict]) -> dict:
        profile = profile_from_ref({"base": "neutral-profile.json", "patch": []})
        recipe = copy.deepcopy(edge_recipe)
        recipe["steps"][0]["fields"] = fields  # type: ignore[index]
        profile["recipes"].append(recipe)
        return profile

    base_fields = copy.deepcopy(edge_recipe["steps"][0]["fields"])  # type: ignore[index]
    assert _code_of(_with_edge(base_fields)) == "profile-export-field"
    missing_target = [entry for entry in base_fields if entry["name"] != "target"]
    assert _code_of(_with_edge(missing_target)) == "profile-export-field"

    profile = profile_from_ref({"base": "neutral-profile.json", "patch": []})
    profile["recipes"][7]["steps"][0]["fields"].append(
        {"name": "fill", "value": {"op": "literal", "value": 255}}
    )
    assert _code_of(profile) == "profile-export-field"

    profile = profile_from_ref({"base": "neutral-profile.json", "patch": []})
    profile["recipes"][7]["steps"][0]["fields"].append(
        {"name": "fontSize", "value": {"op": "literal", "value": "12"}}
    )
    assert _code_of(profile) == "profile-export-field"


def test_export_record_cases() -> None:
    """Page parents and nonzero origins under non-counter policies refuse profile-type."""
    profile = profile_from_ref({"base": "neutral-profile.json", "patch": []})
    profile["recipes"][6]["steps"][0]["parent"] = {
        "op": "outputId",
        "binding": "self",
        "domain": "page",
    }
    assert _code_of(profile) == "profile-type"

    for policy in ("digest", "native"):
        profile = profile_from_ref({"base": "neutral-profile.json", "patch": []})
        profile["exports"][0]["idPolicy"] = policy
        profile["exports"][0]["counterOrigin"] = 5 if policy == "digest" else 1
        assert _code_of(profile) == "profile-type", policy

    profile = profile_from_ref({"base": "neutral-profile.json", "patch": []})
    profile["exports"][0]["idPolicy"] = "digest"
    assert _code_of(profile) == "ok"


def test_valid_profiles_still_compile() -> None:
    """The sealed ok compile cases keep compiling with the lot-4 checks on."""
    for ref in (
        {"base": "neutral-profile.json", "patch": []},
        {"base": "neutral-grid-profile.json", "patch": []},
    ):
        result, _, _ = compile_case_profile(ref)
        assert result.status == "ok", result.to_json()


def test_registry_from_json_carries_render_tokens() -> None:
    """The neutral registry loads its render-token signatures and region rules."""
    from bpmn_io.profile._render_tokens import registry_from_json

    doc = json.loads((MECHANISM / "neutral-registry.json").read_text(encoding="utf-8"))
    result = registry_from_json(doc)
    assert result.status == "ok", result.to_json()
    registry = result.payload
    assert set(registry.render_tokens) >= {
        "fill",
        "stroke",
        "textColor",
        "fontFamily",
        "fontSize",
        "strokeWidth",
        "fontWeight",
        "dash",
        "arrow",
    }
    want_pattern = "^region\\.[A-Za-z_][A-Za-z0-9_-]*\\.(headerWidth|padding|gap|minHeight)$"
    assert registry.region_token_pattern == want_pattern
    assert registry.region_token_schema == {"type": "integer", "minimum": 0}
    assert "outputId" in registry.signatures


def test_compiled_profile_carries_lot4_extension() -> None:
    """Compiled profiles keep the full JSON, identity, assets and render registry."""
    from bpmn_io.profile._c14n import digest as c14n_digest

    result, profile, _ = compile_case_profile({"base": "neutral-profile.json", "patch": []})
    assert result.status == "ok", result.to_json()
    compiled = result.payload
    assert compiled.profile == profile
    assert compiled.identity == {
        "mechanismVersion": profile["mechanismVersion"],
        "schemaVersion": profile["schemaVersion"],
        "profile": profile["profile"],
        "version": profile["version"],
        "sha256": c14n_digest(profile),
        "base": profile["base"],
        "descriptors": profile["descriptors"],
    }
    assert set(compiled.assets) == {"neutral-metrics"}
    assert set(compiled.render_registry) >= {"fill", "fontFamily", "dash"}


def test_view_revision_matches_digest_formula() -> None:
    """view_revision binds exactly the §9.2 fields through H."""
    from bpmn_io.profile._c14n import digest as c14n_digest
    from bpmn_io.profile._render_digest import view_revision

    binding = {
        "semanticRevision": "a",
        "layoutDigest": "b",
        "themeId": "plain",
        "themeDigest": "c",
        "overridesDigest": "d",
        "diStylesDigest": "e",
        "metricsDigest": "f",
        "extra": "ignored",
    }
    assert view_revision(binding) == c14n_digest(
        {
            "semanticRevision": "a",
            "layoutDigest": "b",
            "themeId": "plain",
            "themeDigest": "c",
            "overridesDigest": "d",
            "diStylesDigest": "e",
            "metricsDigest": "f",
        }
    )
