"""JavaScript semantics helpers for the literal port (EVOL D5).

Implements the specified ECMAScript behaviours the transposed libraries rely on: truthiness,
the ``undefined``/``null`` distinction, ``Math.round`` (ties toward +Infinity),
``Number#toString`` formatting, ``parseInt``/``parseFloat`` leniency, insertion-ordered sets
and ``JSON.stringify`` semantics for the ``json_equal`` test matcher.

Deviations from ECMA-262 are documented on each helper; they only cover inputs the ported
libraries never produce (astronomical integers, exotic unicode whitespace).
"""

from __future__ import annotations

import json
import math
import re
from typing import TYPE_CHECKING, Any, Final, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

__all__ = [
    "UNDEFINED",
    "OrderedSet",
    "UndefinedType",
    "is_truthy",
    "json_stringify",
    "math_round",
    "number_to_string",
    "parse_float",
    "parse_int",
    "strict_equal",
]

#: Matches a leading ``parseFloat`` number: ``Infinity`` or a decimal with optional exponent.
_FLOAT_PREFIX: Final = re.compile(r"[+-]?(?:Infinity|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")

#: Collapses a zero-padded exponent (``1e-07`` → ``1e-7``); Python ``repr`` pads to two
#: digits while ``Number#toString`` and ``JSON.stringify`` use the shortest form.
_EXPONENT_ZERO: Final = re.compile(r"([eE][+-])0+(\d)")


def _normalize_exponent(text: str) -> str:
    """Strip leading zeros from the exponent of a ``repr``-produced number string."""
    return _EXPONENT_ZERO.sub(r"\1\2", text)


