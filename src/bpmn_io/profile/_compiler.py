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
from bpmn_io.profile._ui import UiIndex, build_ui_index, check_ui_rules

if TYPE_CHECKING:
    from bpmn_io.profile._loader import ValidatedProfile
    from bpmn_io.profile._static import Typing

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

#: Selector admission lives in ``_static`` (``compiler-static.ts:151-200``).
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
    "reparent": frozenset({"edit", "convert", "migrate", "normalize"}),
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
    not here. ``identity`` is the §5.1 record, ``types`` the descriptor index
    with facets, ``producers`` the effective producer matrix,
    ``ref_fields`` the base-declared reference-kind fields (including
    ID-valued scalars) and ``base_types`` the effective-base admitted type
    names; the latter four stay ``None`` unless the profile was compiled
    with its descriptor context and effective base (C/N refuse
    ``descriptor-mismatch`` otherwise).
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
    # Lot 3 extension (B7): descriptor types and producers for C/N, the
    # effective-base type names and the sorted capability names.
    types: dict[str, dict[str, object]] | None = None
    producers: dict[tuple[str, str], frozenset[str]] | None = None
    ref_fields: frozenset[tuple[str, str]] | None = None
    base_types: frozenset[str] | None = None
    capabilities: tuple[str, ...] = ()
    # Lot 5 extension (CR-10): compiled UI/field/message index, attached
    # between CR-09 and CR-11; None when the profile carries no UI section.
    ui: UiIndex | None = None


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


#: Render record typing lives in ``_static`` (``compiler-static.ts:10-15``);
#: the legacy walk below only records families, demands and
#: descriptor-independent checks.
def _as_list(value: object) -> list[object]:
    """Return ``value`` when it is a list, else an empty list (mypy-safe iteration)."""
    return value if isinstance(value, list) else []


#: Bounded generic walk size (DESIGN §2.5 host resource limit).
_MAX_COMPILE_NODES: int = 4000000


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


