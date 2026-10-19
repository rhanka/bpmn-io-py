"""Profile compiler (DESIGN R3.3 §2 with §2.4.1 rejection mapping).

Validates selectors, predicates and recipes, scheduling inputs, registries,
signatures, closed references and descriptor context. Returns the first
applicable closed refusal code; malicious or unknown ASTs refuse with the
mapped code, never a partial compiled result.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bpmn_io.profile._c14n import digest, digest_bytes, jcs
from bpmn_io.profile._results import PureRefused, PureResult, PureSuccess

if TYPE_CHECKING:
    from bpmn_io.profile._loader import ValidatedProfile

__all__ = [
    "CompiledProfile",
    "DescriptorContext",
    "RegistrySet",
    "compile_profile",
    "create_descriptor_context",
]

_VALUE_OPS = frozenset(
    {
        "literal",
        "read",
        "id",
        "ids",
        "param",
        "concat",
        "stripPrefix",
        "case",
        "outputId",
    }
)

_PREDICATE_OPS = frozenset(
    {
        "true",
        "false",
        "all",
        "any",
        "not",
        "typeIs",
        "present",
        "equal",
        "textPrefix",
        "count",
        "boundRole",
        "recognizes",
        "reachable",
    }
)

_SELECTOR_VIA = frozenset(
    {
        "self",
        "root",
        "owner",
        "children",
        "descendants",
        "reference",
        "inverseReference",
        "all",
        "pages",
        "occurrences",
        "semantic",
    }
)

_ACTION_OPS = frozenset(
    {
        "bind",
        "create",
        "ensure",
        "set",
        "unset",
        "assignRef",
        "reparent",
        "place",
        "emit",
        "loss",
        "remove",
        "refuse",
    }
)

_PHASES = frozenset(
    {
        "create",
        "edit",
        "complete",
        "normalize",
        "reference",
        "export",
        "convert",
        "migrate",
    }
)

_KNOWN_CAPABILITIES = frozenset(
    {
        "predicates/1",
        "selectors/1",
        "recipes/1",
        "profile-lint/1",
        "render-data/1",
        "export-ir/1",
    }
)

_ACTION_PHASES: dict[str, frozenset[str]] = {
    "bind": _PHASES,
    "refuse": _PHASES,
    "create": frozenset({"create", "edit", "reference", "complete", "convert", "migrate"}),
    "ensure": frozenset({"normalize"}),
    "set": frozenset(
        {"create", "edit", "reference", "complete", "normalize", "convert", "migrate"}
    ),
    "unset": frozenset(
        {"create", "edit", "reference", "complete", "normalize", "convert", "migrate"}
    ),
    "assignRef": frozenset(
        {"create", "edit", "reference", "complete", "normalize", "convert", "migrate"}
    ),
    "reparent": frozenset({"edit", "convert", "migrate"}),
    "place": frozenset({"normalize"}),
    "emit": frozenset({"export"}),
    "loss": frozenset({"export"}),
    "remove": frozenset({"edit", "convert", "migrate"}),
}


@dataclass(frozen=True)
class DescriptorContext:
    """Immutable descriptor and effective-base index for compilation."""

    packages: tuple[dict[str, object], ...]
    types: dict[str, dict[str, object]]
    digest: str


@dataclass(frozen=True)
class RegistrySet:
    """Immutable operator registries with capability versions and digests."""

    capabilities: tuple[str, ...]
    signatures: dict[str, str]
    # Lot 4: render-token signatures (token name to JSON Schema),
    # the region-token pattern and the region-token schema.
    render_tokens: dict[str, dict[str, object]] = field(default_factory=dict)
    region_token_pattern: str | None = None
    region_token_schema: dict[str, object] | list[str] | None = None


@dataclass(frozen=True)
class CompiledProfile:
    """One immutable compiled profile with indexes, identity and validation records.

    ``validation`` retains the raw profile validation records verbatim so the
    lint lane can derive its stage transport; record shape is validated there,
    not here.
    """

    profile_digest: str
    notions: dict[str, dict[str, object]]
    recipes: dict[str, dict[str, object]]
    rules: dict[str, dict[str, object]]
    descriptor_digest: str
    registry_digest: str
    validation: tuple[object, ...] = ()
    # Lot 4 extension: the complete validated profile JSON, the closed
    # §5.1 profileIdentity record, verified resource bytes by resource id
    # and the render-token signatures active at compile time.
    profile: dict[str, object] = field(default_factory=dict)
    identity: dict[str, object] = field(default_factory=dict)
    assets: dict[str, bytes] = field(default_factory=dict)
    render_registry: dict[str, dict[str, object]] = field(default_factory=dict)


@dataclass
class _Scope:
    """Mutable checking scope for one predicate/value/selector position."""

    notions: set[str]
    bindings: set[str]
    btypes: dict[str, str]
    params: dict[str, str]
    types: dict[str, dict[str, object]] | None
    producers: dict[tuple[str, str], frozenset[str]] | None
    ref_fields: set[tuple[str, str]] | None
    used_families: set[str] = field(default_factory=set)

    def child(self) -> _Scope:
        """Fork one scope for a nested ``where`` with its own self type."""
        return _Scope(
            notions=self.notions,
            bindings=set(self.bindings),
            btypes=dict(self.btypes),
            params=self.params,
            types=self.types,
            producers=self.producers,
            ref_fields=self.ref_fields,
            used_families=self.used_families,
        )


#: Capability family per operator (CR-01); selectors and render/export
#: positions record their families at their visit sites.
_FAMILY_OF_OP: dict[str, str] = {
    **dict.fromkeys(_VALUE_OPS | _PREDICATE_OPS, "predicates/1"),
    **dict.fromkeys(_ACTION_OPS, "recipes/1"),
}

#: Render traversals and value positions needing the render capability.
_RENDER_VIA = frozenset({"pages", "occurrences", "semantic"})

#: Typed page/occurrence record fields for read-path checks (DESIGN §2.5).
_RECORD_FIELDS: dict[str, object] = {
    "page": {
        "pageId": "string",
        "name": "string",
        "semanticRootId": "string",
        "order": "number",
        "bounds": {"x": "number", "y": "number", "width": "number", "height": "number"},
    },
    "occurrence": {
        "pageId": "string",
        "occurrenceKey": "string",
        "semanticId": "string",
        "role": "string",
        "emittedType": "string",
        "glyphId": "string",
        "order": "number",
        "label": {
            "text": "string",
            "lines": "array",
            "bounds": {"x": "number", "y": "number", "width": "number", "height": "number"},
        },
        "waypoints": "array",
        "style": "array",
        "sourceOccurrence": {"pageId": "string", "occurrenceKey": "string"},
        "targetOccurrence": {"pageId": "string", "occurrenceKey": "string"},
    },
}


def _as_list(value: object) -> list[object]:
    """Return ``value`` when it is a list, else an empty list (mypy-safe iteration)."""
    return value if isinstance(value, list) else []


#: Bounded generic walk size (DESIGN §2.5 host resource limit).
_MAX_COMPILE_NODES: int = 4000000


def _record_path_type(record: object, segments: list[str]) -> str | None:
    """Resolve path ``segments`` in one typed record (None when invalid)."""
    current = record
    for part in segments:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current if isinstance(current, str) else None


def _check_read_path(scope: _Scope, binding: str, path: object) -> str | None:
    """Validate one ``read`` path against the binding type (refusal or None)."""
    if not isinstance(path, str) or not path.startswith("/") or "//" in path:
        return "profile-type"
    segments = path[1:].split("/")
    if any(not part for part in segments):
        return "profile-type"
    btype = scope.btypes.get(binding, "native")
    record = _RECORD_FIELDS.get(btype)
    if record is not None:
        resolved = _record_path_type(record, segments)
        return None if isinstance(resolved, str) else "profile-type"
    if scope.types is not None and btype in scope.types:
        spec = scope.types[btype]
        facets: set[str] = set()
        scalars = spec.get("scalars", ())
        if isinstance(scalars, (list, tuple)):
            facets.update(item for item in scalars if isinstance(item, str))
        for role in ("containment", "references"):
            role_map = spec.get(role, {})
            if isinstance(role_map, dict):
                facets.update(key for key in role_map if isinstance(key, str))
        if segments[0] not in facets:
            return "profile-type"
    return None


def _read_value_type(node: dict[str, object], scope: _Scope) -> str:
    """Classify one ``read`` AST against its binding type (``unknown`` when open)."""
    binding = node.get("binding")
    path = node.get("path")
    if not isinstance(binding, str) or not isinstance(path, str):
        return "unknown"
    btype = scope.btypes.get(binding, "native")
    record = _RECORD_FIELDS.get(btype)
    if record is None:
        return "unknown"
    resolved = _record_path_type(record, path[1:].split("/"))
    return resolved if isinstance(resolved, str) else "unknown"


def _value_type(node: object, scope: _Scope) -> str:  # noqa: C901, PLR0911
    """Classify one value AST (``string``/``number``/``boolean``/``array``/``unknown``)."""
    if not isinstance(node, dict):
        return "unknown"
    op = node.get("op")
    if op == "literal":
        value = node.get("value")
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, str):
            return "string"
        if isinstance(value, (int, float)):
            return "number"
        return "unknown"
    if op in ("id", "outputId", "concat", "stripPrefix", "case"):
        return "string"
    if op == "ids":
        return "array"
    if op == "param":
        declared = scope.params.get(str(node.get("name")))
        if declared in ("string", "number", "boolean", "array"):
            return declared
        return "unknown"
    if op == "read":
        return _read_value_type(node, scope)
    return "unknown"


def _infer_selector_type(selector: object, scope: _Scope) -> str:
    """Infer the native type bound by one selector (``native`` when unknown)."""
    if not isinstance(selector, dict):
        return "native"
    via = selector.get("via")
    if via == "pages":
        return "page"
    if via == "occurrences":
        return "occurrence"
    where = selector.get("where")
    if isinstance(where, dict) and where.get("op") == "typeIs":
        candidate = where.get("type")
        if isinstance(candidate, str) and candidate:
            return candidate
    if via == "self":
        source = selector.get("from")
        if isinstance(source, str):
            return scope.btypes.get(source, "native")
    return "native"


def _check_op_signatures(profile: object, registry: RegistrySet, used: set[str]) -> str | None:
    """Check every profile operator against the registry (CR-01, bounded).

    Any ``op`` outside the known tables refuses ``profile-symbol``; a known
    operator without an exact registry signature refuses
    ``profile-capability``. Schema-valid profiles carry ``op`` only in AST
    positions, so the generic walk is exact.
    """
    stack: list[object] = [profile]
    visited = 0
    while stack:
        node = stack.pop()
        visited += 1
        if visited > _MAX_COMPILE_NODES:
            return "resource-limit"
        if isinstance(node, dict):
            op = node.get("op")
            if isinstance(op, str):
                if op in _VALUE_OPS or op in _PREDICATE_OPS or op in _ACTION_OPS:
                    if op not in registry.signatures:
                        return "profile-capability"
                    used.add(_FAMILY_OF_OP[op])
                else:
                    return "profile-symbol"
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return None


def _default_registry() -> RegistrySet:
    """Return the library-owned generic primitive registry set."""
    signatures = dict.fromkeys(_VALUE_OPS | _PREDICATE_OPS | _ACTION_OPS, "generic/1")
    return RegistrySet(
        capabilities=tuple(sorted(_KNOWN_CAPABILITIES)),
        signatures=signatures,
    )


def _normalize_string_list(value: object) -> tuple[str, ...] | None:
    """Normalize one string-list facet (None when malformed)."""
    if not isinstance(value, list):
        return None
    if not all(isinstance(item, str) for item in value):
        return None
    return tuple(value)


def _normalize_string_map(value: object) -> dict[str, tuple[str, ...]] | None:
    """Normalize one property-to-types facet (None when malformed)."""
    if not isinstance(value, dict):
        return None
    normalized: dict[str, tuple[str, ...]] = {}
    for prop, targets in value.items():
        admitted = _normalize_string_list(targets)
        if not isinstance(prop, str) or admitted is None:
            return None
        normalized[prop] = admitted
    return normalized


def _normalize_producer_fields(value: object) -> dict[str, tuple[str, ...]] | None:
    """Normalize descriptor extension producer rights (None when malformed)."""
    if not isinstance(value, list):
        return None
    producers: dict[str, tuple[str, ...]] = {}
    for item in value:
        if not isinstance(item, dict):
            return None
        field_name = item.get("field")
        actors = _normalize_string_list(item.get("producers"))
        if not isinstance(field_name, str) or actors is None:
            return None
        if field_name in producers:
            return None
        producers[field_name] = actors
    return producers


def _normalize_type_record(name: object, record: object) -> dict[str, object] | None:
    """Normalize one descriptor type to its closed facets (None when malformed).

    Keeps ``scalars``, ``containment`` and ``references`` plus the ``id``
    admission flag and optional ``producerFields``; every facet defaults to
    empty when absent (an absent ``id`` flag defaults to admitted). The
    normalized form is freshly built, so the context owns its index.
    """
    if not isinstance(name, str) or not isinstance(record, dict):
        return None
    scalars = _normalize_string_list(record.get("scalars", []))
    admitted = _normalize_string_map(record.get("containment", {}))
    linked = _normalize_string_map(record.get("references", {}))
    producers = _normalize_producer_fields(record.get("producerFields", []))
    id_flag = record.get("id", True)
    if scalars is None or admitted is None or linked is None or producers is None:
        return None
    if not isinstance(id_flag, bool):
        return None
    return {
        "scalars": scalars,
        "containment": admitted,
        "references": linked,
        "id": id_flag,
        "producerFields": producers,
    }


def _package_bytes(raw: object) -> bytes | None:
    """Decode one package's immutable ``descriptorBytes`` (None when malformed)."""
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    if isinstance(raw, str):
        return raw.encode("utf-8")
    if isinstance(raw, dict):
        return jcs(raw).encode("utf-8")
    return None


