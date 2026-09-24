# Transposed from bpmn-io/moddle@3124e6a lib/types.js (MIT).
"""Built-in type table transposed from moddle ``lib/types.js``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from bpmn_io._js import parse_float, parse_int

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["BUILTINS", "coerce_type", "is_built_in", "is_simple"]

#: Built-in moddle types (``Element`` has no converter, so it is not simple).
BUILTINS: Final = frozenset({"String", "Boolean", "Integer", "Real", "Element"})


def _convert_string(value: object) -> object:
    """Return the string representation (identity, as upstream)."""
    return value


def _convert_boolean(value: object) -> bool:
    """Convert strictly: only ``"true"`` becomes ``True``."""
    return value == "true"


def _convert_integer(value: object) -> int | float:
    """Convert via ``parseInt`` leniency (``NaN`` when nothing parses)."""
    text = value if isinstance(value, str) else str(value)
    return parse_int(text, 10)


def _convert_real(value: object) -> float:
    """Convert via ``parseFloat`` leniency (``NaN`` when nothing parses)."""
    text = value if isinstance(value, str) else str(value)
    return parse_float(text)


#: Converters for built-in types from string representations.
_CONVERTERS: Final[dict[str, Callable[[object], Any]]] = {
    "String": _convert_string,
    "Boolean": _convert_boolean,
    "Integer": _convert_integer,
    "Real": _convert_real,
}


def coerce_type(type_: str, value: object) -> object:
    """Convert ``value`` to its ``type_`` representation (identity when unknown)."""
    converter = _CONVERTERS.get(type_)

    if converter is not None:
        return converter(value)

    return value


def is_built_in(type_: str) -> bool:
    """Return whether ``type_`` is a built-in moddle type."""
    return type_ in BUILTINS


def is_simple(type_: str) -> bool:
    """Return whether ``type_`` is a simple (converter-backed) built-in type."""
    return type_ in _CONVERTERS