def _normalize_type_record(  # noqa: PLR0911 - one return per facet failure
    name: object, record: object
) -> dict[str, object] | None:
    """Normalize one descriptor type to its closed facets (None when malformed).

    Keeps ``scalars``, ``containment`` and ``references`` plus the ``id``
    admission flag, the optional ``many`` (multi-valued reference
    properties) and ``single`` (single-valued containment properties)
    facets, and optional ``producerFields``; every facet defaults to
    empty when absent (an absent ``id`` flag defaults to admitted). The
    normalized form is freshly built, so the context owns its index.
    """
    if not isinstance(name, str) or not isinstance(record, dict):
        return None
    scalars = _normalize_string_list(record.get("scalars", []))
    admitted = _normalize_string_map(record.get("containment", {}))
    linked = _normalize_string_map(record.get("references", {}))
    producers = _normalize_producer_fields(record.get("producerFields", []))
    many = _normalize_string_list(record.get("many", []))
    single = _normalize_string_list(record.get("single", []))
    id_flag = record.get("id", True)
    scalar_types = record.get("scalarTypes", {})
    bases = record.get("extends", [])
    if scalars is None or admitted is None or linked is None or producers is None:
        return None
    if many is None or single is None:
        return None
    if not isinstance(id_flag, bool):
        return None
    if not isinstance(scalar_types, dict) or not all(
        isinstance(value, str) for value in scalar_types.values()
    ):
        return None
    if not isinstance(bases, list) or not all(isinstance(base, str) for base in bases):
        return None
    return {
        "scalars": scalars,
        "containment": admitted,
        "references": linked,
        "id": id_flag,
        "producerFields": producers,
        "many": many,
        "single": single,
        "scalarTypes": dict(scalar_types),
        "extends": tuple(bases),
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


def _index_package_types(
    descriptor: object,
    types: dict[str, dict[str, object]],
    extends: dict[str, list[str]],
) -> str | None:
    """Merge one package's type document into the index (refusal or None).

    ``extends`` collects each type's raw supertype list for the post-pass
    inheritance resolution.
    """
    if not isinstance(descriptor, dict) or not isinstance(descriptor.get("types"), dict):
        return "descriptor-mismatch"
    for type_name, record in descriptor["types"].items():
        if type_name in types:
            return "descriptor-mismatch"
        normalized = _normalize_type_record(type_name, record)
        if normalized is None:
            return "descriptor-mismatch"
        types[type_name] = normalized
        if isinstance(record, dict):
            bases = record.get("extends", [])
            if bases:
                if not isinstance(bases, list) or not all(isinstance(base, str) for base in bases):
                    return "descriptor-mismatch"
                extends[type_name] = list(bases)
    return None


def _merge_supertype(merged: dict[str, object], parent: dict[str, object]) -> bool:
    """Merge one supertype's facets under the subtype's (False when malformed).

    List facets union with the subtype's items first; map facets keep the
    subtype's entry on conflict.
    """
    for key in ("scalars", "many", "single"):
        ours = merged.get(key)
        theirs = parent.get(key)
        if not isinstance(ours, list) or not isinstance(theirs, (list, tuple)):
            return False
        ours.extend(item for item in theirs if item not in ours)
    for key in ("containment", "references", "producerFields", "scalarTypes"):
        ours_map = merged.get(key)
        theirs_map = parent.get(key)
        if not isinstance(ours_map, dict) or not isinstance(theirs_map, dict):
            return False
        for prop, admitted in theirs_map.items():
            ours_map.setdefault(prop, admitted)
    return True


def _fresh_facets(own: dict[str, object]) -> dict[str, object] | None:
    """Copy one normalized type's facets (None when malformed)."""
    merged: dict[str, object] = {}
    for key in ("scalars", "many", "single"):
        facet = own.get(key, ())
        if not isinstance(facet, (list, tuple)):
            return None
        merged[key] = list(facet)
    bases = own.get("extends", ())
    merged["extends"] = tuple(bases) if isinstance(bases, (list, tuple)) else ()
    for key in ("containment", "references", "producerFields", "scalarTypes"):
        facet = own.get(key, {})
        if not isinstance(facet, dict):
            return None
        merged[key] = dict(facet)
    merged["id"] = own.get("id", True)
    return merged


def _freeze_lists(merged: dict[str, object]) -> None:
    """Freeze merged list facets back to the index tuple convention."""
    for key in ("scalars", "many", "single"):
        facet = merged.get(key)
        if isinstance(facet, list):
            merged[key] = tuple(facet)


def _inherit_facets(
    types: dict[str, dict[str, object]], extends: dict[str, list[str]]
) -> str | None:
    """Resolve descriptor ``extends`` inheritance (refusal or None).

    Each subtype merges its supertypes' facets under its own declarations
    (own containment/reference/producer entries win); unknown supertypes
    and inheritance cycles refuse ``descriptor-mismatch``.
    """
    resolved: dict[str, dict[str, object]] = {}

    def _resolve(name: str, stack: tuple[str, ...]) -> dict[str, object] | None:
        cached = resolved.get(name)
        if cached is not None:
            return cached
        if name in stack or name not in types:
            return None
        merged = _fresh_facets(types[name])
        if merged is None:
            return None
        for base in extends.get(name, []):
            parent = _resolve(base, (*stack, name))
            if parent is None or not _merge_supertype(merged, parent):
                return None
        _freeze_lists(merged)
        resolved[name] = merged
        return merged

    for type_name in extends:
        if _resolve(type_name, ()) is None:
            return "descriptor-mismatch"
        types[type_name] = resolved[type_name]
    return None


def create_descriptor_context(  # noqa: PLR0911 - one return per pin failure
    packages: list[dict[str, object]],
) -> PureResult:
    """Build one descriptor context from pinned packages.

    Each package carries ``id``, ``version``, ``sha256`` and immutable UTF-8
    ``descriptorBytes`` whose raw SHA-256 must match. IDs stay unique, and
    the ``types`` document inside the bytes builds the normalized
    descriptor index (scalars, containment, references, id admission,
    ``many``/``single`` facets). Duplicate package or type definitions
    refuse ``descriptor-mismatch``. The context digest is the DESIGN §9.2
    formula over the descriptor pins sorted by id.
    """
    seen: set[str] = set()
    types: dict[str, dict[str, object]] = {}
    extends: dict[str, list[str]] = {}
    pins: list[dict[str, object]] = []
    for entry in packages:
        package_id = entry.get("id")
        want = entry.get("sha256")
        version = entry.get("version", "")
        if not isinstance(package_id, str) or not isinstance(want, str):
            return PureRefused(code="descriptor-mismatch")
        if not isinstance(version, str):
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
        code = _index_package_types(descriptor, types, extends)
        if code is not None:
            return PureRefused(code=code)
        pins.append({"id": package_id, "version": version, "sha256": want})
    code = _inherit_facets(types, extends)
    if code is not None:
        return PureRefused(code=code)
    pins.sort(key=lambda pin: str(pin["id"]).encode("utf-16-be"))
    context_digest = digest(pins)
    owned = tuple(copy.deepcopy(entry) for entry in packages)
    context = DescriptorContext(packages=owned, types=types, digest=context_digest)
    return PureSuccess(payload=context)


def _check_value(node: object, context: str, scope: _Scope, phase: str | None = None) -> str | None:
    """Record value families (typing lives in ``_static``)."""
    _ = context, phase
    _record_families(node, scope.used_families)
    return None


def _record_families(node: object, used: set[str]) -> None:
    """Record selector/render families of one AST (old visit points)."""
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if isinstance(current.get("via"), str) and "from" in current:
                used.add("selectors/1")
                if current.get("via") in _RENDER_VIA:
                    used.add("render-data/1")
            if current.get("op") == "outputId":
                used.add("render-data/1")
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def _check_predicate(node: object, scope: _Scope, context_phase: str = "rule") -> str | None:
    """Record predicate families (typing lives in ``_static``)."""
    _ = context_phase
    _record_families(node, scope.used_families)
    return None


def _check_selector(
    node: object,
    scope: _Scope,
    context_phase: str = "rule",
) -> str | None:
    """Record selector families (typing lives in ``_static``)."""
    _ = context_phase
    _record_families(node, scope.used_families)
    return None


def _authorize(scope: _Scope, btype: str, field_name: str, phase: str) -> str | None:
    """Check one native write against effective producer rights (CR-06).

    The phase actor is ``code`` for complete/normalize and ``editor``
    otherwise; export has no native write authority. A known native type
    checks its own producers; an unknown binding checks every admitted
    target type supporting the field (DESIGN §2.4.1 CR-06). A candidate
    with no producer row is not an admitted write target for the field
    and is skipped.
    """
    if (
        scope.producers is None
        or scope.types is None
        or not field_name
        or _support_unindexed(scope, btype)
    ):
        return None
    actor = "code" if phase in ("complete", "normalize") else "editor"
    if btype in scope.types:
        if actor not in scope.producers.get((btype, field_name), frozenset()):
            return "profile-producer"
        return None
    candidates = [name for name, spec in scope.types.items() if _type_has_field(spec, field_name)]
    if not candidates:
        return "profile-type"
    for candidate in candidates:
        rights = scope.producers.get((candidate, field_name))
        if rights is not None and actor not in rights:
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
            demands.append({"binding": parent, "path": "/" + prop, "mode": "reparent"})
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
            _check_selector(related, scope, context_phase)
        demands.append({"binding": target, "path": "", "mode": "placement"})
        return None
    if op == "emit":
        fields = step.get("fields", [])
        if not isinstance(fields, list):
            return "profile-export-field"
        for entry in fields:
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
                return "profile-export-field"
            _check_value(entry.get("value"), "emit-fields", scope, phase)
        parent = step.get("parent")
        if parent is not None:
            _check_value(parent, "emit-parent", scope, phase)
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
        # B3: full ensure checking (as-alias registration included).
        return _check_ensure(step, phase, scope, demands)
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


#: Native types an ``ensure`` step may allocate (DESIGN §5.2 support objects).
_SUPPORT_ENSURE_TYPES: frozenset[str] = frozenset(
    {"bpmn:Collaboration", "bpmn:Participant", "bpmn:LaneSet", "bpmn:Lane"}
)


def _support_unindexed(scope: _Scope, native_type: str) -> bool:
    """Return whether one support-ensure type lacks a descriptor entry.

    Support objects (§5.2) are native-managed: a profile may ensure them
    without declaring them, in which case descriptor-bound checks degrade
    instead of refusing.
    """
    return (
        native_type in _SUPPORT_ENSURE_TYPES
        and scope.types is not None
        and native_type not in scope.types
    )


def _check_ensure_identity(
    step: dict[str, object], native_type: str, phase: str, scope: _Scope
) -> str | None:
    """Validate one ensure's identity parts and creation fields (CR-07)."""
    for key in ("ownerId", "key"):
        if key not in step:
            return "profile-type"
        _check_value(step.get(key), "create-field", scope, phase)
    if not isinstance(step.get("slot"), str) or not step.get("slot"):
        return "profile-type"
    code = _check_create_fields(step, native_type, phase, scope)
    if code is not None:
        return code
    return None


def _check_ensure(  # noqa: PLR0911 - one return per ensure failure
    step: dict[str, object], phase: str, scope: _Scope, demands: list[dict[str, object]]
) -> str | None:
    """Validate one ensure step with support restriction and demands (CR-05/06/07)."""
    native_type = step.get("type")
    if not isinstance(native_type, str) or not native_type:
        return "profile-type"
    if native_type not in _SUPPORT_ENSURE_TYPES:
        return "profile-producer"
    owner = step.get("owner")
    parent = step.get("parent")
    if not isinstance(owner, str) or not isinstance(parent, str):
        return "profile-type"
    if owner not in scope.bindings or parent not in scope.bindings:
        return "profile-symbol"
    code = _check_ensure_identity(step, native_type, phase, scope)
    if code is not None:
        return code
    code = _check_create_parent(step, native_type, phase, scope, demands)
    if code is not None:
        return code
    demands.append({"binding": "envelope", "path": "/bindings", "mode": "binding"})
    alias = step.get("as")
    if not isinstance(alias, str) or not alias:
        return "profile-type"
    scope.bindings.add(alias)
    scope.btypes[alias] = native_type
    return None


def _check_bind(step: dict[str, object], scope: _Scope, context_phase: str) -> str | None:
    """Validate one bind step and register its alias (CR-05/CR-13)."""
    selector = step.get("select")
    _check_selector(selector, scope, context_phase)
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
            _check_selector(entry, scope, context_phase)
    scope.bindings.add(alias)
    scope.btypes[alias] = "native"
    return None


def _check_create_parent(
    step: dict[str, object],
    native_type: str,
    phase: str,
    scope: _Scope,
    demands: list[dict[str, object]],
) -> str | None:
    """Record one create parent/property demand (typing lives in ``_static``)."""
    _ = native_type, phase
    parent = step.get("parent")
    prop = step.get("property")
    if parent is None and prop is None:
        return None
    if not isinstance(parent, str) or not isinstance(prop, str):
        return "profile-type"
    if parent not in scope.bindings:
        return "profile-symbol"
    demands.append({"binding": parent, "path": "/" + prop, "mode": "create"})
    return None


def _check_create_field(
    entry: object,
    native_type: str,
    phase: str,
    scope: _Scope,
) -> str | None:
    """Record one create field value family (typing lives in ``_static``)."""
    _ = native_type
    if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
        return "profile-type"
    _check_value(entry.get("value"), "create-field", scope, phase)
    return None


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
    """Validate one create step shape and record demands (typing in ``_static``)."""
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
    for key in ("ownerId", "key"):
        if key in step:
            _check_value(step.get(key), "create-field", scope, phase)
    code = _check_create_fields(step, native_type, phase, scope)
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
    """Validate one set/unset step shape and record its demand (CR-06)."""
    target, path, head, error = _write_target(step, scope)
    if error is not None:
        return error
    _ = head
    if op == "set":
        _check_value(step.get("value"), "set", scope, phase)
    demands.append({"binding": target, "path": path, "mode": op})
    return None


def _check_assign_ref(
    step: dict[str, object],
    phase: str,
    scope: _Scope,
    demands: list[dict[str, object]],
) -> str | None:
    """Validate one assignRef step shape and record its demand (CR-06)."""
    target, path, head, error = _write_target(step, scope)
    if error is not None:
        return error
    _ = head
    values = step.get("values")
    if not isinstance(values, list):
        return "profile-type"
    for entry in values:
        _check_value(entry, "assignRef-values", scope, phase)
    if step.get("mode") not in ("replace", "appendUnique", "remove"):
        return "profile-type"
    demands.append({"binding": target, "path": path, "mode": "reference"})
    return None


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


def _base_type_names(base: dict[str, object] | None) -> frozenset[str] | None:
    """Return the effective-base admitted type names (None without a base)."""
    if base is None:
        return None
    declared = base.get("types")
    if not isinstance(declared, list):
        return frozenset()
    return frozenset(item for item in declared if isinstance(item, str))


def _base_producers(  # noqa: PLR0911 - one return per base failure
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
    scalars = base.get("idRefScalars", [])
    if not isinstance(scalars, list):
        return "profile-producer"
    for item in scalars:
        if not isinstance(item, str) or "." not in item:
            return "profile-producer"
        owner, _, member = item.rpartition(".")
        if not owner or not member:
            return "profile-producer"
        ref_fields.add((owner, member))
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


def _supertypes(descriptor_context: DescriptorContext | None) -> dict[str, tuple[str, ...]]:
    """Return the own ``extends`` lists of every descriptor type (JS descriptorIndex)."""
    found: dict[str, tuple[str, ...]] = {}
    if descriptor_context is None:
        return found
    for type_name, record in descriptor_context.types.items():
        bases = record.get("extends", ()) if isinstance(record, dict) else ()
        if not isinstance(bases, (list, tuple)):
            continue
        found[type_name] = tuple(base for base in bases if isinstance(base, str))
    return found


def _static_typing(
    profile: dict[str, object],
    types: dict[str, dict[str, object]] | None,
    descriptor_context: DescriptorContext | None,
    base: dict[str, object] | None,
    producers: dict[tuple[str, str], frozenset[str]] | None,
) -> Typing:
    """Build the ``_static.Typing`` authority of one compilation."""
    from bpmn_io.profile import _static  # noqa: PLC0415 - typing core stays lazily bound

    notions = {
        str(entry.get("id")): entry
        for entry in _as_list(profile.get("notions"))
        if isinstance(entry, dict)
    }
    if types is None:
        return _static.Typing(descriptors=None, native_types=(), notions=notions)
    declared = base.get("types") if base is not None else None
    if isinstance(declared, list):
        native = tuple(item for item in declared if isinstance(item, str))
    else:
        native = tuple(types)
    id_refs = frozenset(
        item
        for item in _as_list(base.get("idRefScalars") if base is not None else None)
        if isinstance(item, str)
    )
    grants: dict[tuple[str, str, str], frozenset[str]] | None = None
    if base is not None and producers is not None:
        grants = {}
        for entry in _as_list(base.get("fields")):
            if isinstance(entry, dict):
                key = (str(entry.get("type")), str(entry.get("field")))
                grants[(key[0], key[1], str(entry.get("kind")))] = producers.get(key, frozenset())
    return _static.Typing(
        descriptors=types,
        native_types=native,
        id_ref_scalars=id_refs,
        notions=notions,
        grants=grants,
        supertypes=_supertypes(descriptor_context),
        base_fields=frozenset(
            (str(entry.get("type")), str(entry.get("field")))
            for entry in _as_list(base.get("fields") if base is not None else None)
            if isinstance(entry, dict)
        )
        if base is not None
        else None,
    )


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

    # Static admission (``compiler-static.ts``): the structural pre-pass then
    # the whole-profile walk, the only typing authority of this compilation.
    from bpmn_io.profile import _static  # noqa: PLC0415 - typing core stays lazily bound

    typing = _static_typing(profile, types, descriptor_context, base, producers)
    try:
        for _notion in notions_raw:
            if isinstance(_notion, dict):
                _static.structure_predicate(_notion.get("recognition"))
        for _rule in rules_raw:
            if isinstance(_rule, dict):
                _static.structure_selector(_rule.get("select"))
                _static.structure_predicate(_rule.get("assert"))
                for _bind in _as_list(_rule.get("bindings")):
                    if isinstance(_bind, dict):
                        _static.structure_bind(_bind)
        for _recipe in recipes_raw:
            if isinstance(_recipe, dict):
                _static.structure_recipe(_recipe)
        _static.static_walk(profile, typing)
    except _static.StaticRefusal as refusal:
        return PureRefused(code=refusal.code)

    def _new_scope(
        bindings: set[str], btypes: dict[str, str], params: dict[str, str] | None = None
    ) -> _Scope:
        # The legacy walk below records families and demands only: no
        # descriptor index, no producers, no reference fields.
        return _Scope(
            notions=set(notions),
            bindings=set(bindings),
            btypes=dict(btypes),
            params=dict(params or {}),
            types=None,
            producers=None,
            ref_fields=None,
            used_families=used_families,
        )

    # Family/demand walks: notions with recognition scope (CR-02/03/05).
    for notion in notions_raw:
        if not isinstance(notion, dict):
            continue
        scope = _new_scope({"root", "self", "bindingOwner"}, {})
        for key in ("recognition",):
            predicate = notion.get(key)
            if predicate is not None:
                _check_predicate(predicate, scope)
        for field_entry in _as_list(notion.get("fields")):
            if not isinstance(field_entry, dict):
                continue
            for key in ("visible", "mutable"):
                predicate = field_entry.get(key)
                if predicate is not None:
                    _check_predicate(predicate, scope)
        for binding in _as_list(notion.get("renderBindings")):
            if not isinstance(binding, dict):
                continue
            label = binding.get("label")
            if label is not None:
                _check_value(label, "predicate", scope, None)

    # Family/demand walks: rules with rule scope.
    for rule in rules_raw:
        if not isinstance(rule, dict):
            continue
        scope = _new_scope({"root", "self", "bindingOwner"}, {})
        _check_selector(rule.get("select"), scope)
        scope.btypes["self"] = "native"
        for binding in _as_list(rule.get("bindings")):
            if not isinstance(binding, dict):
                return PureRefused(code="profile-type")
            _check_selector(binding.get("select"), scope)
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
                    _check_selector(entry, scope)
            scope.bindings.add(alias)
            scope.btypes[alias] = "native"
        _check_predicate(rule.get("assert"), scope)

    # Family/demand walks: recipes with recipe scope, collecting write demands.
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
        scope = _new_scope({"root", "self", "bindingOwner"}, {}, recipe_params)
        for name, param_type in recipe_params.items():
            if param_type == "element":
                scope.bindings.add(name)
                scope.btypes[name] = "native"
        if phase == "export":
            scope.bindings.add("render")
            scope.btypes["render"] = "render"
        recipe_phase = "export" if phase == "export" else "recipe"
        _check_selector(recipe.get("select"), scope, recipe_phase)
        scope.btypes["self"] = "native"
        when = recipe.get("when")
        if when is not None:
            _check_predicate(when, scope, recipe_phase)
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

    # Secondary family positions with minimal scope (ui/exports gates, themes).
    # Every environment built from baseEnv binds bindingOwner, including UI
    # entries and recipes (compiler-static.ts:54, :240, :369).
    plain_scope = _new_scope({"root", "self", "bindingOwner"}, {})
    for ui_entry in _as_list(profile.get("ui")):
        if not isinstance(ui_entry, dict):
            continue
        when = ui_entry.get("when")
        if when is not None:
            _check_predicate(when, plain_scope)
    for export in _as_list(profile.get("exports")):
        if not isinstance(export, dict):
            continue
        for capability in _as_list(export.get("capabilities")):
            if not isinstance(capability, dict):
                continue
            when = capability.get("when")
            if when is not None:
                # Capability predicates visit baseEnv root/self/bindingOwner
                # for family recording (typing lives in ``_static``).
                _check_predicate(when, plain_scope, "capability")
    for theme in _as_list(profile.get("themes")):
        if not isinstance(theme, dict):
            continue
        for occurrence in _as_list(theme.get("syntheticOccurrences")):
            if not isinstance(occurrence, dict):
                continue
            _check_selector(occurrence.get("select"), plain_scope)
            label = occurrence.get("label")
            if label is not None:
                _check_value(label, "predicate", plain_scope, None)

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
        if {jcs(entry) for entry in required} != {jcs(entry) for entry in declared}:
            return PureRefused(code="profile-write-set")

    # CR-10 UI/field rules (lot 5), between CR-09 and CR-11.
    code = check_ui_rules(profile, recipes)
    if code is not None:
        return PureRefused(code=code)

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
    # B7 identity: closed §5.1 pin record; sha256 is validated.digest
    # (== digest(profile) since profile is validated.profile).
    identity = _profile_identity(profile, validated.digest)
    ui_index = build_ui_index(profile)
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
        types=copy.deepcopy(types) if descriptor_context is not None else None,
        producers=dict(producers) if base is not None and producers is not None else None,
        ref_fields=frozenset(ref_fields) if base is not None and ref_fields is not None else None,
        base_types=_base_type_names(base),
        capabilities=tuple(
            sorted(str(name) for name in registry.capabilities if isinstance(name, str))
        ),
        ui=ui_index,
    )
    return PureSuccess(payload=compiled)


def _profile_identity(profile: dict[str, object], profile_digest: str) -> dict[str, object]:
    """Build the §5.1 identity record of one schema-valid profile."""
    base_pin = profile.get("base")
    base_record: dict[str, object] = {}
    if isinstance(base_pin, dict):
        base_record = {key: base_pin.get(key) for key in ("id", "version", "sha256")}
    descriptors_pin = profile.get("descriptors")
    descriptor_records: list[dict[str, object]] = []
    if isinstance(descriptors_pin, list):
        descriptor_records.extend(
            {key: entry.get(key) for key in ("id", "version", "sha256")}
            for entry in descriptors_pin
            if isinstance(entry, dict)
        )
    return {
        "mechanismVersion": profile.get("mechanismVersion"),
        "schemaVersion": profile.get("schemaVersion"),
        "profile": profile.get("profile"),
        "version": profile.get("version"),
        "sha256": profile_digest,
        "base": base_record,
        "descriptors": descriptor_records,
    }
