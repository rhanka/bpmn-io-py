"""Closed JSON Schema 2020-12 validator for the mechanism subset.

Supports exactly the 29 DESIGN §2.1 keywords, Boolean schemas, ``re.fullmatch``
patterns with outer anchors removed, integer-as-integral-float semantics,
code-point string lengths and structural enum/const/uniqueItems that
distinguish ``True`` from ``1``. References resolve only within the current
schema or an explicitly supplied digest-pinned registry; no filesystem or
network access.
"""

from __future__ import annotations

import math
import re

__all__ = [
    "CLOSED_KEYWORDS",
    "PATTERN_INVENTORY",
    "SchemaError",
    "SchemaRefusal",
    "validate",
]

#: The 29 supported keywords (DESIGN §2.1, binding §1.1).
CLOSED_KEYWORDS: tuple[str, ...] = (
    "$schema",
    "$id",
    "$comment",
    "title",
    "$defs",
    "$ref",
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minLength",
    "pattern",
    "enum",
    "const",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "allOf",
    "anyOf",
    "oneOf",
    "not",
    "if",
    "then",
    "else",
)

_CLOSED_SET: frozenset[str] = frozenset(CLOSED_KEYWORDS)

_MAX_DEPTH: int = 256


class SchemaRefusal(Exception):  # noqa: N818
    """Schema loading refusal with its closed code."""

    def __init__(self, code: str, message: str = "") -> None:
        """Bind the refusal ``code`` and human ``message``."""
        super().__init__(message or code)
        self.code = code


class SchemaError(Exception):
    """Internal validation traversal error (depth exceeded)."""


def _is_bool(value: object) -> bool:
    """Return whether ``value`` is a JSON boolean."""
    return isinstance(value, bool)


def _is_integer_value(value: object) -> bool:
    """Return whether ``value`` is a JSON Schema integer (integral float ok)."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value) and value.is_integer()
    return False


def _is_number_value(value: object) -> bool:
    """Return whether ``value`` is a finite JSON number."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return False


def _json_equal(first: object, second: object) -> bool:  # noqa: PLR0911
    """Compare two JSON values structurally, keeping ``True`` from ``1``."""
    first_bool = isinstance(first, bool)
    second_bool = isinstance(second, bool)
    if first_bool or second_bool:
        return first_bool and second_bool and first == second
    if isinstance(first, (int, float)) and isinstance(second, (int, float)):
        first_f = float(first)
        second_f = float(second)
        if math.isnan(first_f) or math.isnan(second_f):
            return False
        return first_f == second_f
    if isinstance(first, str) or isinstance(second, str):
        return isinstance(first, str) and isinstance(second, str) and first == second
    if first is None or second is None:
        return first is None and second is None
    if isinstance(first, list) and isinstance(second, list):
        return len(first) == len(second) and all(
            _json_equal(a, b) for a, b in zip(first, second, strict=True)
        )
    if isinstance(first, dict) and isinstance(second, dict):
        if set(first.keys()) != set(second.keys()):
            return False
        return all(_json_equal(first[k], second[k]) for k in first)
    return False


def _check_type(type_name: str, value: object) -> bool:  # noqa: PLR0911
    """Apply one ``type`` name to ``value``."""
    if type_name == "null":
        return value is None
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "integer":
        return _is_integer_value(value)
    if type_name == "number":
        return _is_number_value(value)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "object":
        return isinstance(value, dict)
    return False


#: Closed regex inventory (SPEC §1.2, displayed with schema anchors).
#: Only these eight pinned patterns validate data; any other pattern refuses
#: schema loading with ``profile-schema-pattern``.
PATTERN_INVENTORY: tuple[str, ...] = (
    "^[A-Za-z_][A-Za-z0-9_.:/-]*$",
    "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$",
    "^[a-z]{2}(?:-[A-Z]{2})?$",
    "^[0-9a-f]{64}$",
    "^[A-Za-z_][A-Za-z0-9_]*$",
    "^(?:/(?:[^~/]|~[01])*)*$",
    "^(?:bpmnlint:recommended|plugin:[A-Za-z_][A-Za-z0-9_.-]*/[A-Za-z_][A-Za-z0-9_.-]*)$",
    "^[A-Za-z_][A-Za-z0-9_.:/-]*/[1-9][0-9]*$",
)

_INVENTORY_SET: frozenset[str] = frozenset(PATTERN_INVENTORY)


def _compile_pattern(pattern: str) -> re.Pattern[str]:
    """Compile one schema pattern with the fullmatch policy."""
    if pattern not in _INVENTORY_SET:
        code = "profile-schema-pattern"
        message = f"pattern outside the closed inventory {pattern!r}"
        raise SchemaRefusal(code, message)
    body = pattern[1:-1] if pattern.startswith("^") and pattern.endswith("$") else pattern
    try:
        return re.compile(body)
    except re.error as exc:
        code = "profile-schema-pattern"
        message = f"invalid pattern {pattern!r}"
        raise SchemaRefusal(code, message) from exc