def _index_package_types(descriptor: object, types: dict[str, dict[str, object]]) -> str | None:
    """Merge one package's type document into the index (refusal or None)."""
    if not isinstance(descriptor, dict) or not isinstance(descriptor.get("types"), dict):
        return "descriptor-mismatch"
    for type_name, record in descriptor["types"].items():
        if type_name in types:
            return "descriptor-mismatch"
        normalized = _normalize_type_record(type_name, record)
        if normalized is None:
            return "descriptor-mismatch"
        types[type_name] = normalized
    return None


def create_descriptor_context(
    packages: list[dict[str, object]],
) -> PureResult:
    """Build one descriptor context from pinned packages.

    Each package carries ``id``, ``version``, ``sha256`` and immutable UTF-8
    ``descriptorBytes`` whose raw SHA-256 must match. IDs stay unique, and
    the ``types`` document inside the bytes builds the normalized
    descriptor index (scalars, containment, references, id admission).
    Duplicate package or type definitions refuse ``descriptor-mismatch``.
    """
    seen: set[str] = set()
    types: dict[str, dict[str, object]] = {}
    for entry in packages:
        package_id = entry.get("id")
        want = entry.get("sha256")
        if not isinstance(package_id, str) or not isinstance(want, str):
            return PureRefused(code="descriptor-mismatch")
        if package_id in seen:
            return PureRefused(code="descriptor-mismatch")
        seen.add(package_id)
        raw_bytes = _package_bytes(entry.get("descriptorBytes"))
        if raw_bytes is None or digest_bytes(raw_bytes) != want:
            return PureRefused(code="descriptor-mismatch")
        try:
            descriptor = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return PureRefused(code="descriptor-mismatch")
        code = _index_package_types(descriptor, types)
        if code is not None:
            return PureRefused(code=code)
    context_digest = digest(sorted(seen))
    owned = tuple(copy.deepcopy(entry) for entry in packages)
    context = DescriptorContext(packages=owned, types=types, digest=context_digest)
    return PureSuccess(payload=context)


