"""Glyph shape checks and template geometry (DESIGN R3.3 §9.3).

Compile-time checks (CR-09 subset): every glyph ``viewBox`` needs a
positive width and height; template parameters must be exactly the closed
signature below. ``template_geometry`` binds the four closed templates on
exact rationals with a single ties-to-even rounding at output.
"""

from __future__ import annotations

import math
from decimal import Decimal
from fractions import Fraction
from typing import Any

from bpmn_io.profile._results import PureRefused, PureResult, PureSuccess

__all__ = ["check_glyph", "template_geometry"]

Json = Any

MAX_SAFE_INTEGER = 2**53 - 1

#: Closed template parameter signatures (name to value predicate id).
_TEMPLATE_PARAMS: dict[str, dict[str, str]] = {
    "header-band": {"headerHeight": "nonneg_int"},
    "corner-fold": {"foldRatio": "ratio", "headerRotation": "rotation"},
    "attached-badge": {
        "offsetX": "safe_int",
        "offsetY": "safe_int",
        "hideSource": "bool",
        "markerShift": "safe_int",
    },
    "band-stripe": {"stripeWidth": "nonneg_int"},
}


def _is_safe_int(value: object) -> bool:
    """Return whether ``value`` is a non-bool integer in the safe range."""
    return isinstance(value, int) and not isinstance(value, bool) and abs(value) <= MAX_SAFE_INTEGER


def _check_param_value(kind: str, value: object) -> bool:  # noqa: PLR0911
    """Check one template parameter value against its declared kind."""
    if kind == "nonneg_int":
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and 0 <= value <= MAX_SAFE_INTEGER
        )
    if kind == "safe_int":
        return _is_safe_int(value)
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "ratio":
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            number = float(value)
        elif isinstance(value, float):
            number = value
        else:
            return False
        return math.isfinite(number) and 0 <= number <= 0.5
    if kind == "rotation":
        return isinstance(value, int) and not isinstance(value, bool) and value in (0, 90, 270)
    return False


def check_glyph(glyph: object) -> str | None:  # noqa: C901, PLR0911
    """Check one glyph record (viewBox, template params); refusal or ``None``."""
    if not isinstance(glyph, dict):
        return "profile-glyph-shape"
    view_box = glyph.get("viewBox")
    if (
        not isinstance(view_box, list)
        or len(view_box) != 4
        or not all(
            isinstance(entry, (int, float)) and not isinstance(entry, bool) and math.isfinite(entry)
            for entry in view_box
        )
    ):
        return "profile-glyph-shape"
    if not (view_box[2] > 0 and view_box[3] > 0):
        return "profile-glyph-shape"
    if glyph.get("kind") != "template":
        return None
    signature = _TEMPLATE_PARAMS.get(str(glyph.get("template")))
    if signature is None:
        return "profile-glyph-shape"
    parameters = glyph.get("parameters")
    if not isinstance(parameters, list):
        return "profile-glyph-shape"
    seen: set[str] = set()
    for entry in parameters:
        if not isinstance(entry, dict):
            return "profile-glyph-shape"
        name = entry.get("name")
        if not isinstance(name, str) or name in seen or name not in signature:
            return "profile-glyph-shape"
        seen.add(name)
        if "value" not in entry or not _check_param_value(signature[name], entry.get("value")):
            return "profile-glyph-shape"
    if set(seen) != set(signature):
        return "profile-glyph-shape"
    return None


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


def _check_bounds(bounds: object) -> dict[str, int] | None:
    """Project one integer bounds record (None when malformed)."""
    if not isinstance(bounds, dict):
        return None
    out: dict[str, int] = {}
    for key in ("x", "y", "width", "height"):
        entry = bounds.get(key)
        if not _is_safe_int(entry):
            return None
        out[key] = int(entry)  # type: ignore[arg-type]
    if out["width"] < 0 or out["height"] < 0:
        return None
    return out


def _param(glyph: dict[str, Json], name: str) -> Json:
    """Read one template parameter value by name (None when absent)."""
    for entry in glyph.get("parameters", []):
        if isinstance(entry, dict) and entry.get("name") == name:
            return entry.get("value")
    return None


def template_geometry(  # noqa: C901, PLR0911
    glyph: object,
    bounds: object,
    *,
    label_bounds: object = None,
    badge_size: object = None,
) -> PureResult:
    """Compute the geometry payload of one template glyph instance."""
    if not isinstance(glyph, dict) or glyph.get("kind") != "template":
        return PureRefused(code="render-unsupported")
    if check_glyph(glyph) is not None:
        return PureRefused(code="profile-glyph-shape")
    shape = _check_bounds(bounds)
    if shape is None:
        return PureRefused(code="profile-glyph-shape")
    template = str(glyph.get("template"))
    x, y, width, height = shape["x"], shape["y"], shape["width"], shape["height"]
    if template == "header-band":
        header_height = int(_param(glyph, "headerHeight"))
        cut = min(header_height, height)
        return PureSuccess(
            payload={
                "header": {"x": x, "y": y, "width": width, "height": cut},
                "body": {"x": x, "y": y + cut, "width": width, "height": height - cut},
            }
        )
    if template == "corner-fold":
        ratio = _shortest_fraction(_param(glyph, "foldRatio"))
        fold = _round_even(min(Fraction(width, 1), Fraction(height, 1)) * ratio)
        payload: dict[str, Json] = {
            "fold": fold,
            "foldPath": [
                {"x": x + width - fold, "y": y},
                {"x": x + width - fold, "y": y + fold},
                {"x": x + width, "y": y + fold},
            ],
        }
        if label_bounds is not None:
            label = _check_bounds(label_bounds)
            if label is None:
                return PureRefused(code="profile-glyph-shape")
            center = (
                _round_even(Fraction(label["x"], 1) + Fraction(label["width"], 2)),
                _round_even(Fraction(label["y"], 1) + Fraction(label["height"], 2)),
            )
            payload["labelRotation"] = {
                "angle": int(_param(glyph, "headerRotation")),
                "center": {"x": center[0], "y": center[1]},
            }
        return PureSuccess(payload=payload)
    if template == "band-stripe":
        stripe_width = int(_param(glyph, "stripeWidth"))
        stripe = {"x": x, "y": y, "width": min(stripe_width, width), "height": height}
        return PureSuccess(payload={"stripe": stripe})
    if template == "attached-badge":
        if not isinstance(badge_size, dict):
            return PureRefused(code="profile-glyph-shape")
        size_width = badge_size.get("width")
        size_height = badge_size.get("height")
        if not _is_safe_int(size_width) or not _is_safe_int(size_height):
            return PureRefused(code="profile-glyph-shape")
        offset_x = int(_param(glyph, "offsetX"))
        offset_y = int(_param(glyph, "offsetY"))
        return PureSuccess(
            payload={
                "badge": {
                    "x": x + offset_x,
                    "y": y + height + offset_y,
                    "width": int(size_width),  # type: ignore[arg-type]
                    "height": int(size_height),  # type: ignore[arg-type]
                },
                "markerShift": int(_param(glyph, "markerShift")),
                "hideSource": bool(_param(glyph, "hideSource")),
            }
        )
    return PureRefused(code="profile-glyph-shape")
