"""Lot-4 theme resolution and switch check (spec §§9.4, 9.5, 14)."""

from __future__ import annotations

from tests.profile_render._lot4_harness import compile_case_profile


def _compiled(ref: dict) -> object:
    """Compile one case profile, asserting success."""
    result, _, _ = compile_case_profile(ref)
    assert result.status == "ok", result.to_json()
    return result.payload


def test_switch_paint_only_keeps_shared_geometry() -> None:
    """A paint-only switch keeps the shared geometry."""
    from bpmn_io.profile._themes import check_theme_switch

    compiled = _compiled({"base": "neutral-profile.json", "patch": []})
    _ = compiled
    profile_patch = [
        {
            "op": "add",
            "path": "/themes/-",
            "value": {
                "id": "dim",
                "aliases": [],
                "tokens": [{"name": "fill", "value": "#f4f4f4"}],
                "glyphs": [],
                "metricsResource": "neutral-metrics",
                "geometry": "shared",
                "fallback": "plain",
                "syntheticOccurrences": [],
            },
        }
    ]
    result, _, _ = compile_case_profile({"base": "neutral-profile.json", "patch": profile_patch})
    assert result.status == "ok", result.to_json()
    switched = check_theme_switch(result.payload, "plain", "dim")
    assert switched.status == "ok", switched.to_json()
    assert switched.payload == {"relayoutRequired": False}  # type: ignore[union-attr]


def test_switch_region_token_differs_conflicts() -> None:
    """Shared themes with different region tokens refuse theme-geometry-conflict."""
    from bpmn_io.profile._themes import check_theme_switch

    profile_patch = [
        {
            "op": "add",
            "path": "/themes/-",
            "value": {
                "id": "dense",
                "aliases": [],
                "tokens": [
                    {"name": "fill", "value": "#ffffff"},
                    {"name": "stroke", "value": "#000000"},
                    {"name": "region.content.headerWidth", "value": 0},
                    {"name": "region.content.padding", "value": 4},
                    {"name": "region.content.gap", "value": 8},
                    {"name": "region.content.minHeight", "value": 40},
                ],
                "glyphs": [],
                "metricsResource": "neutral-metrics",
                "geometry": "shared",
                "syntheticOccurrences": [],
            },
        }
    ]
    result, _, _ = compile_case_profile({"base": "neutral-profile.json", "patch": profile_patch})
    assert result.status == "ok", result.to_json()
    switched = check_theme_switch(result.payload, "plain", "dense")
    assert switched.status == "refused", switched.to_json()
    assert switched.code == "theme-geometry-conflict"  # type: ignore[union-attr]


def test_switch_unknown_theme_is_stale() -> None:
    """An unknown theme id is an unresolved input."""
    from bpmn_io.profile._themes import check_theme_switch

    compiled = _compiled({"base": "neutral-profile.json", "patch": []})
    switched = check_theme_switch(compiled, "plain", "no-such-theme")
    assert switched.status == "refused", switched.to_json()
    assert switched.code == "render-stale"  # type: ignore[union-attr]


def test_switch_own_geometry_stays_gated() -> None:
    """A geometry:theme target stays disabled while the policy is not approved."""
    from bpmn_io.profile._themes import check_theme_switch

    profile_patch = [
        {
            "op": "add",
            "path": "/themes/-",
            "value": {
                "id": "owned",
                "aliases": [],
                "tokens": [{"name": "fill", "value": "#ffffff"}],
                "glyphs": [],
                "metricsResource": "neutral-metrics",
                "geometry": "theme",
                "syntheticOccurrences": [],
            },
        }
    ]
    result, _, _ = compile_case_profile({"base": "neutral-profile.json", "patch": profile_patch})
    assert result.status == "ok", result.to_json()
    switched = check_theme_switch(result.payload, "plain", "owned")
    assert switched.status == "refused", switched.to_json()
    assert switched.code == "profile-open"  # type: ignore[union-attr]