def _check_value(  # noqa: C901, PLR0911, PLR0912
    node: object, context: str, scope: _Scope, phase: str | None = None
) -> str | None:
    """Validate one value AST; return a refusal code or ``None``."""
    _ = phase
    if not isinstance(node, dict):
        return "profile-type"
    op = node.get("op")
    if not isinstance(op, str) or op not in _VALUE_OPS:
        return "profile-symbol"
    if op == "literal":
        if "value" not in node or not isinstance(node["value"], (str, int, float, bool)):
            return "profile-type"
        if isinstance(node["value"], bool):
            return None
        return None
    if op == "read":
        binding = node.get("binding")
        if not isinstance(binding, str) or not isinstance(node.get("path"), str):
            return "profile-type"
        if binding not in scope.bindings:
            return "profile-symbol"
        return _check_read_path(scope, binding, node.get("path"))
    if op == "id":
        binding = node.get("binding")
        if not isinstance(binding, str):
            return "profile-type"
        if binding not in scope.bindings:
            return "profile-symbol"
        return None
    if op == "ids":
        if context != "assignRef-values":
            return "profile-value-context"
        return None
    if op == "param":
        name = node.get("name")
        if not isinstance(name, str):
            return "profile-type"
        if name not in scope.params:
            return "profile-symbol"
        return None
    if op == "concat":
        values = node.get("values")
        if not isinstance(values, list) or not values:
            return "profile-type"
        for entry in values:
            code = _check_value(entry, "concat", scope, phase)
            if code is not None:
                return code
            if _value_type(entry, scope) not in ("string", "unknown"):
                return "profile-type"
        return None
    if op == "stripPrefix":
        if not isinstance(node.get("prefix"), str):
            return "profile-type"
        code = _check_value(node.get("value"), context, scope, phase)
        if code is not None:
            return code
        if _value_type(node.get("value"), scope) not in ("string", "unknown"):
            return "profile-type"
        return None
    if op == "case":
        if node.get("mode") not in ("upper", "lower"):
            return "profile-type"
        if node.get("unicode", "15.0.0") != "15.0.0":
            return "profile-type"
        code = _check_value(node.get("value"), context, scope, phase)
        if code is not None:
            return code
        if _value_type(node.get("value"), scope) not in ("string", "unknown"):
            return "profile-type"
        return None
    if op == "outputId":
        if context not in ("emit-fields", "emit-parent"):
            return "profile-value-context"
        binding = node.get("binding")
        if not isinstance(binding, str) or not isinstance(node.get("domain"), str):
            return "profile-type"
        if binding not in scope.bindings:
            return "profile-symbol"
        scope.used_families.add("render-data/1")
        return None
    return "profile-type"


def _check_predicate(  # noqa: C901, PLR0911, PLR0912, PLR0915
    node: object, scope: _Scope, context_phase: str = "rule"
) -> str | None:
    """Validate one predicate AST; return a refusal code or ``None``."""
    if not isinstance(node, dict):
        return "profile-type"
    op = node.get("op")
    if not isinstance(op, str) or op not in _PREDICATE_OPS:
        return "profile-symbol"
    if op in ("true", "false"):
        return None
    if op in ("all", "any"):
        args = node.get("args")
        if not isinstance(args, list) or not args:
            return "profile-type"
        for entry in args:
            code = _check_predicate(entry, scope, context_phase)
            if code is not None:
                return code
        return None
    if op == "not":
        if "arg" not in node or "args" in node:
            return "profile-type"
        return _check_predicate(node.get("arg"), scope, context_phase)
    if op == "typeIs":
        binding = node.get("binding")
        type_name = node.get("type")
        if not isinstance(binding, str) or not isinstance(type_name, str):
            return "profile-type"
        if node.get("mode") not in ("exact", "assignable"):
            return "profile-type"
        if binding not in scope.bindings:
            return "profile-symbol"
        if ":" in type_name and scope.types is not None and type_name not in scope.types:
            return "profile-type"
        return None
    if op == "present":
        return _check_value(node.get("value"), "predicate", scope, None)
    if op == "equal":
        for key in ("left", "right"):
            code = _check_value(node.get(key), "predicate", scope, None)
            if code is not None:
                return code
        return None
    if op == "textPrefix":
        if not isinstance(node.get("prefix"), str) or not node.get("prefix"):
            return "profile-type"
        if node.get("trim") not in ("none", "ecma262-2024-start"):
            return "profile-type"
        return _check_value(node.get("value"), "predicate", scope, None)
    if op == "count":
        selector = node.get("select", node.get("selector"))
        code = _check_selector(selector, scope, context_phase)
        if code is not None:
            return code
        minimum = node.get("min")
        maximum = node.get("max")
        if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 0:
            return "profile-bounds"
        if maximum is not None and (
            not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < minimum
        ):
            return "profile-bounds"
        return None
    if op == "boundRole":
        binding = node.get("binding")
        owner = node.get("owner")
        if not isinstance(binding, str) or not isinstance(owner, str):
            return "profile-type"
        if binding not in scope.bindings or owner not in scope.bindings:
            return "profile-symbol"
        return None
    if op == "recognizes":
        binding = node.get("binding")
        notion = node.get("notion")
        if not isinstance(binding, str) or not isinstance(notion, str):
            return "profile-type"
        if binding not in scope.bindings:
            return "profile-symbol"
        if notion not in scope.notions:
            return "profile-symbol"
        return None
    if op == "reachable":
        for key in ("source", "target"):
            code = _check_selector(node.get(key), scope, context_phase)
            if code is not None:
                return code
        edge_types = node.get("edgeTypes")
        if not isinstance(edge_types, list) or not edge_types:
            return "profile-type"
        if scope.types is not None:
            for edge in edge_types:
                if isinstance(edge, str) and ":" in edge and edge not in scope.types:
                    return "profile-type"
        min_hops = node.get("minHops")
        max_hops = node.get("maxHops")
        if not isinstance(min_hops, int) or isinstance(min_hops, bool) or min_hops < 0:
            return "profile-bounds"
        if max_hops is not None and (
            not isinstance(max_hops, int) or isinstance(max_hops, bool) or max_hops < min_hops
        ):
            return "profile-bounds"
        return None
    return "profile-type"


def _check_reference_property(scope: _Scope, from_name: str, prop: str) -> str | None:
    """Validate a reference-traversal property against the descriptor index.

    Admits descriptor reference properties and base-declared ID-valued
    scalar references such as ``calledElement`` (DESIGN §2.2); anything else
    on a known native type refuses.
    """
    from_type = scope.btypes.get(from_name, "native")
    if from_type in ("page", "occurrence"):
        if prop not in ("sourceOccurrence", "targetOccurrence"):
            return "profile-selector-property"
        return None
    if scope.types is None or from_type not in scope.types:
        return None
    spec = scope.types[from_type]
    references = spec.get("references", {})
    if isinstance(references, dict) and prop in references:
        return None
    scalars = spec.get("scalars", ())
    is_scalar = isinstance(scalars, (list, tuple)) and prop in scalars
    if is_scalar and scope.ref_fields is not None and (from_type, prop) in scope.ref_fields:
        return None
    return "profile-type"


