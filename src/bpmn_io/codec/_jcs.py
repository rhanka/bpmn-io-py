# Codec-local RFC 8785 (JCS) canonical JSON for the F1 object-size metric.
"""Canonical JSON bytes (contract ``profile-c14n/2``) owned by the codec lane.

Number rendering follows ECMAScript ``Number::toString`` exactly: plain
notation for ``1e-6 <= |n| < 1e21``, exponent notation otherwise, ``-0`` as
``0``. Keys sort in UTF-16 code-unit order with tight separators. This module
is deliberately independent of ``bpmn_io.profile._c14n`` (owned by another
lane); the differential reference is the pinned Node ``canonicalize``
package (see the oracle number-parity test).
"""

from __future__ import annotations

import json
import math
from typing import Any, Final

__all__ = ["canonical_bytes", "canonicalize", "ecma_number"]

#: Magnitude window rendered without an exponent (ECMAScript ``Number::toString``).
_PLAIN_MIN: Final = 1e-6
_PLAIN_MAX: Final = 1e21


def _utf16_key(text: str) -> bytes:
    """Return the UTF-16 code-unit sort key of ``text`` (contract order)."""
    return text.encode("utf-16-be", "surrogatepass")


def _split(magnitude: float) -> tuple[str, int]:
    """Split the shortest repr of ``magnitude`` into significant digits and scale.

    Returns ``(digits, scale)`` with ``value == int(digits) * 10**scale`` and
    no leading or trailing zeros in ``digits``.
    """
    head, _, exp_text = repr(magnitude).partition("e")
    exponent = int(exp_text) if exp_text else 0
    int_part, _, frac_part = head.partition(".")
    digits = (int_part + frac_part).lstrip("0")
    scale = exponent - len(frac_part)
    stripped = digits.rstrip("0")
    scale += len(digits) - len(stripped)
    return stripped, scale


def _plain(magnitude: float) -> str:
    """Render ``magnitude`` (in the plain window) without an exponent."""
    digits, scale = _split(magnitude)
    if scale >= 0:
        return digits + "0" * scale
    point = len(digits) + scale
    if point > 0:
        return digits[:point] + "." + digits[point:]
    if point == 0:
        return "0." + digits
    return "0." + "0" * (-point) + digits


def _exponent(magnitude: float) -> str:
    """Render ``magnitude`` (outside the plain window) with an exponent."""
    digits, scale = _split(magnitude)
    exp = len(digits) - 1 + scale
    mantissa = digits[0] if len(digits) == 1 else digits[0] + "." + digits[1:]
    sign = "+" if exp >= 0 else "-"
    return f"{mantissa}e{sign}{abs(exp)}"


def ecma_number(value: float) -> str:
    """Render one finite float exactly like ECMAScript ``Number::toString``."""
    if not math.isfinite(value):
        msg = "non-finite numbers have no canonical form"
        raise ValueError(msg)
    if value == 0:
        return "0"
    prefix = "-" if value < 0 else ""
    magnitude = -value if value < 0 else value
    if _PLAIN_MIN <= magnitude < _PLAIN_MAX:
        return prefix + _plain(magnitude)
    return prefix + _exponent(magnitude)


def _render_scalar(value: object) -> str:
    """Render one JSON scalar (strings quoted, numbers via ECMAScript)."""
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, float):
        return ecma_number(value)
    return str(value)


def canonicalize(value: Any) -> str:  # noqa: ANN401 - arbitrary JSON data
    """Render the canonical JSON string of ``value`` (RFC 8785 shape)."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (str, int, float)):
        return _render_scalar(value)
    if isinstance(value, list):
        return "[" + ",".join(canonicalize(entry) for entry in value) + "]"
    if isinstance(value, dict):
        ordered = sorted(value.items(), key=lambda item: _utf16_key(item[0]))
        return (
            "{"
            + ",".join(
                json.dumps(key, ensure_ascii=False) + ":" + canonicalize(entry)
                for key, entry in ordered
            )
            + "}"
        )
    msg = f"not JSON data: {type(value).__name__}"
    raise TypeError(msg)


def canonical_bytes(value: Any) -> bytes:  # noqa: ANN401 - arbitrary JSON data
    """Return the UTF-8 canonical bytes of ``value`` (the size metric).

    Lone surrogates (which always fail O1 downstream) encode as 3-byte
    sequences so the metric stays total and deterministic.
    """
    return canonicalize(value).encode("utf-8", "surrogatepass")