def _unescape_pointer(part: str) -> str:
    """Decode one JSON Pointer segment (``~1`` then ``~0``)."""
    return part.replace("~1", "/").replace("~0", "~")


def _resolve_local_pointer(root: object, pointer: str) -> object:
    """Resolve one ``#/...`` pointer within ``root``."""
    if pointer == "#":
        return root
    if not pointer.startswith("#/"):
        code = "profile-schema-ref"
        raise SchemaRefusal(code, f"unsupported ref {pointer!r}")
    current: object = root
    for raw in pointer[2:].split("/"):
        part = _unescape_pointer(raw)
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            code = "profile-schema-ref"
            raise SchemaRefusal(code, f"unresolvable ref {pointer!r}")
    return current


def _resolve_ref(ref: str, root: object, registry: dict[str, object]) -> tuple[object, object]:
    """Resolve one ``$ref``, returning the target and its resource root.

    Local pointers re-anchor to ``root``; an external ``uri#pointer`` target
    becomes its own resource root so nested local pointers inside the
    referenced document resolve there (Ajv parity), not against the
    referring schema.
    """
    if ref.startswith("#"):
        return _resolve_local_pointer(root, ref), root
    if "#" in ref:
        uri, _, pointer = ref.partition("#")
        target = registry.get(uri)
        if target is None:
            for candidate in registry.values():
                if isinstance(candidate, dict) and candidate.get("$id") == uri:
                    target = candidate
                    break
        if target is None:
            code = "profile-schema-ref"
            raise SchemaRefusal(code, f"unregistered external ref {ref!r}")
        if pointer in ("", "/"):
            return target, target
        if not pointer.startswith("/"):
            code = "profile-schema-ref"
            raise SchemaRefusal(code, f"unsupported ref {ref!r}")
        return _resolve_local_pointer(target, "#" + pointer), target
    code = "profile-schema-ref"
    raise SchemaRefusal(code, f"unsupported ref {ref!r}")


def _audit_keywords(  # noqa: C901, PLR0912
    schema: object, registry: dict[str, object], root: object
) -> None:
    """Refuse schemas using keywords outside the closed subset (bounded).

    Each stack entry carries its own resource root; an external ``$ref``
    target is audited once under its own root so its patterns and nested
    references face the same closed checks (cycle-safe via the seen set).
    """
    stack: list[tuple[object, object]] = [(schema, root)]
    audited: set[int] = set()
    seen = 0
    while stack:
        current, current_root = stack.pop()
        seen += 1
        if seen > 100000 or len(stack) > _MAX_DEPTH * 4:
            message = "schema audit size exceeded"
            raise SchemaError(message)
        if isinstance(current, bool):
            continue
        if not isinstance(current, dict):
            continue
        if id(current) in audited:
            continue
        audited.add(id(current))
        for key, entry in current.items():
            if key not in _CLOSED_SET:
                code = "profile-schema-keyword"
                raise SchemaRefusal(code, f"unsupported keyword {key!r}")
            if key == "additionalProperties" and not isinstance(entry, bool):
                code = "profile-schema-keyword"
                message = "additionalProperties allows Boolean closure only"
                raise SchemaRefusal(code, message)
            if key == "pattern" and isinstance(entry, str):
                _compile_pattern(entry)
        ref = current.get("$ref")
        if isinstance(ref, str):
            # Eager resolution refuses unregistered external pins at load,
            # even when no data element reaches the branch (Ajv parity).
            resolved, resolved_root = _resolve_ref(ref, current_root, registry)
            if resolved_root is not current_root and id(resolved) not in audited:
                stack.append((resolved, resolved_root))
        for key in ("properties", "$defs"):
            branch = current.get(key)
            if isinstance(branch, dict):
                stack.extend((entry, current_root) for entry in branch.values())
        for key in ("items", "not", "if", "then", "else"):
            branch = current.get(key)
            if isinstance(branch, dict | bool):
                stack.append((branch, current_root))
        for key in ("allOf", "anyOf", "oneOf"):
            branch = current.get(key)
            if isinstance(branch, list):
                stack.extend((entry, current_root) for entry in branch)


