"""Shared pure layout seams: ticks and region rows (DESIGN R3.3 §§3.1, 9.4).

``layout_ticks`` converts binary64 DI units to integer micro-point ticks
through the exact rational of the shortest round-trip decimal form,
rounded once with ties to even. ``layout_regions`` binds the region row
rule on explicit numbers: exact rationals throughout, one ties-to-even
rounding per output coordinate.
"""

from __future__ import annotations

import math
from decimal import Decimal
from fractions import Fraction
from typing import Any

from bpmn_io.profile._results import PureRefused, PureResult, PureSuccess

__all__ = ["layout_regions", "layout_ticks"]

Json = Any

_MAX_SAFE_INTEGER = 2**53 - 1


def _shortest_fraction(value: float) -> Fraction:
    """Return the exact rational of the shortest round-trip decimal form."""
    if isinstance(value, int):
        return Fraction(value, 1)
    return Fraction(Decimal(repr(value)))


def _round_even(value: Fraction) -> int:
    """Round one exact rational to the nearest integer, ties to even."""
    floor = value.numerator // value.denominator
    remainder = value - floor
    if remainder < Fraction(1, 2):
        return floor
    if remainder > Fraction(1, 2):
        return floor + 1
    return floor if floor % 2 == 0 else floor + 1


def layout_ticks(points: object) -> PureResult:
    """Convert DI units to integer ticks (one roundEven per point)."""
    if not isinstance(points, list):
        return PureRefused(code="operation-error")
    converted: list[int] = []
    for entry in points:
        if isinstance(entry, bool):
            return PureRefused(code="operation-error")
        if isinstance(entry, int) or (isinstance(entry, float) and math.isfinite(entry)):
            converted.append(_round_even(_shortest_fraction(entry) * 1000))
        else:
            return PureRefused(code="operation-error")
    return PureSuccess(payload=converted)


