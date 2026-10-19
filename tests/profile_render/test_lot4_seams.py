"""Lot-4 pure seams: ticks, regions, digests, templates, text (spec §§4.1, 6-8)."""

from __future__ import annotations

import pytest

from tests.profile_render._lot4_harness import MECHANISM


def test_layout_ticks_rounds_once_ties_even() -> None:
    """DI units times 1000 round once, ties to even, negative zero is zero."""
    from bpmn_io.profile._regions import layout_ticks

    result = layout_ticks([0.0005, 0.0015, 0.0025, 0.0035, -0.0005, -0.0015, -0.0025])
    assert result.status == "ok", result.to_json()
    assert result.payload == [0, 2, 2, 4, 0, -2, -2]  # type: ignore[union-attr]


def test_layout_ticks_uses_shortest_decimal_rational() -> None:
    """The conversion uses the decimal form, not the binary64 product."""
    from bpmn_io.profile._regions import layout_ticks

    result = layout_ticks([0.5055, 2.0155])
    assert result.status == "ok", result.to_json()
    assert result.payload == [506, 2016]  # type: ignore[union-attr]


def test_layout_ticks_refuses_non_numbers() -> None:
    """Non-numbers refuse operation-error."""
    from bpmn_io.profile._regions import layout_ticks

    for bad in ("1", None, True, [1]):
        result = layout_ticks([bad])
        assert result.status == "refused", bad
        assert result.code == "operation-error"  # type: ignore[union-attr]


def test_layout_regions_no_anchor_row() -> None:
    """Items without anchors follow contentLeft then previous right plus gap."""
    from bpmn_io.profile._regions import layout_regions

    region = {
        "page": {"x": 0, "y": 0, "width": 600000, "height": 300000},
        "body": {"x": 0, "y": 0, "width": 600000, "height": 100000},
        "tokens": {"headerWidth": 30000, "padding": 10000, "gap": 20000, "minHeight": 80000},
        "items": [
            {
                "elementId": "In_A",
                "occurrenceKey": "In_A_di",
                "object": {"width": 36000, "height": 50000},
            },
            {
                "elementId": "In_B",
                "occurrenceKey": "In_B_di",
                "object": {"width": 36000, "height": 50000},
            },
        ],
    }
    result = layout_regions(region)
    assert result.status == "ok", result.to_json()
    assert result.payload == {  # type: ignore[union-attr]
        "pageBounds": {"x": 0, "y": 0, "width": 600000, "height": 300000},
        "body": {"x": 0, "y": 0, "width": 600000, "height": 100000},
        "items": [
            {
                "elementId": "In_A",
                "occurrenceKey": "In_A_di",
                "bounds": {"x": 40000, "y": 15000, "width": 36000, "height": 50000},
            },
            {
                "elementId": "In_B",
                "occurrenceKey": "In_B_di",
                "bounds": {"x": 96000, "y": 15000, "width": 36000, "height": 50000},
            },
        ],
    }


def test_layout_regions_missing_token() -> None:
    """A missing row token refuses render-region-missing (no hidden default)."""
    from bpmn_io.profile._regions import layout_regions

    region = {
        "page": {"x": 0, "y": 0, "width": 100, "height": 100},
        "body": {"x": 0, "y": 0, "width": 100, "height": 100},
        "tokens": {"headerWidth": 0, "padding": 0, "gap": 0},
        "items": [],
    }
    result = layout_regions(region)
    assert result.status == "refused", result.to_json()
    assert result.code == "render-region-missing"  # type: ignore[union-attr]


def test_layout_regions_empty_keeps_body() -> None:
    """An empty item list leaves the body and the page unchanged."""
    from bpmn_io.profile._regions import layout_regions

    region = {
        "page": {"x": 0, "y": 0, "width": 600000, "height": 300000},
        "body": {"x": 0, "y": 0, "width": 100, "height": 100},
        "tokens": {"headerWidth": 0, "padding": 0, "gap": 0, "minHeight": 80000},
        "items": [],
    }
    result = layout_regions(region)
    assert result.status == "ok", result.to_json()
    assert result.payload == {  # type: ignore[union-attr]
        "pageBounds": {"x": 0, "y": 0, "width": 600000, "height": 300000},
        "body": {"x": 0, "y": 0, "width": 100, "height": 100},
        "items": [],
    }


