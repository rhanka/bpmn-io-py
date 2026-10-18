# Shared F1 codec model: diagnostics, results, limits and ordering.
"""Shared model for the extension-preserving codec (contract f1-extensions/1).

Holds the frozen ``Diagnostic``/``CodecResult`` types, the limit table,
the closed reserved-name set (mirroring
``contracts/f1-extensions/1/reserved-names.json`` exactly; a contract test
pins the equality) and the UTF-16 ordering plus profile-c14n/2 helpers.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Union

from bpmn_io.moddle.base import AnyModdleElement, ModdleElement

if TYPE_CHECKING:
    from bpmn_io.bpmn_moddle.bpmn_moddle import BpmnModdle
    from bpmn_io.moddle.registry import PackageDef

__all__ = [
    "ERROR_CODES",
    "LIMITS",
    "RESERVED_NAMES",
    "WARNING_CAP",
    "CodecResult",
    "Diagnostic",
    "JsonObject",
    "JsonValue",
    "NativeElement",
    "build_model",
    "c14n_bytes",
    "escape_pointer",
    "is_valid_qname",
    "resolve_limits",
    "utf16_key",
    "utf16_len",
]

#: Closed diagnostic codes that fail the conversion (``ok`` is False).
ERROR_CODES: Final[frozenset[str]] = frozenset(
    {
        "xml-doctype-forbidden",
        "xml-entity-declaration-forbidden",
        "xml-entity-reference-unsupported",
        "xml-depth-limit",
        "xml-element-count-limit",
        "xml-attribute-count-limit",
        "xml-attribute-length-limit",
        "xml-input-size-limit",
        "reserved-name",
        "invalid-any",
        "malformed-qname",
        "unbound-prefix",
        "invalid-namespace",
        "duplicate-attribute",
        "duplicate-namespace",
        "invalid-xsi-type",
        "unsupported-encoding",
        "invalid-encoding",
        "xml-invalid",
        "invalid-xml-character",
        "descriptor-mismatch",
    }
)

#: Frozen resource limits (see ``contracts/f1-extensions/1/limits.json``).
LIMITS: Final[dict[str, int]] = {
    "xml-input-bytes": 67108864,
    "xml-decoded-bytes": 67108864,
    "xml-depth": 256,
    "xml-elements": 1000000,
    "xml-attributes-per-element": 1024,
    "xml-attr-name-utf16": 1048576,
    "xml-attr-value-utf16": 1048576,
    "json-object-bytes": 67108864,
    "warning-cap": 1000,
}

#: Maximum collected warnings per conversion (mirrors ``LIMITS`` entry).
WARNING_CAP: Final[int] = 1000

#: Closed reserved-name union for both runtimes (contract step-1 seal D1).
#: Sorted in UTF-16 code-unit order; compared against the contract bytes by test.
RESERVED_NAMES: Final[frozenset[str]] = frozenset(
    {
        "$attrs",
        "$body",
        "$children",
        "$descriptor",
        "$model",
        "$parent",
        "$type",
        "__class__",
        "__contains__",
        "__delattr__",
        "__dict__",
        "__dir__",
        "__doc__",
        "__eq__",
        "__format__",
        "__ge__",
        "__getattribute__",
        "__getitem__",
        "__gt__",
        "__hash__",
        "__init__",
        "__init_subclass__",
        "__le__",
        "__lt__",
        "__module__",
        "__ne__",
        "__new__",
        "__proto__",
        "__reduce__",
        "__reduce_ex__",
        "__repr__",
        "__setattr__",
        "__setitem__",
        "__sizeof__",
        "__str__",
        "__subclasshook__",
        "__weakref__",
        "attrs_",
        "constructor",
        "descriptor_",
        "get",
        "hasOwnProperty",
        "has_type",
        "instance_of",
        "isPrototypeOf",
        "model_",
        "parent_",
        "propertyIsEnumerable",
        "prototype",
        "set",
        "toJSON",
        "toLocaleString",
        "toString",
        "to_canonical_dict",
        "type_",
        "valueOf",
    }
)


#: Either native element flavor traversing the codec boundary.
NativeElement = ModdleElement | AnyModdleElement


@dataclass(frozen=True)
class Diagnostic:
    """One typed conversion diagnostic with a source pointer."""

    code: str
    path: str | None
    target: str | None
    detail: str | None


@dataclass(frozen=True)
class CodecResult:
    """The outcome of one codec conversion."""

    ok: bool
    value: Any
    diagnostics: tuple[Diagnostic, ...]


def utf16_key(text: str) -> bytes:
    """Return the UTF-16 code-unit sort key of ``text`` (contract order)."""
    return text.encode("utf-16-be", "surrogatepass")


def utf16_len(text: str) -> int:
    """Count UTF-16 code units of ``text`` (contract string metric).

    Lone surrogates count as one unit each (``surrogatepass``); such
    strings always fail O1 validation downstream.
    """
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def escape_pointer(segment: str) -> str:
    """Escape one RFC 6901 pointer segment."""
    return segment.replace("~", "~0").replace("/", "~1")


#: JSON-compatible data (objects, arrays and scalars; never native elements).
JsonValue = Union["dict[str, JsonValue]", "list[JsonValue]", str, int, float, bool, None]
JsonObject = dict[str, "JsonValue"]


def _normalize_numbers(value: JsonValue) -> JsonValue:
    """Map JSON numbers to ECMAScript shortest-round-trip rendering inputs."""
    if isinstance(value, float):
        if value == 0:
            return 0
        if value.is_integer():
            return int(value)
        return value
    if isinstance(value, dict):
        return {key: _normalize_numbers(entry) for key, entry in value.items()}
    if isinstance(value, list):
        return [_normalize_numbers(entry) for entry in value]
    return value


def _c14n(value: JsonValue) -> str:
    """Render canonical JSON (profile-c14n/2: UTF-16 key order, tight)."""
    normalized = _normalize_numbers(value)
    if isinstance(normalized, list):
        return "[" + ",".join(_c14n(entry) for entry in normalized) + "]"
    if isinstance(normalized, dict):
        keys = sorted(normalized.keys(), key=utf16_key)
        return (
            "{"
            + ",".join(
                json.dumps(key, ensure_ascii=False) + ":" + _c14n(normalized[key]) for key in keys
            )
            + "}"
        )
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def c14n_bytes(value: JsonValue) -> bytes:
    """Return the UTF-8 profile-c14n/2 bytes of ``value`` (size metric).

    Lone surrogates (which always fail O1 downstream) encode as 3-byte
    sequences so the metric stays total and deterministic.
    """
    return _c14n(value).encode("utf-8", "surrogatepass")


_QNAME_RE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*(:[A-Za-z_][A-Za-z0-9_.-]*)?$")


def resolve_limits(limits: dict[str, int] | None) -> dict[str, int]:
    """Merge caller ``limits`` overrides over the frozen contract table."""
    if limits is None:
        return dict(LIMITS)
    merged = dict(LIMITS)
    for key, value in limits.items():
        if key not in merged:
            msg = f"unknown limit {key!r}; expected one of {sorted(merged)}"
            raise ValueError(msg)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            msg = f"limit {key!r} must be a non-negative int"
            raise ValueError(msg)
        merged[key] = value
    return merged


def build_model(
    descriptors: dict[str, PackageDef] | None,
) -> tuple[BpmnModdle | None, Diagnostic | None]:
    """Build the per-call native model, validating descriptors once.

    Every extra package is checked once per conversion (mapping shape,
    URI/prefix/types presence and registry acceptance). A valid empty map
    is accepted and yields the default model. Returns ``(model, None)``
    on success or ``(None, diagnostic)`` carrying a
    ``descriptor-mismatch`` refusal. The model is the per-call
    descriptor cache; nothing is shared between calls.
    """
    from bpmn_io.bpmn_moddle.simple import create_moddle  # noqa: PLC0415

    raw: object = descriptors
    extras: dict[str, PackageDef] = {}
    if raw is not None:
        if not isinstance(raw, dict):
            return None, Diagnostic(
                code="descriptor-mismatch",
                path=None,
                target=None,
                detail="descriptors is not a mapping",
            )
        for name, package in raw.items():
            reason = _validate_descriptor(name, package)
            if reason is not None:
                return None, Diagnostic(
                    code="descriptor-mismatch",
                    path=None,
                    target=None,
                    detail=reason,
                )
            extras[name] = package
    try:
        return create_moddle(extras or None), None
    except Exception as err:  # noqa: BLE001 - registry conflicts refuse as diagnostics
        return None, Diagnostic(
            code="descriptor-mismatch",
            path=None,
            target=None,
            detail=f"injected descriptors rejected: {err}",
        )


def _validate_descriptor(name: object, package: object) -> str | None:
    """Return the refusal reason for one injected package, if invalid."""
    if not isinstance(package, dict):
        return f"descriptor {name!r} is not a mapping"
    for field in ("name", "uri", "prefix", "types"):
        if field not in package:
            return f"descriptor {name!r} misses field {field!r}"
    for field in ("name", "uri", "prefix"):
        if not isinstance(package[field], str) or not package[field]:
            return f"descriptor {name!r} has no string {field}"
    if not isinstance(package["types"], list):
        return f"descriptor {name!r} has no types list"
    return None


def is_valid_qname(name: str) -> bool:
    """Return whether ``name`` is a well-formed ``(prefix:)local`` QName.

    Length is governed by the UTF-16 string limits, not here, so the
    limit-1/limit/limit+1 vectors exercise the real bound.
    """
    if _QNAME_RE.match(name) is None:
        return False
    if name == "xmlns" or name.startswith("xmlns:"):
        return True
    return all(part and not part.startswith((".", "-")) for part in name.split(":"))