def _finite_fraction(value: object) -> Fraction | None:
    """Project one finite JSON number to its decimal rational (None if not)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Fraction(value, 1)
    if isinstance(value, float) and math.isfinite(value):
        return Fraction(Decimal(repr(value)))
    return None


def _check_bounds(value: object, *, allow_negative_origin: bool) -> dict[str, Fraction] | None:
    """Project one bounds record to fractions (None when malformed)."""
    if not isinstance(value, dict) or set(value.keys()) != {"x", "y", "width", "height"}:
        return None
    out: dict[str, Fraction] = {}
    for key in ("x", "y", "width", "height"):
        fraction = _finite_fraction(value.get(key))
        if fraction is None:
            return None
        out[key] = fraction
    if out["width"] < 0 or out["height"] < 0:
        return None
    if not allow_negative_origin and (out["x"] < 0 or out["y"] < 0):
        return None
    return out


def _check_size(value: object) -> dict[str, Fraction] | None:
    """Project one {width, height} size to fractions (None when malformed)."""
    if not isinstance(value, dict) or set(value.keys()) != {"width", "height"}:
        return None
    out: dict[str, Fraction] = {}
    for key in ("width", "height"):
        fraction = _finite_fraction(value.get(key))
        if fraction is None or fraction < 0:
            return None
        out[key] = fraction
    return out


def _check_tokens(value: object) -> dict[str, int] | str | None:
    """Project the four row tokens (int map, refusal code, or None)."""
    if not isinstance(value, dict):
        return "operation-error"
    names = ("headerWidth", "padding", "gap", "minHeight")
    if any(name not in value for name in names):
        return "render-region-missing"
    if set(value.keys()) != set(names):
        return "operation-error"
    out: dict[str, int] = {}
    for name in names:
        entry = value.get(name)
        if not isinstance(entry, int) or isinstance(entry, bool):
            return "operation-error"
        if entry < 0 or entry > _MAX_SAFE_INTEGER:
            return "operation-error"
        out[name] = entry
    return out


def _check_item(entry: object) -> dict[str, Json] | str | None:  # noqa: PLR0911
    """Project one region item (record, refusal code, or None)."""
    if not isinstance(entry, dict):
        return "operation-error"
    element_id = entry.get("elementId")
    key = entry.get("occurrenceKey")
    if not isinstance(element_id, str) or not isinstance(key, str):
        return "operation-error"
    allowed = {"elementId", "occurrenceKey", "object", "label", "anchor"}
    if set(entry.keys()) - allowed or "object" not in entry:
        return "operation-error"
    size = _check_size(entry.get("object"))
    if size is None:
        return "operation-error"
    label: dict[str, Fraction] | None = None
    if "label" in entry:
        label = _check_size(entry.get("label"))
        if label is None:
            return "operation-error"
    anchor: dict[str, Fraction] | None = None
    if "anchor" in entry:
        anchor = _check_bounds(entry.get("anchor"), allow_negative_origin=True)
        if anchor is None:
            return "operation-error"
    return {
        "elementId": element_id,
        "occurrenceKey": key,
        "object": size,
        "label": label,
        "anchor": anchor,
    }


def _emit_bounds(values: dict[str, Fraction]) -> dict[str, int]:
    """Round one fraction bounds record once, ties to even."""
    return {key: _round_even(values[key]) for key in ("x", "y", "width", "height")}


def layout_regions(region_input: object) -> PureResult:  # noqa: C901, PLR0911, PLR0912, PLR0915
    """Place one region row at the top of the support body."""
    if not isinstance(region_input, dict) or set(region_input.keys()) != {
        "page",
        "body",
        "tokens",
        "items",
    }:
        return PureRefused(code="operation-error")
    page = _check_bounds(region_input.get("page"), allow_negative_origin=True)
    body = _check_bounds(region_input.get("body"), allow_negative_origin=True)
    if page is None or body is None:
        return PureRefused(code="operation-error")
    tokens = _check_tokens(region_input.get("tokens"))
    if not isinstance(tokens, dict):
        return PureRefused(code=tokens or "operation-error")
    raw_items = region_input.get("items")
    if not isinstance(raw_items, list):
        return PureRefused(code="operation-error")
    items: list[dict[str, Json]] = []
    for entry in raw_items:
        projected = _check_item(entry)
        if not isinstance(projected, dict):
            return PureRefused(code=projected or "operation-error")
        items.append(projected)
    if not items:
        return PureSuccess(
            payload={
                "pageBounds": _emit_bounds(page),
                "body": _emit_bounds(body),
                "items": [],
            }
        )
    content_left = body["x"] + tokens["headerWidth"] + tokens["padding"]
    placed: list[dict[str, Fraction]] = []
    for index, item in enumerate(items):
        size = item["object"]
        label = item["label"] or {"width": Fraction(0), "height": Fraction(0)}
        footprint = max(size["width"], label["width"])
        anchor = item["anchor"]
        if anchor is not None:
            desired = anchor["x"] + anchor["width"] / 2 - footprint / 2
        elif index == 0:
            desired = content_left
        else:
            desired = placed[index - 1]["right"] + tokens["gap"]
        left = max(desired, content_left)
        if index > 0:
            left = max(left, placed[index - 1]["right"] + tokens["gap"])
        placed.append(
            {
                "left": left,
                "right": left + footprint,
                "footprint": footprint,
                "width": size["width"],
                "height": size["height"],
                "labelWidth": label["width"],
                "labelHeight": label["height"],
            }
        )
    stacks = [entry["height"] + entry["labelHeight"] for entry in placed]
    row_height = max(Fraction(tokens["minHeight"], 1), max(stacks) + 2 * tokens["padding"])
    half_heights = [entry["height"] / 2 for entry in placed]
    full_heights = [entry["height"] / 2 + entry["labelHeight"] for entry in placed]
    top = max(half_heights)
    bottom = max(full_heights)
    center = body["y"] + max(top, (row_height + top - bottom) / 2)
    out_items: list[dict[str, Json]] = []
    for item, entry in zip(items, placed, strict=True):
        left = entry["left"]
        record: dict[str, Json] = {
            "elementId": item["elementId"],
            "occurrenceKey": item["occurrenceKey"],
            "bounds": _emit_bounds(
                {
                    "x": left + (entry["footprint"] - entry["width"]) / 2,
                    "y": center - entry["height"] / 2,
                    "width": entry["width"],
                    "height": entry["height"],
                }
            ),
        }
        if item["label"] is not None:
            record["labelBounds"] = _emit_bounds(
                {
                    "x": left + (entry["footprint"] - entry["labelWidth"]) / 2,
                    "y": center + entry["height"] / 2,
                    "width": entry["labelWidth"],
                    "height": entry["labelHeight"],
                }
            )
        out_items.append(record)
    last_right = placed[-1]["right"]
    grown_width = max(body["width"], last_right + tokens["padding"] - body["x"])
    grown_height = max(body["height"], row_height, center + bottom - body["y"])
    grown = {"x": body["x"], "y": body["y"], "width": grown_width, "height": grown_height}
    page_right = max(page["x"] + page["width"], grown["x"] + grown["width"])
    page_bottom = max(page["y"] + page["height"], grown["y"] + grown["height"])
    page_origin_x = min(page["x"], grown["x"])
    page_origin_y = min(page["y"], grown["y"])
    page_bounds = {
        "x": page_origin_x,
        "y": page_origin_y,
        "width": page_right - page_origin_x,
        "height": page_bottom - page_origin_y,
    }
    return PureSuccess(
        payload={
            "pageBounds": _emit_bounds(page_bounds),
            "body": _emit_bounds(grown),
            "items": out_items,
        }
    )
