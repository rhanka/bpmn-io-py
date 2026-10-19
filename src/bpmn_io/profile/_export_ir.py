"""Export-ir/1 field vocabulary and compile-time emit checks (DESIGN §10.2).

Field names, required fields and literal value types per record kind;
``counter``/``digest``/``native`` ID allocation over the planning pass.
"""

from __future__ import annotations

import math
from typing import Any

__all__ = ["check_emit", "check_export_record"]

Json = Any

#: Optional string fields per record kind (DESIGN §10.2 field vocabulary).
_STRING_FIELDS: dict[str, frozenset[str]] = {
    "page": frozenset(),
    "node": frozenset({"name", "shape", "fill", "stroke", "textColor", "fontFamily"}),
    "edge": frozenset({"name", "stroke", "dash", "arrow"}),
    "label": frozenset(),
    "metadata": frozenset(),
}

#: Optional numeric fields per record kind.
_NUMBER_FIELDS: dict[str, frozenset[str]] = {
    "page": frozenset(),
    "node": frozenset({"fontSize", "strokeWidth"}),
    "edge": frozenset({"strokeWidth"}),
    "label": frozenset(),
    "metadata": frozenset(),
}

#: Required fields per record kind.
_REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    "page": frozenset({"id", "name"}),
    "node": frozenset({"id"}),
    "edge": frozenset({"id", "source", "target"}),
    "label": frozenset({"id", "text"}),
    "metadata": frozenset({"name", "value"}),
}

_ID_FIELD = "id"


def _vocabulary(kind: str) -> set[str]:
    """Return every admittable field name for one record kind."""
    names = set(_REQUIRED_FIELDS[kind])
    names.update(_STRING_FIELDS[kind])
    names.update(_NUMBER_FIELDS[kind])
    return names


def _check_literal_type(kind: str, name: str, value: dict[str, Json]) -> bool:
    """Check one literal emit value against its declared field type.

    Only the §10.2 declared optional node/edge fields carry a compile-time
    type (strings vs numbers); id, endpoints, texts and metadata values
    accept any value AST and evaluate at map time.
    """
    if not isinstance(value, dict) or value.get("op") != "literal":
        return True
    literal = value.get("value")
    if name in _NUMBER_FIELDS[kind]:
        if isinstance(literal, bool):
            return False
        if isinstance(literal, int):
            return True
        return isinstance(literal, float) and math.isfinite(literal)
    if name in _STRING_FIELDS[kind]:
        return isinstance(literal, str)
    return True


def _check_emit_field(kind: str, entry: object, vocabulary: set[str], seen: set[str]) -> str | None:
    """Check one emit field entry (name, duplicate, literal type)."""
    if not isinstance(entry, dict):
        return "profile-export-field"
    name = entry.get("name")
    if not isinstance(name, str) or name in seen or name not in vocabulary:
        return "profile-export-field"
    seen.add(name)
    value = entry.get("value")
    if name == _ID_FIELD and not isinstance(value, dict):
        return "profile-export-field"
    if isinstance(value, dict) and not _check_literal_type(kind, name, value):
        return "profile-export-field"
    return None


def check_emit(step: object) -> str | None:  # noqa: PLR0911
    """Check one emit step (field vocabulary, duplicates, literals).

    Returns ``profile-export-field`` for vocabulary violations,
    ``profile-type`` for a page parent, else ``None``.
    """
    if not isinstance(step, dict):
        return "profile-export-field"
    kind = step.get("kind")
    if kind not in _REQUIRED_FIELDS:
        return "profile-export-field"
    if kind == "page" and step.get("parent") is not None:
        return "profile-type"
    fields = step.get("fields")
    if not isinstance(fields, list):
        return "profile-export-field"
    name = str(kind)
    vocabulary = _vocabulary(name)
    seen: set[str] = set()
    for entry in fields:
        code = _check_emit_field(name, entry, vocabulary, seen)
        if code is not None:
            return code
    if not _REQUIRED_FIELDS[name] <= seen:
        return "profile-export-field"
    return None


def check_export_record(export: object) -> str | None:
    """Check one exports[] record (counter-origin policy); refusal or ``None``."""
    if not isinstance(export, dict):
        return "profile-type"
    policy = export.get("idPolicy")
    origin = export.get("counterOrigin")
    if (
        policy != "counter"
        and isinstance(origin, (int, float))
        and not isinstance(origin, bool)
        and origin != 0
    ):
        return "profile-type"
    return None