def _check_selector(  # noqa: C901, PLR0911, PLR0912
    node: object,
    scope: _Scope,
    context_phase: str = "rule",
) -> str | None:
    """Validate one selector AST; return a refusal code or ``None``."""
    if not isinstance(node, dict):
        return "profile-type"
    from_name = node.get("from")
    via = node.get("via")
    order = node.get("order")
    if not isinstance(from_name, str) or not isinstance(via, str):
        return "profile-type"
    if from_name not in scope.bindings:
        return "profile-symbol"
    if via not in _SELECTOR_VIA:
        return "profile-symbol"
    scope.used_families.add("selectors/1")
    native_via = {
        "self",
        "root",
        "owner",
        "children",
        "descendants",
        "reference",
        "inverseReference",
        "all",
    }
    render_via = {"pages", "occurrences", "semantic"}
    if via in render_via:
        scope.used_families.add("render-data/1")
        if context_phase != "export":
            return "profile-value-context"
    if via == "self" and order not in ("id", "page-occurrence"):
        return "profile-selector-order"
    if via in native_via and via != "self" and order != "id":
        # Lot 4 (DESIGN §2.2): a reference traversal from an occurrence
        # binding takes page-occurrence order.
        if (
            via == "reference"
            and order == "page-occurrence"
            and scope.btypes.get(from_name) == "occurrence"
        ):
            pass
        else:
            return "profile-selector-order"
    if via in render_via and via != "semantic" and order != "page-occurrence":
        return "profile-selector-order"
    if via == "semantic" and order != "id":
        return "profile-selector-order"
    has_property = "property" in node
    if via in ("reference", "inverseReference"):
        if not has_property or not isinstance(node.get("property"), str):
            return "profile-selector-property"
        if via == "inverseReference":
            from_type = scope.btypes.get(from_name, "native")
            if from_type in ("page", "occurrence"):
                return "profile-selector-property"
        code = _check_reference_property(scope, from_name, str(node.get("property")))
        if code is not None:
            return code
    elif via == "children":
        if has_property and not isinstance(node.get("property"), str):
            return "profile-selector-property"
        from_type = scope.btypes.get(from_name, "native")
        if has_property and scope.types is not None and from_type in scope.types:
            spec = scope.types[from_type]
            containment = spec.get("containment", {})
            if isinstance(containment, dict) and node.get("property") not in containment:
                return "profile-type"
    elif has_property:
        return "profile-selector-property"
    where = node.get("where")
    if where is not None:
        inner = scope.child()
        inner.btypes["self"] = _infer_selector_type(node, scope)
        code = _check_predicate(where, inner, context_phase)
        if code is not None:
            return code
    return None


def _authorize(scope: _Scope, btype: str, field_name: str, phase: str) -> str | None:
    """Check one native write against effective producer rights (CR-06).

    The phase actor is ``code`` for complete/normalize and ``editor``
    otherwise; export has no native write authority. A known native type
    checks its own producers; an unknown binding checks every admitted
    target type supporting the field (DESIGN §2.4.1 CR-06).
    """
    if scope.producers is None or scope.types is None or not field_name:
        return None
    actor = "code" if phase in ("complete", "normalize") else "editor"
    if btype in scope.types:
        candidates = [btype]
    else:
        candidates = [
            name for name, spec in scope.types.items() if _type_has_field(spec, field_name)
        ]
        if not candidates:
            return "profile-type"
    for candidate in candidates:
        if actor not in scope.producers.get((candidate, field_name), frozenset()):
            return "profile-producer"
    return None


def _type_has_field(spec: dict[str, object], field_name: str) -> bool:
    """Return whether one normalized type admits ``field_name`` anywhere."""
    scalars = spec.get("scalars", ())
    if isinstance(scalars, (list, tuple)) and field_name in scalars:
        return True
    for role in ("containment", "references"):
        role_map = spec.get(role, {})
        if isinstance(role_map, dict) and field_name in role_map:
            return True
    return False


def _check_action(  # noqa: C901, PLR0911, PLR0912, PLR0915
    step: object, phase: str, scope: _Scope, demands: list[dict[str, object]]
) -> str | None:
    """Validate one recipe step; return a refusal code or ``None``."""
    if not isinstance(step, dict):
        return "profile-type"
    op = step.get("op")
    if not isinstance(op, str) or op not in _ACTION_OPS:
        return "profile-symbol"
    allowed = _ACTION_PHASES.get(op, frozenset())
    if phase not in allowed:
        return "profile-action-phase"
    context_phase = "export" if phase == "export" else "recipe"
    if op == "bind":
        return _check_bind(step, scope, context_phase)
    if op == "create":
        return _check_create(step, phase, scope, demands)
    if op in ("set", "unset"):
        return _check_set(step, op, phase, scope, demands)
    if op == "assignRef":
        return _check_assign_ref(step, phase, scope, demands)
    if op == "reparent":
        target = step.get("target")
        parent = step.get("parent")
        prop = step.get("property")
        if not isinstance(target, str) or not isinstance(parent, str):
            return "profile-type"
        if target not in scope.bindings or parent not in scope.bindings:
            return "profile-symbol"
        if prop is not None:
            if not isinstance(prop, str):
                return "profile-type"
            parent_type = scope.btypes.get(parent, "native")
            if scope.types is not None and parent_type in scope.types:
                containment = scope.types[parent_type].get("containment", {})
                if isinstance(containment, dict) and prop not in containment:
                    return "profile-type"
            demands.append({"binding": parent, "path": "/" + prop, "mode": "reparent"})
            code = _authorize(scope, parent_type, prop, phase)
            if code is not None:
                return code
        demands.append({"binding": target, "path": "", "mode": "reparent"})
        return None
    if op == "place":
        target = step.get("target")
        if not isinstance(target, str):
            return "profile-type"
        if target not in scope.bindings:
            return "profile-symbol"
        owner = step.get("owner")
        if owner is not None:
            if not isinstance(owner, str):
                return "profile-type"
            if owner not in scope.bindings:
                return "profile-symbol"
        related = step.get("related")
        if related is not None:
            code = _check_selector(related, scope, context_phase)
            if code is not None:
                return code
        demands.append({"binding": target, "path": "", "mode": "placement"})
        return None
    if op == "emit":
        fields = step.get("fields", [])
        if not isinstance(fields, list):
            return "profile-export-field"
        for entry in fields:
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
                return "profile-export-field"
            code = _check_value(entry.get("value"), "emit-fields", scope, phase)
            if code is not None:
                return code
        parent = step.get("parent")
        if parent is not None:
            code = _check_value(parent, "emit-parent", scope, phase)
            if code is not None:
                return code
        scope.used_families.add("export-ir/1")
        demands.append({"binding": "self", "path": "", "mode": "artifact"})
        return None
    if op == "loss":
        target = step.get("target")
        if target is not None:
            if not isinstance(target, str):
                return "profile-type"
            if target not in scope.bindings:
                return "profile-symbol"
            demands.append({"binding": target, "path": "", "mode": "report"})
        scope.used_families.add("export-ir/1")
        return None
    if op == "remove":
        target = step.get("target")
        if not isinstance(target, str):
            return "profile-type"
        if target not in scope.bindings:
            return "profile-symbol"
        demands.append({"binding": target, "path": "", "mode": "remove"})
        return None
    if op == "ensure":
        alias = step.get("as")
        if alias is not None:
            if not isinstance(alias, str) or not alias:
                return "profile-type"
            scope.bindings.add(alias)
            native_type = step.get("type")
            scope.btypes[alias] = native_type if isinstance(native_type, str) else "native"
        return None
    if op == "refuse":
        if not isinstance(step.get("code"), str):
            return "profile-type"
        target = step.get("target")
        if target is not None:
            if not isinstance(target, str):
                return "profile-type"
            if target not in scope.bindings:
                return "profile-symbol"
        return None
    return "profile-type"


def _check_bind(step: dict[str, object], scope: _Scope, context_phase: str) -> str | None:
    """Validate one bind step and register its alias (CR-05/CR-13)."""
    selector = step.get("select")
    code = _check_selector(selector, scope, context_phase)
    if code is not None:
        return code
    alias = step.get("as")
    cardinality = step.get("cardinality")
    if not isinstance(alias, str) or not alias:
        return "profile-type"
    if cardinality not in ("one", "zeroOrOne", "first"):
        return "profile-type"
    fallbacks = step.get("fallbacks")
    if fallbacks is not None and cardinality != "first":
        return "profile-bind-fallbacks"
    if isinstance(fallbacks, list):
        for entry in fallbacks:
            code = _check_selector(entry, scope, context_phase)
            if code is not None:
                return code
    scope.bindings.add(alias)
    scope.btypes[alias] = _infer_selector_type(selector, scope)
    return None


