"""Lot-3 read context, envelope prefix pipeline and refusal records.

``Authority`` and ``create_read_context`` are the public surface; the tree
index, the §5.0 steps 1-5 prefix runner, the echo-rule refusal builder and
the C/N graph index are shared by every lot-3 operation. Inputs are deep
copied at the boundary; evaluation never mutates the owned snapshot.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Final, Literal, TypeGuard

from bpmn_io.profile._compat import check_compatibility
from bpmn_io.profile._compiler import CompiledProfile
from bpmn_io.profile._envelope import (
    _check_identity_full,
    check_envelope_integrity,
    check_envelope_shape,
)
from bpmn_io.profile._evaluate import ReadContext as _BaseReadContext
from bpmn_io.profile._evaluate import make_read_context
from bpmn_io.profile._results import (
    PureResult,
    Report,
    ResultRefused,
    pure_refused,
    pure_success,
    result_refused,
)

__all__ = [
    "Authority",
    "ReadContext",
    "create_read_context",
]

#: Runtime capabilities of this library (DESIGN §2.1 ids).
_RUNTIME_CAPABILITIES: Final[tuple[str, ...]] = (
    "predicates/1",
    "selectors/1",
    "recipes/1",
    "profile-lint/1",
    "render-data/1",
    "export-ir/1",
)

#: Closed invocation vocabularies.
_ACTORS: Final[frozenset[str]] = frozenset({"editor", "code"})
_ACTIVATIONS: Final[frozenset[str]] = frozenset({"edit", "qualification"})
_MODES: Final[frozenset[str]] = frozenset({"extraction", "retained"})


@dataclass(frozen=True)
class Authority:
    """One recipe-planning authority (wire members ``actor``/``activation``).

    ``actor`` is ``editor`` or ``code``; ``activation`` is ``edit``
    (default, every open technical gate enforced) or ``qualification``
    (read-only preview and neutral qualification). ``deletion_intent``
    authorizes explicit deletions. Invalid records refuse
    ``operation-error`` at the call boundary.
    """

    actor: Literal["editor", "code"]
    activation: Literal["edit", "qualification"] = "edit"
    deletion_intent: bool = False


@dataclass(frozen=True)
class TreeIndex:
    """Immutable pre-order index over one JSON snapshot tree."""

    elements: tuple[dict[str, Any], ...]
    by_id: dict[str, dict[str, Any]]
    parents: dict[int, dict[str, Any]]
    pointers: dict[int, str]
    via_property: dict[int, str]


def _escape_segment(segment: str) -> str:
    """Escape one RFC 6901 pointer segment."""
    return segment.replace("~", "~0").replace("/", "~1")


def _utf16(value: str) -> bytes:
    """Encode one string in UTF-16 code units (the deterministic sort order)."""
    return value.encode("utf-16-be")


def build_tree_index(tree: dict[str, Any]) -> TreeIndex:
    """Index one JSON tree in pre-order (members in UTF-16 key order).

    Every mapping is a node (element-ness is decided by consumers from
    the descriptor index); arrays contribute indexed segments. ``by_id``
    keeps the first visit on duplicate ids. Operates with an explicit
    stack and visits each node once.
    """
    elements: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    parents: dict[int, dict[str, Any]] = {}
    pointers: dict[int, str] = {}
    via_property: dict[int, str] = {}
    stack: list[tuple[dict[str, Any], str]] = [(tree, "")]
    seen: set[int] = set()
    while stack:
        node, pointer = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        elements.append(node)
        pointers[id(node)] = pointer
        element_id = node.get("id")
        if isinstance(element_id, str) and element_id not in by_id:
            by_id[element_id] = node
        pending: list[tuple[dict[str, Any], str]] = []
        for key in sorted(node.keys(), key=_utf16):
            value = node[key]
            segment = _escape_segment(key)
            if isinstance(value, dict):
                parents.setdefault(id(value), node)
                via_property.setdefault(id(value), key)
                pending.append((value, f"{pointer}/{segment}"))
            elif isinstance(value, list):
                for position, entry in enumerate(value):
                    if isinstance(entry, dict):
                        parents.setdefault(id(entry), node)
                        via_property.setdefault(id(entry), key)
                        pending.append((entry, f"{pointer}/{segment}/{position}"))
        stack.extend(reversed(pending))
    return TreeIndex(
        elements=tuple(elements),
        by_id=by_id,
        parents=parents,
        pointers=pointers,
        via_property=via_property,
    )


@dataclass(frozen=True)
class ReadContext(_BaseReadContext):
    """Immutable lot-3 evaluation context over one envelope snapshot.

    Extends the Block A ``ReadContext`` (additive, with defaults) with
    the compiled profile, its descriptor/effective-base index, the
    immutable envelope copy, its source pointers and revision.
    """

    compiled: CompiledProfile | None = None
    identity: dict[str, Any] = field(default_factory=dict)
    descriptor_types: dict[str, dict[str, Any]] = field(default_factory=dict)
    producers: dict[tuple[str, str], frozenset[str]] = field(default_factory=dict)
    envelope: dict[str, Any] = field(default_factory=dict)
    pointers: dict[int, str] = field(default_factory=dict)
    revision: str = ""


@dataclass(frozen=True)
class Prefix:
    """One validated envelope prefix (steps 1-5 of §5.0)."""

    identity: dict[str, Any]
    revision: str
    tree: dict[str, Any]
    bindings: list[dict[str, Any]]
    index: TreeIndex


def echo_identity(envelope: object) -> tuple[dict[str, Any] | None, str | None]:
    """Return the echoed ``(profileIdentity, baseRevision)`` pair or nothings.

    Echo applies whenever the envelope argument is a JSON object with
    ``documentVersion`` ``"1"``, a shape-valid closed §5.1 identity record
    and a string ``semanticRevision``, even when a later check fails.
    """
    if not isinstance(envelope, dict):
        return None, None
    if envelope.get("documentVersion") != "1":
        return None, None
    identity = envelope.get("profileIdentity")
    if _check_identity_full(identity) is not None:
        return None, None
    revision = envelope.get("semanticRevision")
    if not isinstance(revision, str) or not isinstance(identity, dict):
        return None, None
    return copy.deepcopy(identity), revision


def refuse_result(operation: str, code: str, envelope: object) -> ResultRefused:
    """Build one lot-3 refusal with the echo rule and an empty report."""
    identity, revision = echo_identity(envelope)
    report = Report(
        operation=operation,
        source_identity=identity,
        input_revision=revision,
    )
    return result_refused(
        operation,
        code,
        report,
        profile_identity=identity,
        base_revision=revision,
    )


def check_compiled(compiled: object) -> TypeGuard[CompiledProfile]:
    """Return whether one value is a C/N-ready compiled profile (B7)."""
    return (
        isinstance(compiled, CompiledProfile)
        and compiled.types is not None
        and compiled.producers is not None
    )


def check_compat(compiled: CompiledProfile, envelope: dict[str, Any]) -> str | None:
    """Run the §5.0 step 3 compatibility decision (refusal code or None)."""
    mine = compiled.identity
    other = envelope.get("profileIdentity")
    available = "known-and-available" if other == mine else "unavailable"
    verdict = check_compatibility(
        {
            "mechanisms": ["1"],
            "schemas": ["1.0.0"],
            "capabilities": list(_RUNTIME_CAPABILITIES),
            "assets": [],
        },
        mine,
        other if isinstance(other, dict) else None,
        document_version=envelope.get("documentVersion")
        if isinstance(envelope.get("documentVersion"), str)
        else None,
        source_availability=available,
        selected_migration=False,
        required_capabilities=list(compiled.capabilities),
        required_assets=[],
        envelope_valid=True,
    )
    if verdict.get("status") == "ok":
        return None
    code = verdict.get("code")
    return str(code) if isinstance(code, str) else "profile-schema"


def _reference_members(
    type_name: str, types: dict[str, dict[str, Any]]
) -> dict[str, tuple[str, ...]]:
    """Return the admitted reference targets of one descriptor type."""
    spec = types.get(type_name)
    if spec is None:
        return {}
    references = spec.get("references", {})
    if not isinstance(references, dict):
        return {}
    return {prop: tuple(targets) for prop, targets in references.items() if isinstance(prop, str)}


def _is_many_reference(type_name: str, prop: str, types: dict[str, dict[str, Any]]) -> bool:
    """Return whether one reference property is multi-valued."""
    spec = types.get(type_name)
    if spec is None:
        return False
    many = spec.get("many", ())
    return isinstance(many, (list, tuple)) and prop in many


def check_graph(  # noqa: C901, PLR0912 - one branch per graph-index failure
    index: TreeIndex,
    types: dict[str, dict[str, Any]],
    ref_fields: frozenset[tuple[str, str]] = frozenset(),
) -> str | None:
    """Run the §5.0 step 5 graph index (refusal code or None).

    One pre-order pass classifies every element and member; reference
    resolution follows once the full id set is known. Containment
    admission is not a graph-index check. An empty single-valued
    reference value is not a reference. Base-declared ID-valued scalars
    (``ref_fields``) validate as existence-only references.
    """
    seen_ids: set[str] = set()
    pending: list[tuple[dict[str, Any], str, object, bool]] = []
    for element in index.elements:
        type_name = element.get("$type")
        if not isinstance(type_name, str) or type_name not in types:
            return "descriptor-role-unknown"
        spec = types[type_name]
        scalars = spec.get("scalars", ())
        containment = spec.get("containment", {})
        references = _reference_members(type_name, types)
        element_id = element.get("id")
        if isinstance(element_id, str):
            if element_id in seen_ids:
                return "id-collision"
            seen_ids.add(element_id)
        for key in element:
            if key == "$type":
                continue
            if isinstance(scalars, (list, tuple)) and key in scalars:
                if (type_name, key) not in ref_fields:
                    continue
                pending.append((element, key, element[key], True))
                continue
            if isinstance(containment, dict) and key in containment:
                continue
            if key in references:
                pending.append((element, key, element[key], False))
                continue
            if (type_name, key) in ref_fields:
                pending.append((element, key, element[key], True))
                continue
            return "descriptor-role-unknown"
    for element, key, value, scalar in pending:
        code = _check_reference_value(element, key, value, index, types, scalar=scalar)
        if code is not None:
            return code
    return None


def _dangling_admits_key(
    type_name: str,
    key: str,
    spec: dict[str, Any],
    references: dict[str, tuple[str, ...]],
    ref_fields: frozenset[tuple[str, str]],
) -> bool:
    """Return whether one element member can carry a reference value."""
    if key == "$type":
        return False
    scalars = spec.get("scalars", ())
    if isinstance(scalars, (list, tuple)) and key in scalars:
        return (type_name, key) in ref_fields
    containment = spec.get("containment", {})
    if isinstance(containment, dict) and key in containment:
        return False
    return key in references or (type_name, key) in ref_fields


def find_dangling(
    index: TreeIndex,
    types: dict[str, dict[str, Any]],
    ref_fields: frozenset[tuple[str, str]] = frozenset(),
) -> list[dict[str, str | None]]:
    """Locate every dangling reference of one indexed JSON tree (§6.9 PS-20).

    Same member classification as :func:`check_graph`, but exhaustive and
    located: each reference value naming an absent target yields one
    ``{"pointer", "targetId"}`` record in document order (list members
    address their indexed member pointer). Empty values are not references;
    target-type admission is not checked here — a present but mistyped
    target is reported by its rule, never as dangling. The index is only
    read, never mutated.
    """
    known = set(index.by_id)
    found: list[dict[str, str | None]] = []
    for element in index.elements:
        type_name = element.get("$type")
        if not isinstance(type_name, str) or type_name not in types:
            continue
        spec = types[type_name]
        references = _reference_members(type_name, types)
        holder = element.get("id")
        holder_id = holder if isinstance(holder, str) and holder else None
        base = index.pointers.get(id(element), "")
        for key in element:
            if not _dangling_admits_key(type_name, key, spec, references, ref_fields):
                continue
            value = element[key]
            listed = isinstance(value, list)
            items = value if listed else [value]
            for position, item in enumerate(items):
                if item is None:
                    continue
                target = item.get("$ref") if isinstance(item, dict) else item
                if isinstance(target, str) and (target == "" or target in known):
                    continue
                found.append(
                    {
                        "pointer": _member_pointer(base, key, position, listed=listed),
                        "targetId": holder_id,
                    }
                )
    return found


def _member_pointer(base: str, key: str, position: int, *, listed: bool) -> str:
    """Address one reference member (indexed when multi-valued)."""
    segment = _escape_segment(key)
    if listed:
        return f"{base}/{segment}/{position}"
    return f"{base}/{segment}"


def _check_reference_value(  # noqa: PLR0913 - reference check inputs travel together
    element: dict[str, Any],
    key: str,
    value: object,
    index: TreeIndex,
    types: dict[str, dict[str, Any]],
    *,
    scalar: bool = False,
) -> str | None:
    """Check one reference value for dangling or wrong-type targets.

    ID-valued scalars carry no admitted target list, so only existence
    is checked; an empty value is not a reference.
    """
    items = value if isinstance(value, list) else [value]
    for item in items:
        if not isinstance(item, str):
            return "reference-dangling"
        if item == "":
            continue
        target = index.by_id.get(item)
        if target is None:
            return "reference-dangling"
        if scalar:
            continue
        admitted = _reference_members(str(element.get("$type")), types).get(key, ())
        target_type = target.get("$type")
        if not isinstance(target_type, str) or target_type not in admitted:
            return "reference-dangling"
    return None


def run_prefix(  # noqa: PLR0911 - one return per prefix failure
    compiled: object, envelope: object
) -> Prefix | str:
    """Run the §5.0 steps 1-5 prefix (a ``Prefix`` or a refusal code).

    Step 1 checks the B7 compilation fields; step 2 the envelope shape;
    step 3 compatibility; step 4 envelope integrity; step 5 the graph
    index. Nothing is mutated; the tree and bindings are deep copied.
    """
    if not check_compiled(compiled):
        return "descriptor-mismatch"
    if not isinstance(envelope, dict):
        return "profile-schema"
    failed = check_envelope_shape(envelope)
    if failed is not None:
        return failed
    failed = check_compat(compiled, envelope)
    if failed is not None:
        return failed
    failed = check_envelope_integrity(envelope)
    if failed is not None:
        return failed
    tree = envelope.get("tree")
    bindings = envelope.get("bindings")
    identity = envelope.get("profileIdentity")
    revision = envelope.get("semanticRevision")
    if (
        not isinstance(compiled, CompiledProfile)
        or compiled.types is None
        or not isinstance(tree, dict)
        or not isinstance(bindings, list)
        or not isinstance(identity, dict)
        or not isinstance(revision, str)
    ):
        return "profile-schema"
    owned_tree = copy.deepcopy(tree)
    owned_bindings = copy.deepcopy(bindings)
    index = build_tree_index(owned_tree)
    failed = check_graph(index, compiled.types, compiled.ref_fields or frozenset())
    if failed is not None:
        return failed
    return Prefix(
        identity=copy.deepcopy(identity),
        revision=revision,
        tree=owned_tree,
        bindings=owned_bindings,
        index=index,
    )


def create_read_context(
    compiled: CompiledProfile,
    envelope: object,
    *,
    stage: str,
) -> PureResult:
    """Build one lot-3 read context over an envelope snapshot (§5.0 steps 1-5).

    Returns the Block A ``ReadContext`` extended with the compiled
    profile, its descriptor/effective-base index, the immutable envelope
    copy, its source pointers and revision. The payload is a
    lot-3 ``ReadContext``; failures refuse with the step code.
    """
    if stage not in {
        "load",
        "import",
        "complete",
        "pre-normalize",
        "normalize",
        "post-normalize",
        "layout",
        "post-layout",
        "release",
        "render",
        "export",
    }:
        return pure_refused("operation-error")
    outcome = run_prefix(compiled, to_wire_envelope(envelope))
    if isinstance(outcome, str):
        return pure_refused(outcome)
    if not check_compiled(compiled):
        return pure_refused("descriptor-mismatch")
    context = context_from_snapshot(
        compiled,
        outcome.identity,
        outcome.revision,
        outcome.tree,
        outcome.bindings,
        stage=stage,
    )
    if isinstance(context, str):
        return pure_refused(context)
    return pure_success(context)


def to_wire_envelope(envelope: object) -> object:
    """Convert a ``DocumentEnvelope`` to its wire mapping (mappings pass through)."""
    to_json = getattr(envelope, "to_json", None)
    if callable(to_json):
        return to_json()
    return envelope


def context_from_snapshot(  # noqa: PLR0913 - snapshot parts travel together
    compiled: CompiledProfile,
    identity: dict[str, Any],
    revision: str,
    tree: dict[str, Any],
    bindings: list[dict[str, Any]],
    *,
    stage: str,
) -> ReadContext | str:
    """Assemble one lot-3 read context over an owned snapshot."""
    if compiled.types is None or compiled.producers is None:
        return "descriptor-mismatch"
    notions: dict[str, object] = {key: dict(value) for key, value in compiled.notions.items()}
    base = make_read_context(tree, stage=stage, notions=notions)
    index = build_tree_index(tree)
    return ReadContext(
        root=base.root,
        elements=base.elements,
        by_id=dict(base.by_id),
        bindings=tuple(copy.deepcopy(bindings)),
        stage=stage,
        notions=dict(base.notions),
        parents=dict(base.parents),
        compiled=compiled,
        identity=copy.deepcopy(identity),
        descriptor_types=copy.deepcopy(compiled.types),
        producers=dict(compiled.producers),
        envelope={
            "documentVersion": "1",
            "profileIdentity": copy.deepcopy(identity),
            "tree": tree,
            "bindings": copy.deepcopy(bindings),
            "semanticRevision": revision,
        },
        pointers=dict(index.pointers),
        revision=revision,
    )
