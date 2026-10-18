# DESIGN R3.3 §3.1 (profile-c14n/2): canonical JSON and digests for lint data.
"""Canonical JSON (``profile-c14n/2``) and digests for the lint bridge.

Only the lint bridge inputs need hashing here (flattened setting arrays,
``{phase, readinessPolicy, settings}`` records): JSON objects with string
keys and scalar values. The implementation still follows the full
``profile-c14n/2`` rule so later lots can reuse it: UTF-16 code-unit key
order, no insignificant whitespace, UTF-8 without BOM, ECMAScript
shortest-round-trip number rendering, ``-0`` as ``0``, JSON escaping and no
Unicode normalization. Arrays keep order.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

__all__ = ["digest", "dumps_jcs", "render_number", "utf16_key"]


def utf16_key(value: str) -> bytes:
    """Return the UTF-16 code-unit sort key of ``value`` (big-endian bytes).

    Byte comparison of UTF-16BE encodings equals code-unit comparison
    (fixed two-byte units, most significant byte first). ``surrogatepass``
    keeps lone surrogates orderable instead of raising; such inputs are
    refused by earlier validation layers, never hashed here.
    """
    return value.encode("utf-16-be", errors="surrogatepass")


def render_number(value: object) -> str:
    """Render ``value`` with ECMAScript ``Number::toString`` semantics.

    Integral values (including integral floats and ``-0``) render as plain
    digits below 1e21 and in single-digit mantissa exponent form at or
    above it; fractional values use the shortest round-trip digits with
    the ``profile-c14n/2`` plain/fraction/exponent thresholds. NaN and
    infinities are refused: they have no canonical form.
    """
    if isinstance(value, bool):
        msg = f"booleans are not numbers: {value!r}"
        raise TypeError(msg)
    if isinstance(value, int):
        return _render_integer(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            msg = f"non-finite numbers have no canonical form: {value!r}"
            raise ValueError(msg)
        if value == 0:
            return "0"
        return _render_fractional(value)
    msg = f"not a number: {value!r}"
    raise TypeError(msg)


def _render_integer(value: int) -> str:
    """Render an integral value per the ECMAScript plain/exponent boundary."""
    magnitude = abs(value)
    if magnitude < 10**21:
        return str(value)
    digits = str(magnitude)
    exponent = len(digits) - 1
    rest = digits[1:].rstrip("0") if len(digits) > 1 else ""
    mantissa = digits[0] if not rest else digits[0] + "." + rest
    sign = "-" if value < 0 else ""
    return f"{sign}{mantissa}e+{exponent}"


def _render_fractional(value: float) -> str:
    """Render a fractional float with the shortest round-trip digits."""
    sign = "-" if value < 0 else ""
    text = repr(abs(value))
    mantissa, separator, exponent_text = text.partition("e")
    if not separator:
        mantissa, separator, exponent_text = text.partition("E")
    exponent = int(exponent_text) if separator else 0
    point = mantissa.index(".") if "." in mantissa else len(mantissa)
    # Shortest digits never end in zero, except fixed forms like ``100.0``:
    # strip those (keeping the position) so ``100.0`` renders ``100``.
    digits = mantissa.replace(".", "").rstrip("0") or "0"
    # value = int(digits) * 10**(position - len(digits)).
    return _format_decimal(sign, digits, exponent + point)


def _format_decimal(sign: str, digits: str, position: int) -> str:
    """Format ``int(digits) * 10**(position - len(digits))`` per the thresholds."""
    width = len(digits)
    if width <= position <= 21:
        body = digits + "0" * (position - width)
    elif 0 < position <= 21:
        body = digits[:position] + "." + digits[position:]
    elif -6 < position <= 0:
        body = "0." + "0" * (-position) + digits
    else:
        rest = digits[1:] if len(digits) > 1 else ""
        mantissa = digits[0] if not rest else digits[0] + "." + rest
        marker = "+" if position - 1 >= 0 else ""
        body = f"{mantissa}e{marker}{position - 1}"
    return sign + body


def _normalize(value: Any) -> Any:  # noqa: ANN401 - JSON-dynamic input
    """Map JSON values to their canonical rendering inputs.

    Containers map recursively; scalars map through :func:`_normalize_scalar`.
    """
    if isinstance(value, dict):
        return {key: _normalize(entry) for key, entry in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(entry) for entry in value]
    return _normalize_scalar(value)


def _normalize_scalar(value: Any) -> Any:  # noqa: ANN401 - JSON-dynamic input
    """Map one scalar to its canonical rendering input.

    Integral floats become integers (``1.0`` canonicalizes to ``1``) and
    ``-0`` becomes ``0``; booleans are never numbers despite subclassing.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        if value == 0:
            return 0
        if value.is_integer():
            return int(value)
    return value


def dumps_jcs(value: Any) -> str:  # noqa: ANN401 - JSON-dynamic input
    """Dump ``value`` as canonical JSON (``profile-c14n/2``, ASCII-safe subset).

    Object keys sort in UTF-16 code-unit order; separators carry no
    insignificant whitespace; strings keep UTF-8 output without BOM or
    normalization (``ensure_ascii=False``).
    """
    normalized = _normalize(value)
    if isinstance(normalized, dict):
        keys = sorted(normalized.keys(), key=utf16_key)
        inner = ",".join(
            json.dumps(key, ensure_ascii=False) + ":" + dumps_jcs(normalized[key]) for key in keys
        )
        return "{" + inner + "}"
    if isinstance(normalized, (list, tuple)):
        return "[" + ",".join(dumps_jcs(entry) for entry in normalized) + "]"
    if isinstance(normalized, (int, float)) and not isinstance(normalized, bool):
        return render_number(normalized)
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def digest(value: Any) -> str:  # noqa: ANN401 - JSON-dynamic input
    """Return ``H(value)``: lowercase hex SHA-256 over UTF-8 JCS bytes."""
    return hashlib.sha256(dumps_jcs(value).encode("utf-8")).hexdigest()