def _check_create_parent(
    step: dict[str, object],
    native_type: str,
    phase: str,
    scope: _Scope,
    demands: list[dict[str, object]],
) -> str | None:
    """Validate one create parent/property with containment admission (CR-06)."""
    parent = step.get("parent")
    prop = step.get("property")
    if parent is None and prop is None:
        return None
    if not isinstance(parent, str) or not isinstance(prop, str):
        return "profile-type"
    if parent not in scope.bindings:
        return "profile-symbol"
    parent_type = scope.btypes.get(parent, "native")
    if scope.types is not None and parent_type in scope.types:
        containment = scope.types[parent_type].get("containment", {})
        admitted_types: tuple[str, ...] | list[str] | None = None
        if isinstance(containment, dict):
            maybe = containment.get(prop)
            if isinstance(maybe, (list, tuple)):
                admitted_types = maybe
        if admitted_types is None or native_type not in admitted_types:
            return "profile-type"
    demands.append({"binding": parent, "path": "/" + prop, "mode": "create"})
    return _authorize(scope, parent_type, prop, phase)


def _check_create_field(
    entry: object,
    native_type: str,
    phase: str,
    scope: _Scope,
) -> str | None:
    """Validate one create field with scalar admission and producers."""
    if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
        return "profile-type"
    field_name = str(entry.get("name"))
    if scope.types is not None and native_type in scope.types:
        scalars = scope.types[native_type].get("scalars", ())
        if not isinstance(scalars, (list, tuple)) or field_name not in scalars:
            return "profile-type"
        if field_name == "id":
            return "profile-type"
    code = _check_value(entry.get("value"), "create-field", scope, phase)
    if code is not None:
        return code
    return _authorize(scope, native_type, field_name, phase)


def _check_create_fields(
    step: dict[str, object],
    native_type: str,
    phase: str,
    scope: _Scope,
) -> str | None:
    """Validate one create field list with scalar admission and producers."""
    fields = step.get("fields", [])
    if not isinstance(fields, list):
        return "profile-type"
    for entry in fields:
        code = _check_create_field(entry, native_type, phase, scope)
        if code is not None:
            return code
    return None


def _check_create(  # noqa: C901, PLR0911, PLR0912
    step: dict[str, object], phase: str, scope: _Scope, demands: list[dict[str, object]]
) -> str | None:
    """Validate one create step with identity, admission and producers (CR-06/07)."""
    identity = step.get("identity")
    if identity not in ("allocated", "containment"):
        return "profile-create-identity"
    if identity == "allocated":
        for key in ("ownerId", "slot", "key"):
            if key not in step:
                return "profile-create-identity"
    else:
        for key in ("ownerId", "slot", "key"):
            if key in step:
                return "profile-create-identity"
    native_type = step.get("type")
    if not isinstance(native_type, str) or not native_type:
        return "profile-type"
    if ":" in native_type and scope.types is not None and native_type not in scope.types:
        return "profile-type"
    if scope.types is not None and native_type in scope.types:
        admitted = scope.types[native_type].get("id", True) is True
        if admitted != (identity == "allocated"):
            return "profile-create-identity"
    for key in ("ownerId", "key"):
        if key in step:
            code = _check_value(step.get(key), "create-field", scope, phase)
            if code is not None:
                return code
    code = _check_create_fields(step, native_type, phase, scope)
    if code is not None:
        return code
    if identity == "allocated":
        code = _authorize(scope, native_type, "id", phase)
        if code is not None:
            return code
    alias = step.get("as")
    if alias is not None:
        if not isinstance(alias, str) or not alias:
            return "profile-type"
        scope.bindings.add(alias)
        scope.btypes[alias] = native_type
    return _check_create_parent(step, native_type, phase, scope, demands)


def _write_target(step: dict[str, object], scope: _Scope) -> tuple[str, str, str, str | None]:
    """Split one write step into ``(target, path, head, error)`` (CR-06)."""
    target = step.get("target")
    path = step.get("path")
    if not isinstance(target, str) or not isinstance(path, str):
        return "", "", "", "profile-type"
    if target not in scope.bindings:
        return "", "", "", "profile-symbol"
    if not path.startswith("/") or "//" in path:
        return "", "", "", "profile-type"
    head = path[1:].split("/")[0]
    if not head:
        return "", "", "", "profile-type"
    if head == "id":
        return "", "", "", "profile-producer"
    return target, path, head, None


def _check_set(
    step: dict[str, object],
    op: str,
    phase: str,
    scope: _Scope,
    demands: list[dict[str, object]],
) -> str | None:
    """Validate one set/unset step with path admission and producers (CR-06)."""
    target, path, head, error = _write_target(step, scope)
    if error is not None:
        return error
    target_type = scope.btypes.get(target, "native")
    if scope.types is not None and target_type in scope.types:
        scalars = scope.types[target_type].get("scalars", ())
        if not isinstance(scalars, (list, tuple)) or head not in scalars:
            return "profile-type"
    if op == "set":
        code = _check_value(step.get("value"), "set", scope, phase)
        if code is not None:
            return code
    demands.append({"binding": target, "path": path, "mode": op})
    return _authorize(scope, target_type, head, phase)


def _check_assign_ref(
    step: dict[str, object],
    phase: str,
    scope: _Scope,
    demands: list[dict[str, object]],
) -> str | None:
    """Validate one assignRef step with reference admission and producers."""
    target, path, head, error = _write_target(step, scope)
    if error is not None:
        return error
    target_type = scope.btypes.get(target, "native")
    if scope.types is not None and target_type in scope.types:
        references = scope.types[target_type].get("references", {})
        if not isinstance(references, dict) or head not in references:
            return "profile-type"
    values = step.get("values")
    if not isinstance(values, list):
        return "profile-type"
    for entry in values:
        code = _check_value(entry, "assignRef-values", scope, phase)
        if code is not None:
            return code
    if step.get("mode") not in ("replace", "appendUnique", "remove"):
        return "profile-type"
    demands.append({"binding": target, "path": path, "mode": "reference"})
    return _authorize(scope, target_type, head, phase)


def _collect_recognizes(node: object, edges: set[str]) -> None:
    """Collect ``recognizes`` notion targets under one AST (bounded, iterative)."""
    stack: list[object] = [node]
    visited = 0
    while stack:
        current = stack.pop()
        visited += 1
        if visited > _MAX_COMPILE_NODES:
            return
        if isinstance(current, dict):
            if current.get("op") == "recognizes":
                notion = current.get("notion")
                if isinstance(notion, str):
                    edges.add(notion)
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def _recognition_cycle(notions_raw: list[object]) -> str | None:  # noqa: C901
    """Detect a recognition dependency cycle (CR-05, ``profile-cycle``)."""
    edges: dict[str, set[str]] = {}
    for notion in notions_raw:
        if not isinstance(notion, dict):
            continue
        notion_id = notion.get("id")
        if not isinstance(notion_id, str):
            continue
        targets: set[str] = set()
        _collect_recognizes(notion.get("recognition"), targets)
        targets.discard(notion_id)
        edges[notion_id] = targets
    done: set[str] = set()

    def visit(node_id: str, active: set[str]) -> bool:
        if node_id in active:
            return True
        if node_id in done:
            return False
        active.add(node_id)
        for target in edges.get(node_id, ()):
            if visit(target, active):
                return True
        active.discard(node_id)
        done.add(node_id)
        return False

    for notion_id in edges:
        if visit(notion_id, set()):
            return "profile-cycle"
    return None


