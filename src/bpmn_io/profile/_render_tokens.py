"""Render-token signatures, registry loading and bag normalization (DESIGN §9.3).

Token names and value shapes come from the registry ``renderTokens``
signatures with the generic DESIGN §9.3 table as the fallback; region
geometry tokens (``region.<key>.(headerWidth|padding|gap|minHeight)``)
validate through the registry region pattern. Overrides/1 and DiStyles/1
records normalize by UTF-16 order for digesting.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import math
import re
from typing import TYPE_CHECKING, Any

from bpmn_io.profile._results import PureRefused, PureResult, PureSuccess

if TYPE_CHECKING:
    from bpmn_io.profile._compiler import RegistrySet

__all__ = [
    "MAX_SAFE_INTEGER",
    "normalize_di_styles",
    "normalize_overrides",
    "registry_from_json",
    "validate_bags",
    "validate_token_list",
]

#: Largest integral value admitted outside string patterns (JSON safe range).
MAX_SAFE_INTEGER = 2**53 - 1

#: Generic region-token pattern (DESIGN §9.3) when the registry pins none.
GENERIC_REGION_PATTERN = r"^region\.[A-Za-z_][A-Za-z0-9_-]*\.(headerWidth|padding|gap|minHeight)$"

#: Fixed generic signatures (DESIGN §9.3) used with the default registry.
_GENERIC_COLORS = frozenset({"fill", "stroke", "textColor"})
_GENERIC_NUMBERS = frozenset({"fontSize", "strokeWidth"})
_GENERIC_ENUMS = {
    "fontWeight": frozenset({"normal", "bold"}),
    "arrow": frozenset({"none", "open", "filled", "hollow-triangle"}),
}
_COLOR_PATTERN = r"^#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?$"

Json = Any


def _is_safe_integer(value: object) -> bool:
    """Return whether ``value`` is a non-bool integral number in safe range."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return abs(value) <= MAX_SAFE_INTEGER
    if isinstance(value, float):
        return value.is_integer() and math.isfinite(value) and abs(value) <= MAX_SAFE_INTEGER
    return False