class UndefinedType:
    """Sentinel for JavaScript ``undefined``, distinct from ``None`` (``null``)."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "undefined"

    def __bool__(self) -> bool:
        return False

    def __copy__(self) -> UndefinedType:
        return self

    def __deepcopy__(self, _memo: dict[int, Any]) -> UndefinedType:
        return self


#: The single ``undefined`` value; identity-comparable (``value is UNDEFINED``).
UNDEFINED: Final = UndefinedType()


def is_truthy(value: object) -> bool:
    """Return the JavaScript truthiness of ``value``.

    Falsy: ``False``, ``0``/``0.0``, ``""``, ``None`` (``null``), ``UNDEFINED``
    (``undefined``) and ``NaN``. Everything else — including empty containers, which are
    truthy in JS unlike Python — is truthy.
    """
    if value is None or value is UNDEFINED:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, float):
        return not math.isnan(value) and value != 0.0
    if isinstance(value, str):
        return len(value) > 0
    return True


def math_round(value: float) -> float:
    """Return ``Math.round(value)``: fractional ties go toward +Infinity.

    Non-finite inputs (``NaN``, ``±Infinity``) pass through unchanged, as upstream.
    """
    if not math.isfinite(value):
        return value
    return math.floor(value + 0.5)


def number_to_string(value: float) -> str:
    """Return ``Number#toString`` of ``value`` (radix 10).

    ``int`` arguments are accepted through the numeric tower.

    Integral floats render without a decimal point (``100``, not ``100.0``); large and
    tiny magnitudes use exponent notation (``1e+21``, ``1e-7``); ``-0.0`` renders as
    ``"0"``; non-finite values render as ``"NaN"``/``"Infinity"``/``"-Infinity"``.

    Deviation: Python ``int`` has arbitrary precision while JS numbers do not; integers
    beyond float range render exactly here.
    """
    if isinstance(value, bool):
        msg = f"number_to_string() requires int | float, got bool ({value!r})"
        raise TypeError(msg)
    if isinstance(value, int):
        return str(value)
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "Infinity" if value > 0 else "-Infinity"
    if value == 0:
        return "0"
    if value.is_integer() and abs(value) < 1e21:
        return str(int(value))
    return _normalize_exponent(repr(value))


def parse_int(text: str, radix: int | None = None) -> int | float:
    """Return the ``parseInt`` subset used by the ported libraries.

    Strips leading whitespace, consumes an optional sign, resolves the radix (``0x``/``0X``
    prefix → 16 when ``radix`` is ``None`` or ``0``, else 10; an explicit ``16`` also strips
    the prefix), then takes the longest valid digit prefix. Returns ``NaN`` (``float``)
    when no digits follow, or when ``radix`` is outside 2-36.

    Deviation: leading-whitespace detection uses Python's unicode strip instead of the
    ECMA WhiteSpace production (differs only on exotic separators such as U+200B, which
    never occur in the ported inputs); precision beyond 2**53 is kept exact.
    """
    rest = text.lstrip()
    sign = 1
    if rest.startswith(("+", "-")):
        sign = -1 if rest[0] == "-" else 1
        rest = rest[1:]
    base = radix if radix not in (None, 0) else None
    if base is None:
        if rest.startswith(("0x", "0X")):
            rest = rest[2:]
            base = 16
        else:
            base = 10
    elif base == 16 and rest.startswith(("0x", "0X")):
        rest = rest[2:]
    if base < 2 or base > 36:
        return math.nan
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"[:base]
    digits = []
    for char in rest:
        lowered = char.lower()
        if lowered not in alphabet:
            break
        digits.append(lowered)
    if not digits:
        return math.nan
    return sign * int("".join(digits), base)


def strict_equal(left: object, right: object) -> bool:
    """Return JavaScript ``===`` semantics for plain values.

    Numbers (``int`` and ``float`` alike) and strings compare by value; containers
    (``dict``/``list``/``tuple``) compare by identity like JS objects; ``bool``
    never equals a number (``typeof`` differs); ``None`` (``null``) and
    ``UNDEFINED`` (``undefined``) equal only themselves. ``NaN`` never equals,
    including itself.
    """
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if left is None or right is None or left is UNDEFINED or right is UNDEFINED:
        return left is right
    if isinstance(left, (dict, list, tuple)) or isinstance(right, (dict, list, tuple)):
        return left is right
    return bool(left == right)


def parse_float(text: str) -> float:
    """Return the ``parseFloat`` subset used by the ported libraries.

    Strips leading whitespace, then takes the longest valid ``Infinity``/decimal prefix
    (``Infinity`` is case-sensitive, as upstream). Returns ``NaN`` when nothing parses.
    """
    match = _FLOAT_PREFIX.match(text.lstrip())
    if match is None:
        return math.nan
    return float(match.group(0))


T = TypeVar("T")


class OrderedSet(Generic[T]):
    """Insertion-ordered set (the ``Set`` semantics the ported code relies on)."""

    __slots__ = ("_items",)

    def __init__(self, iterable: Iterable[T] | None = None) -> None:
        self._items: dict[T, None] = {}
        if iterable is not None:
            for item in iterable:
                self._items[item] = None

    def add(self, item: T) -> None:
        """Add ``item``; re-adding keeps the original position, as upstream."""
        self._items[item] = None

    def discard(self, item: T) -> None:
        """Remove ``item`` if present; missing items are ignored, as upstream."""
        self._items.pop(item, None)

    def __contains__(self, item: object) -> bool:
        return item in self._items

    def __iter__(self) -> Iterator[T]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({list(self._items)!r})"


def _encode_float(value: float) -> str:
    """Encode a JSON number: non-finite → ``null``, integral → plain, else repr."""
    if not math.isfinite(value):
        return "null"
    if value.is_integer() and abs(value) < 1e21:
        return str(int(value))
    return _normalize_exponent(repr(value))


def json_stringify(value: object) -> str:
    """Return the ``JSON.stringify`` subset backing the ``json_equal`` test matcher.

    Object keys keep insertion order with ``", "``-free separators; ``UNDEFINED`` values
    are skipped in objects and become ``null`` in arrays; non-finite numbers become
    ``null``; ``-0.0`` encodes as ``0``. Non-ASCII strings stay unescaped, as upstream.
    A bare ``UNDEFINED`` raises ``ValueError`` (upstream returns ``undefined`` instead of
    a string, which has no Python equivalent at this boundary).

    Iterative: safe on deeply nested models.
    """
    if value is UNDEFINED:
        msg = "json_stringify() of undefined has no string value"
        raise ValueError(msg)
    parts: list[str] = []
    stack: list[tuple[str, Any, Any]] = [("val", value, None)]
    while stack:
        kind, item, extra = stack.pop()
        if kind == "lit":
            parts.append(item)
        elif kind == "val":
            _encode_value(item, parts, stack)
        elif kind == "arr":
            _encode_array_item(item, parts, stack, first=extra)
        else:  # kind == "dict"
            _encode_dict_item(item, parts, stack, first=extra)
    return "".join(parts)


def _encode_value(value: object, parts: list[str], stack: list[tuple[str, Any, Any]]) -> None:
    """Push the encoding of one plain value."""
    if value is None or value is UNDEFINED:
        parts.append("null")
    elif isinstance(value, bool):
        parts.append("true" if value else "false")
    elif isinstance(value, int):
        parts.append(str(value))
    elif isinstance(value, float):
        parts.append(_encode_float(value))
    elif isinstance(value, str):
        parts.append(json.dumps(value, ensure_ascii=False))
    elif isinstance(value, (list, tuple)):
        parts.append("[")
        stack.append(("arr", iter(value), True))
    elif isinstance(value, dict):
        parts.append("{")
        stack.append(("dict", iter(value.items()), True))
    else:
        msg = f"json_stringify() supports JSON-like values, got {type(value).__name__}"
        raise TypeError(msg)


def _encode_array_item(
    iterator: Iterator[object],
    parts: list[str],
    stack: list[tuple[str, Any, Any]],
    *,
    first: bool,
) -> None:
    """Encode the next array element, or close the array when exhausted."""
    try:
        element = next(iterator)
    except StopIteration:
        parts.append("]")
        return
    if not first:
        parts.append(",")
    stack.append(("arr", iterator, False))
    stack.append(("val", None if element is UNDEFINED else element, None))


def _encode_dict_item(
    iterator: Iterator[tuple[object, object]],
    parts: list[str],
    stack: list[tuple[str, Any, Any]],
    *,
    first: bool,
) -> None:
    """Encode the next object entry, skipping ``UNDEFINED`` values, or close it."""
    try:
        key, val = next(iterator)
    except StopIteration:
        parts.append("}")
        return
    if val is UNDEFINED:
        stack.append(("dict", iterator, first))
        return
    if not first:
        parts.append(",")
    key_text = ("true" if key else "false") if isinstance(key, bool) else str(key)
    stack.append(("dict", iterator, False))
    stack.append(("val", val, None))
    stack.append(("lit", json.dumps(key_text, ensure_ascii=False) + ":", None))