def _base_producers(
    base: dict[str, object],
    producers: dict[tuple[str, str], frozenset[str]],
    ref_fields: set[tuple[str, str]],
) -> str | None:
    """Fold ratified base field producers into the rights map (refusal or None)."""
    fields = base.get("fields")
    if not isinstance(fields, list):
        return "profile-producer"
    for entry in fields:
        if not isinstance(entry, dict):
            return "profile-producer"
        type_name = entry.get("type")
        field_name = entry.get("field")
        actors = entry.get("producers")
        if (
            not isinstance(type_name, str)
            or not isinstance(field_name, str)
            or not isinstance(actors, list)
            or not all(isinstance(actor, str) for actor in actors)
        ):
            return "profile-producer"
        producers[(type_name, field_name)] = frozenset(actors)
        if entry.get("kind") == "reference":
            ref_fields.add((type_name, field_name))
    return None


def _apply_producer_delta(
    delta: object,
    types: dict[str, dict[str, object]] | None,
    producers: dict[tuple[str, str], frozenset[str]],
) -> str | None:
    """Apply one ratified producer delta (refusal or None, DESIGN §2.4.1)."""
    if not isinstance(delta, dict):
        return "profile-producer"
    native_type = delta.get("nativeType")
    path = delta.get("path")
    source = delta.get("from")
    target = delta.get("to")
    if (
        not isinstance(native_type, str)
        or not isinstance(path, str)
        or not path.startswith("/")
        or "//" in path
    ):
        return "profile-producer"
    field_name = path[1:].split("/")[0]
    if not field_name or not isinstance(source, str) or not isinstance(target, str):
        return "profile-producer"
    if types is not None:
        spec = types.get(native_type)
        if spec is None or not _type_has_field(spec, field_name):
            return "profile-producer"
    actors = producers.get((native_type, field_name))
    if actors is not None:
        if source not in actors:
            return "profile-producer"
        remaining = set(actors)
        remaining.discard(source)
        remaining.add(target)
        producers[(native_type, field_name)] = frozenset(remaining)
    return None


def _effective_producers(  # noqa: C901
    base: dict[str, object] | None,
    types: dict[str, dict[str, object]] | None,
    profile: dict[str, object],
) -> tuple[dict[tuple[str, str], frozenset[str]] | None, set[tuple[str, str]] | None, str | None]:
    """Build effective producer rights from base, descriptors and delta.

    Returns ``(producers, reference_fields, error)`` where ``producers`` maps
    ``(type, field)`` to its actor set (None when no base was supplied) and
    ``reference_fields`` holds base-declared reference-kind fields.
    """
    producers: dict[tuple[str, str], frozenset[str]] = {}
    ref_fields: set[tuple[str, str]] = set()
    if base is not None:
        error = _base_producers(base, producers, ref_fields)
        if error is not None:
            return None, None, error
    if types is not None:
        for type_name, spec in types.items():
            extra = spec.get("producerFields", {})
            if not isinstance(extra, dict):
                return None, None, "profile-producer"
            for field_name, actors in extra.items():
                key = (type_name, field_name)
                if key in producers:
                    return None, None, "profile-producer"
                if not isinstance(actors, (list, tuple)):
                    return None, None, "profile-producer"
                producers[key] = frozenset(actors)
    for delta in _as_list(profile.get("producerDelta")):
        error = _apply_producer_delta(delta, types, producers)
        if error is not None:
            return None, None, error
    resolved = dict(producers) if base is not None or types is not None else None
    refs = set(ref_fields) if base is not None else None
    return resolved, refs, None


def _named_ids(entries: object) -> set[str]:
    """Collect ``id`` names from a message/resource list."""
    names: set[str] = set()
    if not isinstance(entries, list):
        return names
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            names.add(str(entry.get("id")))
        elif isinstance(entry, str):
            names.add(entry)
    return names


def _check_render_binding(binding: object, themes: dict[str, dict[str, object]]) -> str | None:
    """Check one render binding theme/glyph reference (CR-05)."""
    if not isinstance(binding, dict):
        return None
    theme_id = binding.get("theme")
    theme = themes.get(str(theme_id)) if isinstance(theme_id, str) else None
    if theme is None:
        return "profile-symbol"
    glyphs = {g.get("id") for g in _as_list(theme.get("glyphs")) if isinstance(g, dict)}
    if binding.get("glyph") not in glyphs:
        return "profile-symbol"
    return None


def _check_notion_refs(  # noqa: C901
    profile: dict[str, object],
    recipe_ids: set[str],
    messages: set[str],
    themes: dict[str, dict[str, object]],
) -> str | None:
    """Check notion recipe/message/theme cross-references (CR-05)."""
    for notion in _as_list(profile.get("notions")):
        if not isinstance(notion, dict):
            continue
        recipe = notion.get("createRecipe")
        if recipe is not None and recipe not in recipe_ids:
            return "profile-symbol"
        for reference in _as_list(notion.get("referenceRecipes")):
            if reference not in recipe_ids:
                return "profile-symbol"
        for field_entry in _as_list(notion.get("fields")):
            if not isinstance(field_entry, dict):
                continue
            command = field_entry.get("command")
            if command is not None and command not in recipe_ids:
                return "profile-symbol"
            for key in ("label", "message"):
                label = field_entry.get(key)
                if label is not None and label not in messages:
                    return "profile-symbol"
        for binding in _as_list(notion.get("renderBindings")):
            code = _check_render_binding(binding, themes)
            if code is not None:
                return code
    return None


def _check_theme_refs(themes: dict[str, dict[str, object]], resources: set[str]) -> str | None:
    """Check theme fallback/metrics references and fallback cycles (CR-05)."""
    for theme in themes.values():
        fallback = theme.get("fallback")
        if fallback is not None and fallback not in themes:
            return "profile-symbol"
        metrics = theme.get("metricsResource")
        if metrics is not None and metrics not in resources:
            return "profile-symbol"
    seen: set[str] = set()

    def _fallback_cycle(theme_id: str, active: set[str]) -> bool:
        if theme_id in active:
            return True
        if theme_id in seen:
            return False
        active.add(theme_id)
        fallback = themes[theme_id].get("fallback")
        if isinstance(fallback, str) and _fallback_cycle(fallback, active):
            return True
        active.discard(theme_id)
        seen.add(theme_id)
        return False

    for theme_id in themes:
        if _fallback_cycle(theme_id, set()):
            return "profile-cycle"
    return None


def _check_rule_ui_refs(  # noqa: C901
    profile: dict[str, object], recipe_ids: set[str], messages: set[str]
) -> str | None:
    """Check rule/ui/export recipe and message references (CR-05)."""
    for rule in _as_list(profile.get("rules")):
        if not isinstance(rule, dict):
            continue
        if rule.get("message") not in messages:
            return "profile-symbol"
        repair = rule.get("repairRecipe")
        if repair is not None and repair not in recipe_ids:
            return "profile-symbol"
    for ui_entry in _as_list(profile.get("ui")):
        if not isinstance(ui_entry, dict):
            continue
        if ui_entry.get("recipe") not in recipe_ids:
            return "profile-symbol"
    for export in _as_list(profile.get("exports")):
        if not isinstance(export, dict):
            continue
        for recipe in _as_list(export.get("recipes")):
            if recipe not in recipe_ids:
                return "profile-symbol"
    return None


def _check_closed_refs(
    profile: dict[str, object],
    recipe_ids: set[str],
) -> str | None:
    """Check notion/recipe/theme/message cross-references (CR-05)."""
    themes: dict[str, dict[str, object]] = {}
    for entry in _as_list(profile.get("themes")):
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            themes[str(entry.get("id"))] = entry
    messages = _named_ids(profile.get("messages"))
    resources = _named_ids(profile.get("resources"))
    code = _check_notion_refs(profile, recipe_ids, messages, themes)
    if code is not None:
        return code
    code = _check_theme_refs(themes, resources)
    if code is not None:
        return code
    return _check_rule_ui_refs(profile, recipe_ids, messages)