def test_render_digests_reordered_bags_match() -> None:
    """Reordered override/style records and tokens normalize identically."""
    from bpmn_io.profile._render_digest import render_digests

    def _record(order: str) -> dict:
        semantic = [
            {"semanticId": "Task_A", "tokens": [{"name": "fill", "value": "#000003"}]},
            {
                "semanticId": "Process_1",
                "tokens": [
                    {"name": "fill", "value": "#000001"},
                    {"name": "stroke", "value": "#000002"},
                ],
            },
        ]
        occurrence = [
            {
                "pageId": "A-page",
                "occurrenceKey": "k2",
                "tokens": [{"name": "textColor", "value": "#000004"}],
            },
            {
                "pageId": "Z-page",
                "occurrenceKey": "k1",
                "tokens": [
                    {"name": "arrow", "value": "open"},
                    {"name": "fill", "value": "#000005"},
                ],
            },
        ]
        if order == "reverse":
            semantic.reverse()
            occurrence.reverse()
        return {
            "semanticTree": {
                "$type": "bpmn:Definitions",
                "id": "Definitions_1",
                "rootElements": [{"$type": "bpmn:Process", "id": "Process_1"}],
            },
            "profileIdentity": {
                "mechanismVersion": "1",
                "schemaVersion": "1.0.0",
                "profile": "neutral/1",
                "version": "1.1.0",
                "sha256": "0" * 64,
                "base": {"id": "neutral-base/1", "version": "fixture-2", "sha256": "1" * 64},
                "descriptors": [],
            },
            "bindings": [],
            "descriptorPins": [],
            "layout": {
                "layoutVersion": "1",
                "pages": [
                    {
                        "pageId": "Z-page",
                        "name": "First sheet",
                        "order": 0,
                        "semanticRootId": "Process_1",
                        "bounds": {"x": 0, "y": 0, "width": 1000, "height": 800},
                    }
                ],
                "geometry": [],
            },
            "themeId": "plain",
            "themes": [
                {
                    "id": "plain",
                    "aliases": [],
                    "tokens": [{"name": "fill", "value": "#ffffff"}],
                    "glyphs": [],
                    "metricsResource": "metrics",
                    "geometry": "shared",
                    "syntheticOccurrences": [],
                }
            ],
            "overrides": {"semantic": semantic, "occurrence": occurrence},
            "diStyles": {"native": [], "bioc": []},
            "metrics": [{"id": "metrics", "utf8": "{}"}],
        }

    first = render_digests(_record("forward"))
    second = render_digests(_record("reverse"))
    assert first.status == "ok", first.to_json()
    assert first.to_json() == second.to_json()


def test_render_digests_shape_violations() -> None:
    """Duplicate targets, null tokens and unknown members refuse render-token-invalid."""
    from bpmn_io.profile._render_digest import render_digests

    base: dict = {
        "semanticTree": {"$type": "bpmn:Definitions", "id": "D1"},
        "profileIdentity": {
            "mechanismVersion": "1",
            "schemaVersion": "1.0.0",
            "profile": "p",
            "version": "v",
            "sha256": "0" * 64,
            "base": {"id": "b", "version": "v", "sha256": "1" * 64},
            "descriptors": [],
        },
        "bindings": [],
        "descriptorPins": [],
        "layout": {"layoutVersion": "1", "pages": [], "geometry": []},
        "themeId": "plain",
        "themes": [
            {
                "id": "plain",
                "aliases": [],
                "tokens": [],
                "glyphs": [],
                "metricsResource": "metrics",
                "geometry": "shared",
                "syntheticOccurrences": [],
            }
        ],
        "overrides": {"semantic": [], "occurrence": []},
        "diStyles": {"native": [], "bioc": []},
        "metrics": [],
    }
    import copy

    def _refuse(record: dict) -> None:
        result = render_digests(record)
        assert result.status == "refused", record
        assert result.code == "render-token-invalid"  # type: ignore[union-attr]

    duplicate = copy.deepcopy(base)
    duplicate["diStyles"] = {
        "native": [
            {"pageId": "P", "occurrenceKey": "k", "tokens": []},
            {"pageId": "P", "occurrenceKey": "k", "tokens": []},
        ],
        "bioc": [],
    }
    _refuse(duplicate)
    null_token = copy.deepcopy(base)
    null_token["overrides"] = {
        "semantic": [{"semanticId": "S", "tokens": [{"name": "fill", "value": None}]}],
        "occurrence": [],
    }
    _refuse(null_token)
    unknown_member = copy.deepcopy(base)
    unknown_member["overrides"] = {"semantic": [], "occurrence": [], "extra": []}
    _refuse(unknown_member)


