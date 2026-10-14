# Transposed from bpmn-io/moddle-utils@30e00f7 index.js (MIT).
"""Moddle element path utilities transposed from ``@bpmn-io/moddle-utils`` ``index.js``.

Paths are lists of property names and collection indexes, e.g.
``["rootElements", 0, "flowElements", 0]``. ``None`` is JS ``null`` and
``UNDEFINED`` (``bpmn_io._js``) is JS ``undefined``; both are *nil* here.
"""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING, cast

from bpmn_io._js import UNDEFINED, is_truthy, parse_int

if TYPE_CHECKING:
    from bpmn_io.moddle.base import ModdleElement

__all__ = [
    "get_path",
    "path_concat",
    "path_equals",
    "path_parse",
    "path_stringify",
]

#: JS ``Number(...)`` on a path segment: decimal, exponent, hex/octal/binary or ``Infinity``.
_JS_NUMBER: re.Pattern[str] = re.compile(
    r"^[+-]?(?:Infinity|0[xX][0-9a-fA-F]+|0[oO][0-7]+|0[bB][01]+"
    r"|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)$",
)


def _is_nil(value: object) -> bool:
    """JS ``isNil``: ``null`` (``None``) or ``undefined`` (``UNDEFINED``)."""
    return value is None or value is UNDEFINED


def _is_number_like(segment: str) -> bool:
    """JS ``!isNaN(segment)``: the segment coerces to a number via ``Number(...)``."""
    text = segment.strip()
    if text == "":
        return True
    return _JS_NUMBER.match(text) is not None


def get_path(
    moddle_element: ModdleElement | None = None,
    parent_moddle_element: ModdleElement | None = None,
) -> list[str | int] | None:
    """Get the path from ``moddle_element`` and optional parent element, or ``None``."""
    if _is_nil(moddle_element):
        return None

    if moddle_element is parent_moddle_element:
        return []

    path: list[str | int] = []
    element = cast("ModdleElement", moddle_element)

    while True:
        parent = element.parent_

        if not is_truthy(parent):
            if element.instance_of("bpmn:Definitions"):
                break
            return None

        parent_element = cast("ModdleElement", parent)
        path = [*_get_property_name(element, parent_element), *path]

        element = parent_element

        if parent_moddle_element is not None and element is parent_moddle_element:
            break

    return path


def _get_property_name(
    moddle_element: ModdleElement,
    parent_moddle_element: ModdleElement,
) -> list[str | int]:
    """Get the property name (plus index for collections) linking parent to element."""
    for prop in parent_moddle_element.descriptor_.properties:
        value = parent_moddle_element.get(prop.name)
        if prop.is_many:
            if isinstance(value, list) and moddle_element in value:
                return [prop.name, value.index(moddle_element)]
        elif value is moddle_element:
            return [prop.name]

    return []


def path_concat(*paths: object) -> list[str | int] | None:
    """Concatenate path segments (strings, numbers or segment lists); ``None`` if any is nil."""
    concatenated_paths: list[str | int] = []

    for path in paths:
        if _is_nil(path):
            return None

        segments = path if isinstance(path, list) else [path]

        concatenated_paths = [*concatenated_paths, *segments]

    return concatenated_paths


def path_equals(
    a: str | list[str | int] | None,
    b: str | list[str | int] | None,
    separator: str = ".",
) -> bool:
    """Check whether two paths (string or segment form) are equal."""
    if _is_nil(a) or _is_nil(b):
        return False

    if not isinstance(a, str):
        a = path_stringify(a, separator)

    if not isinstance(b, str):
        b = path_stringify(b, separator)

    return a == b


def path_parse(path: str | None, separator: str = ".") -> list[str | int | float] | None:
    """Parse a stringified path; numeric segments become integers (JS ``parseInt``)."""
    if _is_nil(path):
        return None

    assert isinstance(path, str)  # noqa: S101 - narrowed by the nil check above
    return [
        segment if not _is_number_like(segment) else parse_int(segment)
        for segment in path.split(separator)
    ]


def path_stringify(path: list[str | int] | None, separator: str = ".") -> str | None:
    """Stringify a segment path with ``separator``; ``None`` when the path is nil."""
    if _is_nil(path):
        return None

    assert isinstance(path, list)  # noqa: S101 - narrowed by the nil check above
    return separator.join(_js_string(segment) for segment in path)


def _js_string(segment: str | int) -> str:
    """JS ``Array#join`` element conversion for one path segment."""
    if isinstance(segment, float) and math.isnan(segment):
        return "NaN"
    return str(segment)