def _check_lot4_records(  # noqa: C901, PLR0911, PLR0912
    profile: dict[str, object],
    notions_raw: object,
    recipes_raw: object,
    registry: RegistrySet,
) -> str | None:
    """Run the lot-4 glyph, token and export checks (CR-09/CR-11, spec §8.1)."""
    from bpmn_io.profile._export_ir import check_emit, check_export_record  # noqa: PLC0415
    from bpmn_io.profile._render_tokens import validate_token_list  # noqa: PLC0415
    from bpmn_io.profile._templates import check_glyph  # noqa: PLC0415

    for theme in _as_list(profile.get("themes")):
        if not isinstance(theme, dict):
            continue
        for glyph in _as_list(theme.get("glyphs")):
            if check_glyph(glyph) is not None:
                return "profile-glyph-shape"
        code = validate_token_list(theme.get("tokens", []), registry)
        if code is not None:
            return code
        for occurrence in _as_list(theme.get("syntheticOccurrences")):
            if not isinstance(occurrence, dict):
                continue
            code = validate_token_list(occurrence.get("tokens", []), registry)
            if code is not None:
                return code
    for notion in _as_list(notions_raw):
        if not isinstance(notion, dict):
            continue
        for binding in _as_list(notion.get("renderBindings")):
            if not isinstance(binding, dict):
                continue
            code = validate_token_list(binding.get("tokens", []), registry)
            if code is not None:
                return code
    for recipe in _as_list(recipes_raw):
        if not isinstance(recipe, dict) or recipe.get("phase") != "export":
            continue
        for step in _as_list(recipe.get("steps")):
            if not isinstance(step, dict) or step.get("op") != "emit":
                continue
            code = check_emit(step)
            if code is not None:
                return code
    for export in _as_list(profile.get("exports")):
        if not isinstance(export, dict):
            continue
        code = check_export_record(export)
        if code is not None:
            return code
    return None


def _check_export_migration_phases(
    profile: dict[str, object], recipes: dict[str, dict[str, object]]
) -> str | None:
    """Check export/migration recipe phase admission (CR-11/CR-12)."""
    for export in _as_list(profile.get("exports")):
        if not isinstance(export, dict):
            continue
        for recipe in _as_list(export.get("recipes")):
            known = recipes.get(str(recipe))
            if known is not None and known.get("phase") != "export":
                return "profile-type"
    for migration in _as_list(profile.get("migrations")):
        if not isinstance(migration, dict):
            continue
        for recipe in _as_list(migration.get("recipes")):
            known = recipes.get(str(recipe))
            if known is None:
                return "profile-symbol"
            if known.get("phase") != "migrate":
                return "profile-type"
    return None