def _is_finite_number(value: object) -> bool:
    """Return whether ``value`` is a non-bool finite number."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value)


def _match_full(pattern: str, value: object) -> bool:
    """Full-match one string value against ``pattern`` (never partial)."""
    if not isinstance(value, str):
        return False
    try:
        return re.fullmatch(pattern, value) is not None
    except re.error:
        return False


def _check_schema_type(declared: object, value: Json) -> bool:
    """Check one token value against a schema ``type`` member."""
    if declared == "string":
        return isinstance(value, str)
    if declared == "number":
        return _is_finite_number(value)
    if declared == "integer":
        return _is_safe_integer(value)
    if declared == "boolean":
        return isinstance(value, bool)
    return declared is None


def _check_schema_facets(schema: dict[str, Json], value: Json) -> bool:
    """Check one token value against schema pattern/enum/minimum/range."""
    pattern = schema.get("pattern")
    if pattern is not None and not _match_full(str(pattern), value):
        return False
    enum = schema.get("enum")
    if enum is not None and (not isinstance(enum, list) or value not in enum):
        return False
    minimum = schema.get("minimum")
    if minimum is not None and (
        not _is_finite_number(value)
        or not _is_finite_number(minimum)
        or float(value) < float(minimum)
    ):
        return False
    declared = schema.get("type")
    return not (
        declared in ("number", "integer")
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        and float(value).is_integer()
        and abs(float(value)) > MAX_SAFE_INTEGER
    )


def _check_schema_value(schema: object, value: Json) -> bool:
    """Check one token value against a registry render-token schema."""
    if not isinstance(schema, dict):
        return False
    declared = schema.get("type")
    return _check_schema_type(declared, value) and _check_schema_facets(schema, value)


def _check_generic_value(name: str, value: Json) -> bool:
    """Check one token value against the generic DESIGN §9.3 signatures."""
    if name in _GENERIC_COLORS:
        return _match_full(_COLOR_PATTERN, value)
    if name in _GENERIC_NUMBERS:
        if not _is_finite_number(value):
            return False
        number = float(value)
        return not (number < 0 or (number.is_integer() and abs(number) > MAX_SAFE_INTEGER))
    if name in _GENERIC_ENUMS:
        return isinstance(value, str) and value in _GENERIC_ENUMS[name]
    return False


def _region_names(registry: RegistrySet) -> str:
    """Return the active region-token pattern (registry pin or generic)."""
    if registry.region_token_pattern:
        return registry.region_token_pattern
    return GENERIC_REGION_PATTERN


def check_token_value(name: str, value: Json, registry: RegistrySet) -> bool:
    """Return whether one token value is admitted (name resolved inside)."""
    if not isinstance(name, str) or not name:
        return False
    if value is None:
        return False
    signatures = registry.render_tokens
    if name in signatures:
        schema = signatures[name]
        return _check_schema_value(schema if isinstance(schema, dict) else {}, value)
    try:
        matched = re.fullmatch(_region_names(registry), name) is not None
    except re.error:
        matched = False
    if matched:
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and 0 <= value <= MAX_SAFE_INTEGER
        )
    if not signatures:
        return _check_generic_value(name, value)
    return False


def validate_token_list(tokens: object, registry: RegistrySet) -> str | None:
    """Validate one token list; return a refusal code or ``None``.

    Unknown names, wrong values and duplicate names refuse. The caller
    maps the ``profile-type`` code (compile time) or ``render-token-invalid``
    (runtime bags) onto the result.
    """
    if not isinstance(tokens, list):
        return "profile-type"
    seen: set[str] = set()
    for entry in tokens:
        if not isinstance(entry, dict):
            return "profile-type"
        name = entry.get("name")
        if not isinstance(name, str) or name in seen:
            return "profile-type"
        seen.add(name)
        if "value" not in entry or not check_token_value(name, entry.get("value"), registry):
            return "profile-type"
    return None


def _sorted_tokens(tokens: list[dict[str, Json]]) -> list[dict[str, Json]]:
    """Sort one token list by UTF-16 name (projection to name/value)."""
    return sorted(
        ({"name": entry["name"], "value": entry["value"]} for entry in tokens),
        key=lambda item: str(item["name"]).encode("utf-16-be"),
    )


def _normalize_occurrence_bag(  # noqa: C901, PLR0911
    records: object,
) -> list[dict[str, Json]] | None:
    """Normalize one occurrence-target bag (None when malformed)."""
    if not isinstance(records, list):
        return None
    normalized: list[dict[str, Json]] = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        if not isinstance(record, dict):
            return None
        page_id = record.get("pageId")
        key = record.get("occurrenceKey")
        tokens = record.get("tokens")
        if (
            not isinstance(page_id, str)
            or not isinstance(key, str)
            or set(record.keys()) != {"pageId", "occurrenceKey", "tokens"}
        ):
            return None
        if (page_id, key) in seen:
            return None
        seen.add((page_id, key))
        if not isinstance(tokens, list):
            return None
        names: set[str] = set()
        for entry in tokens:
            if not isinstance(entry, dict) or set(entry.keys()) != {"name", "value"}:
                return None
            if not isinstance(entry.get("name"), str) or entry.get("name") in names:
                return None
            if entry.get("value") is None:
                return None
            names.add(str(entry.get("name")))
        normalized.append(
            {"pageId": page_id, "occurrenceKey": key, "tokens": _sorted_tokens(tokens)}
        )

    def _bag_key(item: dict[str, Json]) -> tuple[bytes, bytes]:
        """Return the UTF-16 page/key order for one occurrence record."""
        return (
            str(item["pageId"]).encode("utf-16-be"),
            str(item["occurrenceKey"]).encode("utf-16-be"),
        )

    normalized.sort(key=_bag_key)
    return normalized


def normalize_overrides(  # noqa: C901, PLR0911
    value: object,
) -> dict[str, Json] | None:
    """Sort one Overrides/1 record (None when malformed, values unchecked)."""
    if not isinstance(value, dict) or set(value.keys()) != {"semantic", "occurrence"}:
        return None
    semantic = value.get("semantic")
    if not isinstance(semantic, list):
        return None
    ordered: list[dict[str, Json]] = []
    seen: set[str] = set()
    for record in semantic:
        if not isinstance(record, dict) or set(record.keys()) != {"semanticId", "tokens"}:
            return None
        semantic_id = record.get("semanticId")
        tokens = record.get("tokens")
        if not isinstance(semantic_id, str) or semantic_id in seen:
            return None
        seen.add(semantic_id)
        if not isinstance(tokens, list):
            return None
        names: set[str] = set()
        for entry in tokens:
            if not isinstance(entry, dict) or set(entry.keys()) != {"name", "value"}:
                return None
            if not isinstance(entry.get("name"), str) or entry.get("name") in names:
                return None
            if entry.get("value") is None:
                return None
            names.add(str(entry.get("name")))
        ordered.append({"semanticId": semantic_id, "tokens": _sorted_tokens(tokens)})
    ordered.sort(key=lambda item: str(item["semanticId"]).encode("utf-16-be"))
    occurrence = _normalize_occurrence_bag(value.get("occurrence"))
    if occurrence is None:
        return None
    return {"semantic": ordered, "occurrence": occurrence}


def normalize_di_styles(value: object) -> dict[str, Json] | None:
    """Sort one DiStyles/1 record (None when malformed, values unchecked)."""
    if not isinstance(value, dict) or set(value.keys()) != {"native", "bioc"}:
        return None
    native = _normalize_occurrence_bag(value.get("native"))
    bioc = _normalize_occurrence_bag(value.get("bioc"))
    if native is None or bioc is None:
        return None
    return {"native": native, "bioc": bioc}


def validate_bags(
    overrides: object,
    di_styles: object,
    registry: RegistrySet,
    *,
    check_signatures: bool,
) -> tuple[dict[str, Json] | None, dict[str, Json] | None, str | None]:
    """Normalize and optionally signature-check both runtime bags.

    Returns ``(overrides, di_styles, error)`` where ``error`` is the
    refusal code (shape errors) or ``None``. Signature failures report
    ``render-token-invalid`` when ``check_signatures`` holds.
    """
    normalized_overrides = normalize_overrides(overrides)
    normalized_styles = normalize_di_styles(di_styles)
    if normalized_overrides is None or normalized_styles is None:
        return None, None, "render-token-invalid"
    if check_signatures:
        bags: list[list[dict[str, Json]]] = [
            normalized_overrides["semantic"],
            normalized_overrides["occurrence"],
            normalized_styles["native"],
            normalized_styles["bioc"],
        ]
        for bag in bags:
            for record in bag:
                code = validate_token_list(record["tokens"], registry)
                if code is not None:
                    return None, None, "render-token-invalid"
    return normalized_overrides, normalized_styles, None


def _check_render_token_entry(entry: object) -> dict[str, Json] | None:
    """Project one registry render-token entry (None when malformed)."""
    if not isinstance(entry, dict):
        return None
    name = entry.get("name")
    schema = entry.get("schema")
    if not isinstance(name, str) or not name or not isinstance(schema, dict):
        return None
    if set(entry.keys()) != {"name", "schema"}:
        return None
    return {"name": name, "schema": copy.deepcopy(schema)}


def registry_from_json(  # noqa: C901, PLR0911
    data: object,
) -> PureResult:
    """Load one registry document over the default operator registry.

    Keeps every block-A operator signature and capability; extends the set
    with the document ``renderTokens`` (token name to JSON Schema
    signature), ``regionTokenPattern`` and ``regionTokenSchema``. Malformed
    documents refuse ``profile-schema``.
    """
    if isinstance(data, (bytes, bytearray)):
        try:
            document = json.loads(bytes(data).decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return PureRefused(code="profile-schema")
    elif isinstance(data, dict):
        document = copy.deepcopy(data)
    else:
        return PureRefused(code="profile-schema")
    if not isinstance(document, dict):
        return PureRefused(code="profile-schema")
    tokens: dict[str, dict[str, Json]] = {}
    raw_tokens = document.get("renderTokens", [])
    if not isinstance(raw_tokens, list):
        return PureRefused(code="profile-schema")
    for entry in raw_tokens:
        projected = _check_render_token_entry(entry)
        if projected is None or projected["name"] in tokens:
            return PureRefused(code="profile-schema")
        tokens[projected["name"]] = projected["schema"]
    pattern = document.get("regionTokenPattern")
    if pattern is not None and not isinstance(pattern, str):
        return PureRefused(code="profile-schema")
    try:
        if pattern is not None:
            re.compile(pattern)
    except re.error:
        return PureRefused(code="profile-schema")
    schema = document.get("regionTokenSchema")
    if schema is not None and not isinstance(schema, (dict, list)):
        return PureRefused(code="profile-schema")
    from bpmn_io.profile._compiler import _default_registry  # noqa: PLC0415

    base = _default_registry()
    extended = dataclasses.replace(
        base,
        render_tokens=tokens,
        region_token_pattern=pattern,
        region_token_schema=copy.deepcopy(schema) if schema is not None else None,
    )
    return PureSuccess(payload=extended)