def _validate_at(  # noqa: C901, PLR0912, PLR0911, PLR0915
    schema: object,
    value: object,
    root: object,
    registry: dict[str, object],
    depth: int,
) -> bool:
    """Validate ``value`` against ``schema`` (recursive, depth-bounded)."""
    if depth > _MAX_DEPTH:
        return False
    if isinstance(schema, bool):
        return schema
    if not isinstance(schema, dict):
        return False
    if "$ref" in schema:
        ref = schema["$ref"]
        if not isinstance(ref, str):
            return False
        resolved, resolved_root = _resolve_ref(ref, root, registry)
        if len(schema) == 1:
            return _validate_at(resolved, value, resolved_root, registry, depth + 1)
        merged = {k: v for k, v in schema.items() if k != "$ref"}
        if not _validate_at(resolved, value, resolved_root, registry, depth + 1):
            return False
        schema = merged
    schema_type = schema.get("type")
    if schema_type is not None:
        names = schema_type if isinstance(schema_type, list) else [schema_type]
        if not any(isinstance(name, str) and _check_type(name, value) for name in names):
            return False
    if "enum" in schema:
        allowed = schema["enum"]
        if not isinstance(allowed, list) or not any(_json_equal(value, entry) for entry in allowed):
            return False
    if "const" in schema and not _json_equal(value, schema["const"]):
        return False
    if isinstance(value, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(value) < min_length:
            return False
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and _compile_pattern(pattern).fullmatch(value) is None:
            return False
    if _is_number_value(value):
        number = float(value)  # type: ignore[arg-type]
        minimum = schema.get("minimum")
        if (
            isinstance(minimum, (int, float))
            and not isinstance(minimum, bool)
            and number < float(minimum)
        ):
            return False
        maximum = schema.get("maximum")
        if (
            isinstance(maximum, (int, float))
            and not isinstance(maximum, bool)
            and number > float(maximum)
        ):
            return False
        exclusive_min = schema.get("exclusiveMinimum")
        if (
            isinstance(exclusive_min, (int, float))
            and not isinstance(exclusive_min, bool)
            and number <= float(exclusive_min)
        ):
            return False
        exclusive_max = schema.get("exclusiveMaximum")
        if (
            isinstance(exclusive_max, (int, float))
            and not isinstance(exclusive_max, bool)
            and number >= float(exclusive_max)
        ):
            return False
    if isinstance(value, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            return False
        max_items = schema.get("maxItems")
        if isinstance(max_items, int) and len(value) > max_items:
            return False
        if schema.get("uniqueItems") is True:
            for i in range(len(value)):
                for j in range(i + 1, len(value)):
                    if _json_equal(value[i], value[j]):
                        return False
        items = schema.get("items")
        if isinstance(items, dict | bool):
            for entry in value:
                if not _validate_at(items, entry, root, registry, depth + 1):
                    return False
    if isinstance(value, dict):
        required = schema.get("required")
        if isinstance(required, list):
            for name in required:
                if not isinstance(name, str) or name not in value:
                    return False
        properties = schema.get("properties")
        if isinstance(properties, dict):
            for name, sub in properties.items():
                if name in value and not _validate_at(sub, value[name], root, registry, depth + 1):
                    return False
        additional = schema.get("additionalProperties")
        if additional is False and isinstance(properties, dict):
            for name in value:
                if name not in properties:
                    return False
    branch_all = schema.get("allOf")
    if isinstance(branch_all, list):
        for sub in branch_all:
            if not _validate_at(sub, value, root, registry, depth + 1):
                return False
    branch_any = schema.get("anyOf")
    if isinstance(branch_any, list) and not any(
        _validate_at(sub, value, root, registry, depth + 1) for sub in branch_any
    ):
        return False
    branch_one = schema.get("oneOf")
    if isinstance(branch_one, list):
        matches = sum(
            1 for sub in branch_one if _validate_at(sub, value, root, registry, depth + 1)
        )
        if matches != 1:
            return False
    not_branch = schema.get("not")
    if isinstance(not_branch, dict | bool) and _validate_at(
        not_branch, value, root, registry, depth + 1
    ):
        return False
    if_branch = schema.get("if")
    if isinstance(if_branch, dict | bool):
        condition = _validate_at(if_branch, value, root, registry, depth + 1)
        branch = schema.get("then" if condition else "else")
        if isinstance(branch, dict | bool) and not _validate_at(
            branch, value, root, registry, depth + 1
        ):
            return False
    return True


def validate(
    schema: object,
    value: object,
    registry: dict[str, object] | None = None,
) -> bool:
    """Validate ``value`` against ``schema`` (closed subset).

    Raises :class:`SchemaRefusal` with ``profile-schema-keyword``,
    ``profile-schema-pattern`` or ``profile-schema-ref`` for schema loading
    failures; returns ``True``/``False`` for data outcomes (``False`` maps to
    ``profile-schema`` at the loader).
    """
    pinned: dict[str, object] = dict(registry) if registry else {}
    _audit_keywords(schema, pinned, schema)
    return _validate_at(schema, value, schema, pinned, 0)
