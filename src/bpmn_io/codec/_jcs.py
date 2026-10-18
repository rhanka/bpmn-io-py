# Codec-local RFC 8785 (JCS) canonical JSON for the F1 object-size metric.
"""Canonical JSON bytes (contract ``profile-c14n/2``) owned by the codec lane.

Number rendering follows ECMAScript ``Number::toString`` exactly: plain
notation for ``1e-6 <= |n| < 1e21``, exponent notation otherwise, ``-0`` as
``0``. Keys sort in UTF-16 code-unit order with tight separators. This module
is deliberately independent of ``bpmn_io.profile._c14n`` (owned by another
lane); the differential reference is the pinned Node ``canonicalize``
package (see the oracle number-parity test).

Every traversal uses an explicit stack: inputs are untrusted, so no bare
recursion (and no stack overflow) is an accepted outcome. Cycles and
non-JSON values raise ``TypeError``; non-finite numbers raise
``ValueError`` (matching the Node reference, which throws on them).
"""

from __future__ import annotations

import json
import math
from typing import Any, Final

__all__ = ["canonical_bytes", "canonical_size", "canonicalize", "ecma_number"]

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


def _render_atom(value: object) -> str:
    """Render one JSON atom (null, boolean, string or number)."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, float):
        return ecma_number(value)
    if isinstance(value, int):
        return str(value)
    msg = f"not JSON data: {type(value).__name__}"
    raise TypeError(msg)


def _ordered_items(node: dict[Any, Any]) -> list[tuple[Any, Any]]:
    """Return the ``(key, value)`` pairs of ``node`` in UTF-16 key order."""
    return sorted(node.items(), key=lambda item: _utf16_key(item[0]))


def canonicalize(value: Any) -> str:  # noqa: ANN401 - arbitrary JSON data
    """Render the canonical JSON string of ``value`` (RFC 8785 shape)."""
    if isinstance(value, (list, dict)):
        return _render_container(value)
    return _render_atom(value)


def _render_container(root: list[Any] | dict[Any, Any]) -> str:
    """Render one container iteratively (explicit stack, no recursion)."""
    parts: dict[int, str] = {}
    active: set[int] = set()
    stack: list[tuple[bool, Any]] = [(False, root)]  # (assembled?, node)
    while stack:
        assembled, node = stack.pop()
        if assembled:
            active.discard(id(node))
            parts[id(node)] = _assemble(node, parts)
            continue
        if id(node) in active:
            msg = "cyclic data has no canonical form"
            raise TypeError(msg)
        if id(node) in parts:
            continue
        active.add(id(node))
        stack.append((True, node))
        stack.extend(
            (False, child) for child in _child_values(node) if isinstance(child, (list, dict))
        )
    return parts[id(root)]


def _child_values(node: list[Any] | dict[Any, Any]) -> list[Any]:
    """List the raw child values of one container in render order."""
    if isinstance(node, list):
        return list(node)
    return [child for _, child in _ordered_items(node)]


def _assemble(node: list[Any] | dict[Any, Any], parts: dict[int, str]) -> str:
    """Render one container whose children are all rendered (in ``parts``)."""
    if isinstance(node, list):
        return "[" + ",".join(_render_part(child, parts) for child in node) + "]"
    return (
        "{"
        + ",".join(
            json.dumps(key, ensure_ascii=False) + ":" + _render_part(child, parts)
            for key, child in _ordered_items(node)
        )
        + "}"
    )


def _render_part(child: Any, parts: dict[int, str]) -> str:  # noqa: ANN401 - JSON data
    """Render one child: assembled containers from ``parts``, atoms directly."""
    if isinstance(child, (list, dict)):
        return parts[id(child)]
    return _render_atom(child)


def canonical_bytes(value: Any) -> bytes:  # noqa: ANN401 - arbitrary JSON data
    """Return the UTF-8 canonical bytes of ``value`` (the size metric).

    Lone surrogates (which always fail O1 downstream) encode as 3-byte
    sequences so the metric stays total and deterministic.
    """
    return canonicalize(value).encode("utf-8", "surrogatepass")


def canonical_size(value: Any) -> int:  # noqa: ANN401 - arbitrary JSON data
    """Return the exact UTF-8 byte length of the canonical form of ``value``.

    Iterative like :func:`canonicalize` but materializes nothing: only the
    length is accumulated, so measuring an untrusted input never allocates
    the rendering. Callers that only need the size must use this.
    """
    if isinstance(value, (list, dict)):
        return _measure_container(value)
    return len(_render_atom(value).encode("utf-8", "surrogatepass"))


def _measure_container(root: list[Any] | dict[Any, Any]) -> int:
    """Measure one container iteratively (explicit stack, no allocation)."""
    total = 0
    active: set[int] = set()
    stack: list[tuple[bool, Any]] = [(False, root)]  # (closing?, node)
    while stack:
        closing, node = stack.pop()
        if closing:
            active.discard(id(node))
            total += 1  # ']' or '}'
            continue
        if isinstance(node, list):
            if id(node) in active:
                msg = "cyclic data has no canonical form"
                raise TypeError(msg)
            active.add(id(node))
            total += 1 + max(0, len(node) - 1)  # '[' plus commas
            stack.append((True, node))
            stack.extend((False, child) for child in reversed(node))
        elif isinstance(node, dict):
            if id(node) in active:
                msg = "cyclic data has no canonical form"
                raise TypeError(msg)
            active.add(id(node))
            ordered = _ordered_items(node)
            total += 1 + max(0, len(ordered) - 1)  # '{' plus commas
            stack.append((True, node))
            for key, child in reversed(ordered):
                total += len(json.dumps(key, ensure_ascii=False).encode("utf-8", "surrogatepass"))
                total += 1  # ':'
                stack.append((False, child))
        else:
            total += len(_render_atom(node).encode("utf-8", "surrogatepass"))
    return total