def test_template_geometry_header_band() -> None:
    """Header-band divides at y plus min(headerHeight, h) with no scaling."""
    from bpmn_io.profile._templates import template_geometry

    glyph = {
        "id": "band",
        "kind": "template",
        "viewBox": [0, 0, 100, 80],
        "commands": [],
        "template": "header-band",
        "parameters": [{"name": "headerHeight", "value": 12000}],
    }
    result = template_geometry(glyph, {"x": 100000, "y": 200000, "width": 100000, "height": 80000})
    assert result.status == "ok", result.to_json()
    assert result.payload == {  # type: ignore[union-attr]
        "header": {"x": 100000, "y": 200000, "width": 100000, "height": 12000},
        "body": {"x": 100000, "y": 212000, "width": 100000, "height": 68000},
    }


def test_template_geometry_refusals() -> None:
    """Native glyphs refuse render-unsupported; bad params refuse profile-glyph-shape."""
    from bpmn_io.profile._templates import template_geometry

    native = {
        "id": "task",
        "kind": "native",
        "nativeType": "bpmn:Task",
        "viewBox": [0, 0, 100, 80],
        "commands": [],
    }
    refused = template_geometry(native, {"x": 0, "y": 0, "width": 10, "height": 10})
    assert refused.status == "refused"  # type: ignore[union-attr]
    assert refused.code == "render-unsupported"  # type: ignore[union-attr]

    broken = {
        "id": "band",
        "kind": "template",
        "viewBox": [0, 0, 100, 80],
        "commands": [],
        "template": "header-band",
        "parameters": [],
    }
    refused = template_geometry(broken, {"x": 0, "y": 0, "width": 10, "height": 10})
    assert refused.status == "refused"  # type: ignore[union-attr]
    assert refused.code == "profile-glyph-shape"  # type: ignore[union-attr]


def test_measure_text_fallback_widths() -> None:
    """Scalar widths use spaceAdvance for U+0020 and the fallback otherwise."""
    from bpmn_io.profile._text_metrics import measure_text

    metrics = (MECHANISM / "neutral-metrics.json").read_bytes()
    result = measure_text(metrics, "A B")
    assert result.status == "ok", result.to_json()
    assert result.payload == {"lines": ["A B"], "width": 1500, "height": 1000}  # type: ignore[union-attr]
    empty = measure_text(metrics, "")
    assert empty.status == "ok", empty.to_json()
    assert empty.payload == {"lines": [""], "width": 0, "height": 1000}  # type: ignore[union-attr]


def test_measure_text_multiline_width_is_widest() -> None:
    """Line feed splits lines; the width is the widest line."""
    from bpmn_io.profile._text_metrics import measure_text

    metrics = (MECHANISM / "neutral-metrics.json").read_bytes()
    result = measure_text(metrics, "Ready\nGo")
    assert result.status == "ok", result.to_json()
    assert result.payload == {"lines": ["Ready", "Go"], "width": 3000, "height": 2000}  # type: ignore[union-attr]


def test_view_revision_binds_exactly_seven_members() -> None:
    """view_revision ignores members outside the section 9.2 record."""
    from bpmn_io.profile._render_digest import view_revision

    binding = {
        "semanticRevision": "a",
        "layoutDigest": "b",
        "themeId": "plain",
        "themeDigest": "c",
        "overridesDigest": "d",
        "diStylesDigest": "e",
        "metricsDigest": "f",
    }
    assert view_revision(binding) == view_revision({**binding, "payloadDigest": "x", "pages": []})
    with pytest.raises(KeyError):
        view_revision({"themeId": "plain"})