def compile_profile(  # noqa: C901, PLR0912, PLR0911, PLR0915
    validated: ValidatedProfile,
    registry_set: RegistrySet | None = None,
    descriptor_context: DescriptorContext | None = None,
    base: dict[str, object] | None = None,
) -> PureResult:
    """Compile one validated profile with closed references and registries.

    Applies the §2.4.1 rules CR-01 through CR-14 in order and returns the
    first refusal code. Unknown operators, mismatched orders, bad bounds,
    duplicate symbols, cycles, authority gaps, identity errors, presentation
    errors, export errors, migration endpoint errors, fallback errors and
    phase errors refuse with their mapped codes.

    ``descriptor_context`` supplies the descriptor type index (type
    existence, path admission) and ``base`` the ratified base field
    producers; without them only descriptor-free checks apply and no
    ambient descriptor is consulted.
    """
    registry = registry_set or _default_registry()
    profile = validated.profile

    # CR-01 capabilities: unique known IDs and operator coverage.
    capabilities = profile.get("capabilities")
    if not isinstance(capabilities, list):
        return PureRefused(code="profile-capability")
    seen_caps: set[str] = set()
    for name in capabilities:
        if not isinstance(name, str) or name in seen_caps:
            return PureRefused(code="profile-capability")
        seen_caps.add(name)
        if name not in _KNOWN_CAPABILITIES and name not in registry.capabilities:
            return PureRefused(code="profile-capability")

    notions_raw = profile.get("notions")
    rules_raw = profile.get("rules")
    recipes_raw = profile.get("recipes")
    if not isinstance(notions_raw, list) or not isinstance(rules_raw, list):
        return PureRefused(code="profile-symbol")
    if not isinstance(recipes_raw, list):
        return PureRefused(code="profile-symbol")

    notions: set[str] = set()
    for _entry in notions_raw:
        if not isinstance(_entry, dict):
            return PureRefused(code="profile-symbol")
        _nid = _entry.get("id")
        if not isinstance(_nid, str) or _nid in notions:
            return PureRefused(code="profile-symbol")
        notions.add(_nid)
    recipe_ids: set[str] = set()
    recipes: dict[str, dict[str, object]] = {}
    for _entry in recipes_raw:
        if not isinstance(_entry, dict):
            return PureRefused(code="profile-symbol")
        _rid = _entry.get("id")
        if not isinstance(_rid, str) or _rid in recipe_ids:
            return PureRefused(code="profile-symbol")
        recipe_ids.add(_rid)
        recipes[_rid] = _entry
    rule_ids: set[str] = set()
    for _entry in rules_raw:
        if not isinstance(_entry, dict):
            return PureRefused(code="profile-symbol")
        _uid = _entry.get("id")
        if not isinstance(_uid, str) or _uid in rule_ids:
            return PureRefused(code="profile-symbol")
        rule_ids.add(_uid)

    # Notion group/kind check (CR-09 subset) before predicate walks.
    for notion in notions_raw:
        if not isinstance(notion, dict):
            return PureRefused(code="profile-notion-kind")
        has_facet = notion.get("facet") is True
        group = notion.get("exclusiveGroup")
        if has_facet == bool(isinstance(group, str) and group):
            return PureRefused(code="profile-notion-kind")

    # CR-01 operator signatures over every AST position (bounded walk).
    used_families: set[str] = set()
    code = _check_op_signatures(profile, registry, used_families)
    if code is not None:
        return PureRefused(code=code)

    types = dict(descriptor_context.types) if descriptor_context is not None else None
    producers, ref_fields, error = _effective_producers(base, types, profile)
    if error is not None:
        return PureRefused(code=error)

    def _new_scope(
        bindings: set[str], btypes: dict[str, str], params: dict[str, str] | None = None
    ) -> _Scope:
        return _Scope(
            notions=set(notions),
            bindings=set(bindings),
            btypes=dict(btypes),
            params=dict(params or {}),
            types=types,
            producers=producers,
            ref_fields=ref_fields,
            used_families=used_families,
        )

    # Typed walks: notions with recognition scope (CR-02/03/05).
    for notion in notions_raw:
        if not isinstance(notion, dict):
            continue
        native_types = notion.get("nativeTypes", [])
        self_type = "native"
        if (
            isinstance(native_types, list)
            and len(native_types) == 1
            and isinstance(native_types[0], str)
        ):
            self_type = native_types[0]
        scope = _new_scope({"root", "self", "bindingOwner"}, {"self": self_type})
        for key in ("recognition",):
            predicate = notion.get(key)
            if predicate is not None:
                code = _check_predicate(predicate, scope)
                if code is not None:
                    return PureRefused(code=code)
        for field_entry in _as_list(notion.get("fields")):
            if not isinstance(field_entry, dict):
                continue
            for key in ("visible", "mutable"):
                predicate = field_entry.get(key)
                if predicate is not None:
                    code = _check_predicate(predicate, scope)
                    if code is not None:
                        return PureRefused(code=code)
        for binding in _as_list(notion.get("renderBindings")):
            if not isinstance(binding, dict):
                continue
            label = binding.get("label")
            if label is not None:
                code = _check_value(label, "predicate", scope, None)
                if code is not None:
                    return PureRefused(code=code)

    # Typed walks: rules with rule scope.
    for rule in rules_raw:
        if not isinstance(rule, dict):
            continue
        scope = _new_scope({"root", "self", "bindingOwner"}, {})
        code = _check_selector(rule.get("select"), scope)
        if code is not None:
            return PureRefused(code=code)
        scope.btypes["self"] = _infer_selector_type(rule.get("select"), scope)
        for binding in _as_list(rule.get("bindings")):
            if not isinstance(binding, dict):
                return PureRefused(code="profile-type")
            code = _check_selector(binding.get("select"), scope)
            if code is not None:
                return PureRefused(code=code)
            alias = binding.get("as")
            cardinality = binding.get("cardinality")
            if not isinstance(alias, str) or not alias:
                return PureRefused(code="profile-type")
            if cardinality not in ("one", "zeroOrOne", "first"):
                return PureRefused(code="profile-type")
            fallbacks = binding.get("fallbacks")
            if fallbacks is not None and cardinality != "first":
                return PureRefused(code="profile-bind-fallbacks")
            if isinstance(fallbacks, list):
                for entry in fallbacks:
                    code = _check_selector(entry, scope)
                    if code is not None:
                        return PureRefused(code=code)
            scope.bindings.add(alias)
            scope.btypes[alias] = _infer_selector_type(binding.get("select"), scope)
        code = _check_predicate(rule.get("assert"), scope)
        if code is not None:
            return PureRefused(code=code)

    # Typed walks: recipes with recipe scope, collecting write demands.
    demands: dict[str, list[dict[str, object]]] = {}
    for recipe in recipes_raw:
        if not isinstance(recipe, dict):
            continue
        phase = recipe.get("phase")
        if phase not in _PHASES:
            return PureRefused(code="profile-action-phase")
        recipe_params: dict[str, str] = {}
        for param in _as_list(recipe.get("parameters")):
            if not isinstance(param, dict):
                return PureRefused(code="profile-type")
            name = param.get("name")
            if not isinstance(name, str) or name in recipe_params:
                return PureRefused(code="profile-symbol")
            param_type = param.get("type")
            recipe_params[name] = param_type if isinstance(param_type, str) else "unknown"
        scope = _new_scope({"root", "self"}, {}, recipe_params)
        for name, param_type in recipe_params.items():
            if param_type == "element":
                scope.bindings.add(name)
                scope.btypes[name] = "native"
        if phase == "export":
            scope.bindings.add("render")
        recipe_phase = "export" if phase == "export" else "recipe"
        code = _check_selector(recipe.get("select"), scope, recipe_phase)
        if code is not None:
            return PureRefused(code=code)
        scope.btypes["self"] = _infer_selector_type(recipe.get("select"), scope)
        when = recipe.get("when")
        if when is not None:
            code = _check_predicate(when, scope, recipe_phase)
            if code is not None:
                return PureRefused(code=code)
        steps = recipe.get("steps")
        if not isinstance(steps, list) or not steps:
            return PureRefused(code="profile-type")
        recipe_demands: list[dict[str, object]] = []
        for step in steps:
            code = _check_action(step, str(phase), scope, recipe_demands)
            if code is not None:
                return PureRefused(code=code)
        recipe_id = recipe.get("id")
        if isinstance(recipe_id, str):
            demands[recipe_id] = recipe_demands

    # Secondary AST positions with minimal scope (ui/exports gates, themes).
    plain_scope = _new_scope({"root", "self"}, {})
    for ui_entry in _as_list(profile.get("ui")):
        if not isinstance(ui_entry, dict):
            continue
        when = ui_entry.get("when")
        if when is not None:
            code = _check_predicate(when, plain_scope)
            if code is not None:
                return PureRefused(code=code)
    for export in _as_list(profile.get("exports")):
        if not isinstance(export, dict):
            continue
        for capability in _as_list(export.get("capabilities")):
            if not isinstance(capability, dict):
                continue
            when = capability.get("when")
            if when is not None:
                # Lot 4 (DESIGN §10.2): capability predicates evaluate per R
                # occurrence with self, root, render, page and semantic.
                capability_scope = _new_scope(
                    {"root", "self", "render", "page", "semantic"},
                    {"page": "page"},
                )
                code = _check_predicate(when, capability_scope, "export")
                if code is not None:
                    return PureRefused(code=code)
    for theme in _as_list(profile.get("themes")):
        if not isinstance(theme, dict):
            continue
        for occurrence in _as_list(theme.get("syntheticOccurrences")):
            if not isinstance(occurrence, dict):
                continue
            code = _check_selector(occurrence.get("select"), plain_scope)
            if code is not None:
                return PureRefused(code=code)
            label = occurrence.get("label")
            if label is not None:
                code = _check_value(label, "predicate", plain_scope, None)
                if code is not None:
                    return PureRefused(code=code)

    # Lot 4 glyph, token and export checks (CR-09/CR-11, spec §8.1).
    code = _check_lot4_records(profile, notions_raw, recipes_raw, registry)
    if code is not None:
        return PureRefused(code=code)

    # CR-01 family capabilities for every used consumer.
    if rules_raw or profile.get("validation"):
        used_families.add("profile-lint/1")
    for family in sorted(used_families):
        if family not in capabilities:
            return PureRefused(code="profile-capability")

    # CR-05 recognition cycles, then closed notion/recipe/theme references.
    code = _recognition_cycle(notions_raw)
    if code is not None:
        return PureRefused(code=code)
    code = _check_closed_refs(profile, recipe_ids)
    if code is not None:
        return PureRefused(code=code)

    # CR-06 write-set: required demands equal declared writes exactly.
    for recipe in recipes_raw:
        if not isinstance(recipe, dict):
            continue
        recipe_id = recipe.get("id")
        declared = recipe.get("writes", [])
        if not isinstance(declared, list) or not isinstance(recipe_id, str):
            return PureRefused(code="profile-write-set")
        required = demands.get(recipe_id, [])
        if sorted(jcs(entry) for entry in required) != sorted(jcs(entry) for entry in declared):
            return PureRefused(code="profile-write-set")

    # CR-11/CR-12 recipe phase admission for exports and migrations.
    code = _check_export_migration_phases(profile, recipes)
    if code is not None:
        return PureRefused(code=code)

    # CR-12 migration endpoints: target self, external source pin.
    migrations = profile.get("migrations")
    if isinstance(migrations, list):
        own_digest = validated.digest
        for migration in migrations:
            if not isinstance(migration, dict):
                return PureRefused(code="profile-migration-endpoint")
            if migration.get("to") != "self":
                return PureRefused(code="profile-migration-endpoint")
            source = migration.get("from")
            if not isinstance(source, dict):
                return PureRefused(code="profile-migration-endpoint")
            if source.get("sha256") == own_digest:
                return PureRefused(code="profile-migration-endpoint")

    validation_raw = profile.get("validation")
    validation_entries = tuple(validation_raw) if isinstance(validation_raw, list) else ()
    owned_profile = copy.deepcopy(profile)
    identity: dict[str, object] = {
        "mechanismVersion": profile.get("mechanismVersion"),
        "schemaVersion": profile.get("schemaVersion"),
        "profile": profile.get("profile"),
        "version": profile.get("version"),
        "sha256": digest(profile),
        "base": copy.deepcopy(profile.get("base")),
        "descriptors": copy.deepcopy(profile.get("descriptors")),
    }
    compiled = CompiledProfile(
        profile_digest=validated.digest,
        notions={
            str(n.get("id")): {
                "recognition": copy.deepcopy(n.get("recognition")),
                "nativeTypes": list(n.get("nativeTypes", [])),
            }
            for n in notions_raw
            if isinstance(n, dict)
        },
        recipes={key: copy.deepcopy(value) for key, value in recipes.items()},
        rules={str(r.get("id")): copy.deepcopy(r) for r in rules_raw if isinstance(r, dict)},
        descriptor_digest=(
            descriptor_context.digest if descriptor_context is not None else validated.digest
        ),
        registry_digest=digest(sorted(registry.capabilities)),
        validation=copy.deepcopy(validation_entries),
        profile=owned_profile,
        identity=identity,
        assets=dict(validated.assets),
        render_registry=copy.deepcopy(registry.render_tokens),
    )
    return PureSuccess(payload=compiled)
