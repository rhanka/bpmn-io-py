"""Lot-3 recipe planning (DESIGN §2.4 ``planRecipe``).

Generic evaluation of injected compiled recipes only: selectors and
predicates run through the Block A evaluator over the immutable snapshot,
value operands through the plan evaluator below (planned elements
materialize as overlay dicts so later steps read them uniformly). Every
mutation is planned, never applied; gates fire only for the internal C/N
driver (public explicit plans never gate).
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, NoReturn

from bpmn_io.profile._c14n import jcs
from bpmn_io.profile._cn_context import (
    Authority,
    ReadContext,
    _reference_members,
    _utf16,
)
from bpmn_io.profile._compiler import _authorize as _compiler_authorize
from bpmn_io.profile._compiler import _Scope as _CompilerScope
from bpmn_io.profile._evaluate import _MISSING, _eval_value, _pinned_is_many, evaluate_predicate
from bpmn_io.profile._evaluate import select as _block_select
from bpmn_io.profile._results import PureRefused, PureResult, pure_refused, pure_success
from bpmn_io.profile._stable_id import allocate_stable_id

__all__ = ["plan_recipe"]

#: Phase actors (DESIGN §2.4.1 bounded authority).
_CODE_PHASES: Final[frozenset[str]] = frozenset({"complete", "normalize"})
_EDITOR_PHASES: Final[frozenset[str]] = frozenset(
    {"create", "edit", "reference", "convert", "migrate"}
)

#: WritePlan version.
_PLAN_VERSION: Final[str] = "1"


class _RefusalError(Exception):
    """Internal first-refusal signal carrying the closed code."""

    def __init__(self, code: str) -> None:
        """Remember the refusal code."""
        super().__init__(code)
        self.code = code


class _RefuseStepError(_RefusalError):
    """A reached profile ``refuse`` step (its own code aborts the plan)."""


def _refuse(code: str) -> NoReturn:
    """Raise the refusal for one closed code."""
    error = _RefusalError(code)
    raise error


def _refuse_step(code: str) -> NoReturn:
    """Raise the reached-refuse signal for one step code."""
    error = _RefuseStepError(code)
    raise error


@dataclass
class _Shared:
    """Mutable per-run planning state (ensure identities, planned ids)."""

    ensure: dict[tuple[Any, ...], object] = field(default_factory=dict)
    roles: dict[tuple[str, str], tuple[Any, ...]] = field(default_factory=dict)
    planned_ids: set[str] = field(default_factory=set)
    planned_sequence: int = 0
    propose: bool = False
    provenance: frozenset[str] = frozenset()
    proposals: list[dict[str, object]] = field(default_factory=list)


@dataclass
class _Planned:
    """One materialized planned element (overlay, not yet staged)."""

    element: dict[str, Any]
    planned_id: str | None
    write_index: int
    ensure_role: tuple[str, str] | None = None


def _is_missing(value: object) -> bool:
    """Return whether a value is the MISSING sentinel."""
    return value is _MISSING


def _eval_plan_value(  # noqa: C901, PLR0911, PLR0912
    node: object, bindings: dict[str, object], context: ReadContext
) -> object:
    """Evaluate one value AST with planned-element awareness.

    ``literal``, ``param``, ``id``, ``read`` and ``concat`` resolve
    against snapshot elements and materialized planned dicts (MISSING is
    preserved); ``ids`` evaluates its selector to the ordered id list;
    ``stripPrefix``/``case`` delegate to the Block A evaluator when the
    subtree names existing bindings only.
    """
    if not isinstance(node, dict):
        _refuse("profile-type")
    op = node.get("op")
    if op == "literal":
        return node.get("value")
    if op == "param":
        name = node.get("name")
        if not isinstance(name, str) or name not in bindings:
            _refuse("profile-symbol")
        return bindings[name]
    if op == "id":
        name = node.get("binding")
        if not isinstance(name, str) or name not in bindings:
            _refuse("profile-symbol")
        target = bindings[name]
        if _is_missing(target):
            _refuse("profile-type")
        if isinstance(target, dict):
            element_id = target.get("id")
            if not isinstance(element_id, str):
                _refuse("profile-type")
            return element_id
        _refuse("profile-type")
    if op == "read":
        name = node.get("binding")
        path = node.get("path")
        if not isinstance(name, str) or not isinstance(path, str):
            _refuse("profile-type")
        if name not in bindings:
            _refuse("profile-symbol")
        target = bindings[name]
        if _is_missing(target):
            return _MISSING
        if not isinstance(target, dict):
            return _MISSING
        return _read_dict_path(target, path)
    if op == "concat":
        values = node.get("values")
        if not isinstance(values, list) or not values:
            _refuse("profile-type")
        parts: list[str] = []
        for entry in values:
            rendered = _eval_plan_value(entry, bindings, context)
            if not isinstance(rendered, str):
                _refuse("profile-type")
            parts.append(rendered)
        return "".join(parts)
    if op == "ids":
        return _eval_ids(node.get("select"), bindings, context)
    if op in ("stripPrefix", "case"):
        if _names_existing_only(node, bindings, context):
            try:
                return _eval_value(node, context, bindings)
            except (ValueError, TypeError) as exc:
                _refuse(str(exc.args[0]) if exc.args else "profile-type")
        _refuse("profile-type")
    if op == "outputId":
        _refuse("profile-value-context")
    _refuse("profile-symbol")


def _read_dict_path(element: dict[str, Any], path: str) -> object:
    """Read one RFC 6901 path from a plain dict (MISSING when absent)."""
    if not path.startswith("/"):
        _refuse("profile-type")
    current: object = element
    for raw in path[1:].split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _names_existing_only(node: object, bindings: dict[str, object], context: ReadContext) -> bool:
    """Return whether a value subtree names snapshot elements only."""
    stack: list[object] = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            name = current.get("binding")
            if isinstance(name, str):
                target = bindings.get(name, _MISSING)
                if _is_missing(target) or not _is_snapshot_element(target, context):
                    return False
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return True


def _is_snapshot_element(target: object, context: ReadContext) -> bool:
    """Return whether an element belongs to the immutable snapshot."""
    return isinstance(target, dict) and id(target) in context.pointers


def _eval_ids(selector: object, bindings: dict[str, object], context: ReadContext) -> list[str]:
    """Evaluate one ``ids`` operand to the ordered id list."""
    handles = _run_select(selector, bindings, context)
    ids: list[str] = []
    for handle in handles:
        element_id = handle.element_id
        if element_id is None:
            _refuse("profile-type")
        ids.append(element_id)
    ordered: list[str] = []
    for element_id in ids:
        if element_id not in ordered:
            ordered.append(element_id)
    return ordered


def _handle_sort_key(handle: object, context: ReadContext, sequence: int) -> tuple[Any, ...]:
    """Order one handle: ID-bearing by UTF-16 id, ID-less by source pointer."""
    element_id = getattr(handle, "element_id", None)
    if isinstance(element_id, str):
        return (0, _utf16(element_id), b"")
    element = getattr(handle, "element", None)
    pointer = context.pointers.get(id(element)) if isinstance(element, dict) else None
    if pointer is not None:
        return (1, b"\x01", _utf16(pointer))
    return (1, b"\xff", _utf16(str(sequence)))


def _run_select(selector: object, bindings: dict[str, object], context: ReadContext) -> list[Any]:
    """Run one selector and return handles in lot-3 order (errors refuse)."""
    if not isinstance(selector, dict):
        _refuse("profile-type")
    outcome = _block_select(selector, context, bindings)
    if isinstance(outcome, PureRefused):
        _refuse(outcome.code)
    payload = outcome.payload
    if not isinstance(payload, list):
        _refuse("profile-type")
    handles = list(payload)
    keyed = [
        (_handle_sort_key(handle, context, position), position, handle)
        for position, handle in enumerate(handles)
    ]
    keyed.sort(key=lambda entry: (entry[0], entry[1]))
    return [handle for _, _, handle in keyed]


def _element_ref(
    element: dict[str, Any], planned: list[_Planned], context: ReadContext
) -> dict[str, Any]:
    """Encode one element reference (``id``, ``pointer`` or ``handle``)."""
    for entry in planned:
        if entry.element is element:
            if entry.planned_id is not None:
                return {"id": entry.planned_id}
            return {"handle": entry.write_index}
    element_id = element.get("id")
    if isinstance(element_id, str):
        return {"id": element_id}
    pointer = context.pointers.get(id(element))
    if pointer is None:
        _refuse("reference-dangling")
    return {"pointer": pointer}


def _lookup(name: object, bindings: dict[str, object], *, required: bool) -> object:
    """Resolve one binding name (undeclared names refuse ``profile-symbol``)."""
    if not isinstance(name, str) or name not in bindings:
        _refuse("profile-symbol")
    target = bindings[name]
    if required and _is_missing(target):
        _refuse("profile-type")
    return target


def _containment_cardinality(
    container_type: str, prop: str, types: dict[str, dict[str, Any]]
) -> str:
    """Return the containment cardinality (``many`` unless ``single``)."""
    spec = types.get(container_type)
    if spec is None:
        return "many"
    single = spec.get("single", ())
    if isinstance(single, (list, tuple)) and prop in single:
        return "single"
    return "many"


def _reference_cardinality(
    container_type: str, prop: str, types: dict[str, dict[str, Any]], stored: object
) -> str:
    """Return the reference cardinality (facet, stored shape, admission).

    A ``many`` facet wins, as does a stored list; a stored scalar stays
    ``single`` (profile-local facts never defer to global state). Only
    when the property is absent does the pinned metamodel decide, and a
    single admitted target narrows a metamodel-many reference to single
    (the profile's closed world keeps no collection); unknown pairs stay
    ``single``. Empty writes to empty-or-absent singles are still accepted
    by the replace count exemption (F1).
    """
    if _is_many_reference(container_type, prop, types):
        return "many"
    if isinstance(stored, list):
        return "many"
    if stored is not _MISSING:
        return "single"
    # The compiled facets carry no ``many`` marks in this profile family,
    # so an absent property consults the pinned metamodel ``isMany``;
    # admitting exactly one target type narrows it to single.
    admitted = _reference_members(container_type, types).get(prop, ())
    if len(admitted) > 1 and _pinned_is_many(container_type, prop):
        return "many"
    return "single"


def _is_many_reference(container_type: str, prop: str, types: dict[str, dict[str, Any]]) -> bool:
    """Return whether one descriptor reference property is multi-valued."""
    spec = types.get(container_type)
    if spec is None:
        return False
    many = spec.get("many", ())
    return isinstance(many, (list, tuple)) and prop in many


def _target_types(container_type: str, prop: str, types: dict[str, dict[str, Any]]) -> list[str]:
    """Return the UTF-16 sorted admitted targets of one reference property."""
    admitted = _reference_members(container_type, types).get(prop, ())
    return sorted((str(name) for name in admitted), key=_utf16)


def _check_runtime_authority(
    container_type: str,
    prop: str,
    phase: str,
    types: dict[str, dict[str, Any]],
    producers: dict[tuple[str, str], frozenset[str]],
) -> None:
    """Enforce the runtime producer check (``profile-producer``/``profile-type``)."""
    scope = _CompilerScope(
        notions=set(),
        bindings=set(),
        btypes={},
        params={},
        types=dict(types),
        producers=dict(producers),
        ref_fields=None,
        used_families=set(),
    )
    code = _compiler_authorize(scope, container_type, prop, phase)
    if code is not None:
        _refuse(code)


@dataclass
class _Planner:
    """Mutable single-recipe planning state over one snapshot."""

    context: ReadContext
    recipe_id: str
    phase: str
    actor: str
    activation: str
    gates: bool
    shared: _Shared
    writes: list[dict[str, Any]] = field(default_factory=list)
    planned: list[_Planned] = field(default_factory=list)

    @property
    def snapshot(self) -> dict[str, Any]:
        """Return the immutable snapshot tree."""
        tree = self.context.envelope["tree"]
        if not isinstance(tree, dict):
            _refuse("profile-type")
        return dict(tree)

    @property
    def types(self) -> dict[str, dict[str, Any]]:
        """Return the descriptor index."""
        return self.context.descriptor_types

    @property
    def producers(self) -> dict[tuple[str, str], frozenset[str]]:
        """Return the effective producer matrix."""
        return self.context.producers

    def authorize(self, container_type: str, prop: str) -> None:
        """Enforce the runtime producer check for one written property."""
        _check_runtime_authority(container_type, prop, self.phase, self.types, self.producers)

    def stored(self, element: dict[str, Any], prop: str) -> object:
        """Read one stored snapshot value (MISSING when absent)."""
        if element in [entry.element for entry in self.planned]:
            return element.get(prop, _MISSING)
        return element.get(prop, _MISSING)

    def element_type(self, element: dict[str, Any]) -> str:
        """Return one element's type name (refuses when unknown)."""
        type_name = element.get("$type")
        if not isinstance(type_name, str):
            _refuse("profile-type")
        return type_name

    def gate_lane_write(
        self, element: dict[str, Any], prop: str, *, effective: bool, removal: bool
    ) -> None:
        """Enforce the OPEN-EXTERNAL/OPEN-SHARING membership gates.

        ``removal`` selects the SHARING (removal) branch; any other
        effective membership change takes the EXTERNAL branch.
        """
        if not self.gates or not effective:
            return
        if prop != "flowNodeRef" or self.element_type(element) != "bpmn:Lane":
            return
        if self.activation == "edit":
            _refuse("profile-open")
        if removal:
            _refuse("responsibility-preservation-required")

    def gate_port_fill(
        self, element: dict[str, Any], prop: str, stored: object, *, effective: bool
    ) -> None:
        """Enforce the OPEN-IO port-fill gate for one effective fill."""
        if not self.gates or not effective or self.phase != "complete":
            return
        if prop != "sourceRef" or self.element_type(element) != "bpmn:DataOutputAssociation":
            return
        if stored is not _MISSING and stored != "":
            return
        if self.activation == "edit":
            _refuse("profile-open")

    def gate_ensure_create(self) -> None:
        """Enforce the OPEN-RESERVED-N creation gate."""
        if self.gates and self.activation == "edit":
            _refuse("profile-open")

    def materialize(
        self,
        type_name: str,
        planned_id: str | None,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """Materialize one planned overlay element for later steps."""
        element: dict[str, Any] = {"$type": type_name}
        if planned_id is not None:
            element["id"] = planned_id
        element.update(fields)
        self.shared.planned_sequence += 1
        if planned_id is not None:
            self.shared.planned_ids.add(planned_id)
        return element

    def register_planned(
        self,
        element: dict[str, Any],
        planned_id: str | None,
        write_index: int,
        ensure_role: tuple[str, str] | None = None,
    ) -> None:
        """Register one materialized element in the plan overlay."""
        self.planned.append(
            _Planned(
                element=element,
                planned_id=planned_id,
                write_index=write_index,
                ensure_role=ensure_role,
            )
        )


def _single_segment(path: object) -> str:
    """Split one single-segment descriptor path (refuses otherwise)."""
    if not isinstance(path, str) or not path.startswith("/") or "/" in path[1:]:
        _refuse("profile-type")
    prop = path[1:]
    if not prop:
        _refuse("profile-type")
    return prop


def _bare_property(name: object) -> str:
    """Validate one bare containment property name (refuses otherwise)."""
    if not isinstance(name, str) or not name or "/" in name:
        _refuse("profile-type")
    return name


def _eval_fields(planner: _Planner, raw: object, bindings: dict[str, object]) -> dict[str, Any]:
    """Evaluate one creation field list to the ordered value mapping."""
    if not isinstance(raw, list):
        _refuse("profile-type")
    fields: dict[str, Any] = {}
    for entry in raw:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            _refuse("profile-type")
        value = _eval_plan_value(entry.get("value"), bindings, planner.context)
        if _is_missing(value) or isinstance(value, (dict, list)):
            _refuse("profile-type")
        fields[entry["name"]] = value
    return fields


def _exec_bind(planner: _Planner, step: dict[str, Any], bindings: dict[str, object]) -> None:
    """Execute one bind step (no write; registers the alias)."""
    alias = step.get("as")
    cardinality = step.get("cardinality")
    if not isinstance(alias, str):
        _refuse("profile-type")
    if cardinality == "one":
        handles = _run_select(step.get("select"), bindings, planner.context)
        if len(handles) != 1:
            _refuse("profile-ambiguous-binding")
        bindings[alias] = handles[0].element
        return
    if cardinality == "zeroOrOne":
        handles = _run_select(step.get("select"), bindings, planner.context)
        if len(handles) > 1:
            _refuse("profile-ambiguous-binding")
        bindings[alias] = handles[0].element if handles else _MISSING
        return
    if cardinality == "first":
        fallbacks = step.get("fallbacks", [])
        if not isinstance(fallbacks, list):
            _refuse("profile-type")
        for selector in [step.get("select"), *fallbacks]:
            handles = _run_select(selector, bindings, planner.context)
            if handles:
                bindings[alias] = handles[0].element
                return
        bindings[alias] = _MISSING
        return
    _refuse("profile-type")


def _exec_create(planner: _Planner, step: dict[str, Any], bindings: dict[str, object]) -> None:
    """Execute one create step (records the write, materializes the alias)."""
    alias = step.get("as")
    type_name = step.get("type")
    if not isinstance(alias, str) or not isinstance(type_name, str):
        _refuse("profile-type")
    parent = _lookup(step.get("parent"), bindings, required=True)
    if not isinstance(parent, dict):
        _refuse("profile-type")
    prop = _bare_property(step.get("property"))
    parent_type = planner.element_type(parent)
    _check_containment_admission(planner, parent_type, prop, type_name)
    fields = _eval_fields(planner, step.get("fields"), bindings)
    planner.authorize(parent_type, prop)
    cardinality = _containment_cardinality(parent_type, prop, planner.types)
    identity = step.get("identity")
    planned_id: str | None = None
    if identity == "allocated":
        owner = _eval_plan_value(step.get("ownerId"), bindings, planner.context)
        slot = step.get("slot")
        key = _eval_plan_value(step.get("key"), bindings, planner.context)
        if not isinstance(owner, str) or not isinstance(slot, str) or not isinstance(key, str):
            _refuse("profile-type")
        planner.authorize(type_name, "id")
        planned_id = allocate_stable_id(owner, slot, key)
    elif identity != "containment":
        _refuse("profile-type")
    element = planner.materialize(type_name, planned_id, fields)
    write: dict[str, Any] = {
        "op": "create",
        "recipeId": planner.recipe_id,
        "type": type_name,
        "parent": _element_ref(parent, planner.planned, planner.context),
        "property": prop,
        "fields": fields,
        "cardinality": cardinality,
    }
    if planned_id is not None:
        write["id"] = planned_id
    planner.writes.append(write)
    planner.register_planned(element, planned_id, len(planner.writes) - 1)
    bindings[alias] = element


def _check_containment_admission(
    planner: _Planner, parent_type: str, prop: str, child_type: str
) -> None:
    """Enforce containment admission with resolved types (``profile-type``)."""
    spec = planner.types.get(parent_type)
    if spec is None:
        _refuse("profile-type")
    containment = spec.get("containment", {})
    if not isinstance(containment, dict):
        _refuse("profile-type")
    admitted = containment.get(prop)
    if not isinstance(admitted, (list, tuple)) or child_type not in admitted:
        _refuse("profile-type")


def _parent_key(parent: dict[str, Any], planned: list[_Planned], context: ReadContext) -> str:
    """Return the stable parent identity for one ensure plan identity."""
    for entry in planned:
        if entry.element is parent:
            if entry.planned_id is not None:
                return f"id:{entry.planned_id}"
            return f"handle:{entry.write_index}"
    element_id = parent.get("id")
    if isinstance(element_id, str):
        return f"id:{element_id}"
    pointer = context.pointers.get(id(parent))
    if pointer is None:
        _refuse("reference-dangling")
    return f"pointer:{pointer}"


def _reuse_candidate_valid(
    planner: _Planner,
    target: dict[str, Any],
    type_name: str,
    parent: dict[str, Any],
    prop: str,
) -> bool:
    """Return whether one element satisfies the §6.3 reuse validation."""
    if planner.element_type(target) != type_name:
        return False
    actual_parent = planner.context.parents.get(id(target))
    if actual_parent is not parent:
        return False
    return _child_property(actual_parent, parent, prop, target) == prop


def _is_binding_target(planner: _Planner, element_id: str) -> bool:
    """Return whether one element is already a snapshot binding target."""
    for record in planner.context.envelope["bindings"]:
        if isinstance(record, dict) and record.get("targetId") == element_id:
            return True
    return False


def _propose_ensure(  # noqa: PLR0913, PLR0917 - one ensure fact set per call
    planner: _Planner,
    planned_id: str,
    type_name: str,
    parent: dict[str, Any],
    prop: str,
    owner_id: str,
    role: str,
    identity: tuple[Any, ...],
    role_key: tuple[str, str],
    bindings: dict[str, object],
    alias: str,
) -> bool:
    """Run one ensure in recovery-proposal mode (True when occupied, §6.7).

    A free stable id falls through to the normal creation path (its write is
    discarded by the dry run). An occupied id never refuses: a qualified,
    attested, unbound occupant is proposed as a reuse, anything else binds
    the alias to the occupying element.
    """
    element = planner.context.by_id.get(planned_id)
    if not isinstance(element, dict):
        return False
    try:
        valid = _reuse_candidate_valid(planner, element, type_name, parent, prop)
    except _RefusalError:
        valid = False
    if (
        valid
        and planned_id in planner.shared.provenance
        and not _is_binding_target(planner, planned_id)
    ):
        proposal: dict[str, object] = {"ownerId": owner_id, "role": role, "targetId": planned_id}
        for existing in planner.shared.proposals:
            if existing.get("targetId") == planned_id and existing != proposal:
                _refuse("support-binding-conflict")
        if proposal not in planner.shared.proposals:
            planner.shared.proposals.append(proposal)
    planner.shared.ensure[identity] = element
    planner.shared.roles[role_key] = identity
    bindings[alias] = element
    return True


def _snapshot_binding(planner: _Planner, owner_id: str, role: str) -> dict[str, Any] | None:
    """Find one snapshot binding by ``(ownerId, role)`` (None when absent)."""
    for record in planner.context.envelope["bindings"]:
        if (
            isinstance(record, dict)
            and record.get("ownerId") == owner_id
            and record.get("role") == role
        ):
            return record
    return None


def _exec_ensure(  # noqa: C901, PLR0912, PLR0915 - one gate branch per ensure outcome
    planner: _Planner, step: dict[str, Any], bindings: dict[str, object]
) -> None:
    """Execute one ensure step (reuse-or-create with gates, §6.3)."""
    alias = step.get("as")
    type_name = step.get("type")
    role = step.get("role")
    slot = step.get("slot")
    prop = step.get("property")
    if (
        not isinstance(alias, str)
        or not isinstance(type_name, str)
        or not isinstance(role, str)
        or not isinstance(slot, str)
        or not isinstance(prop, str)
        or "/" in prop
    ):
        _refuse("profile-type")
    try:
        owner = _lookup(step.get("owner"), bindings, required=False)
        parent = _lookup(step.get("parent"), bindings, required=False)
        if _is_missing(owner) or _is_missing(parent):
            _refuse("support-binding-conflict")
        if not isinstance(owner, dict) or not isinstance(parent, dict):
            _refuse("support-binding-conflict")
        owner_id = owner.get("id")
        if not isinstance(owner_id, str):
            _refuse("support-binding-conflict")
        owner_arg = _eval_plan_value(step.get("ownerId"), bindings, planner.context)
        key = _eval_plan_value(step.get("key"), bindings, planner.context)
        if not isinstance(owner_arg, str) or not isinstance(key, str):
            _refuse("support-binding-conflict")
    except _RefusalError:
        _refuse("support-binding-conflict")
    if (
        not isinstance(owner, dict)
        or not isinstance(parent, dict)
        or not isinstance(owner_id, str)
        or not isinstance(owner_arg, str)
        or not isinstance(key, str)
    ):
        _refuse("support-binding-conflict")
    fields = _eval_fields(planner, step.get("fields"), bindings)
    parent_type = planner.element_type(parent)
    _check_containment_admission(planner, parent_type, prop, type_name)
    planner.authorize(parent_type, prop)
    planner.authorize(type_name, "id")
    cardinality = _containment_cardinality(parent_type, prop, planner.types)
    identity = (
        owner_id,
        role,
        type_name,
        _parent_key(parent, planner.planned, planner.context),
        prop,
        jcs(fields),
        owner_arg,
        slot,
        key,
    )
    role_key = (owner_id, role)
    known = planner.shared.roles.get(role_key)
    if known is not None:
        if known != identity:
            _refuse("profile-write-conflict")
        bindings[alias] = planner.shared.ensure[identity]
        return
    record = _snapshot_binding(planner, owner_id, role)
    if record is not None:
        target_id = record.get("targetId")
        target = planner.context.by_id.get(target_id) if isinstance(target_id, str) else None
        if not isinstance(target, dict):
            _refuse("support-binding-conflict")
        if not _reuse_candidate_valid(planner, target, type_name, parent, prop):
            _refuse("support-binding-conflict")
        write = {
            "op": "ensure",
            "recipeId": planner.recipe_id,
            "decision": "reuse",
            "ownerId": owner_id,
            "role": role,
            "type": type_name,
            "parent": _element_ref(parent, planner.planned, planner.context),
            "property": prop,
            "id": target_id,
            "fields": fields,
            "cardinality": cardinality,
        }
        planner.writes.append(write)
        planner.register_planned(target, target_id, len(planner.writes) - 1, role_key)
        planner.shared.ensure[identity] = target
        planner.shared.roles[role_key] = identity
        bindings[alias] = target
        return
    planner.gate_ensure_create()
    planned_id = allocate_stable_id(owner_arg, slot, key)
    if planner.shared.propose and _propose_ensure(
        planner,
        planned_id,
        type_name,
        parent,
        prop,
        owner_id,
        role,
        identity,
        role_key,
        bindings,
        alias,
    ):
        return
    if not planner.shared.propose and (
        planned_id in planner.context.by_id or planned_id in planner.shared.planned_ids
    ):
        _refuse("id-collision")
    element = planner.materialize(type_name, planned_id, fields)
    write = {
        "op": "ensure",
        "recipeId": planner.recipe_id,
        "decision": "create",
        "ownerId": owner_id,
        "role": role,
        "type": type_name,
        "parent": _element_ref(parent, planner.planned, planner.context),
        "property": prop,
        "id": planned_id,
        "fields": fields,
        "cardinality": cardinality,
    }
    planner.writes.append(write)
    planner.register_planned(element, planned_id, len(planner.writes) - 1, role_key)
    planner.shared.ensure[identity] = element
    planner.shared.roles[role_key] = identity
    bindings[alias] = element


def _child_property(
    actual_parent: object, parent: dict[str, Any], prop: str, target: dict[str, Any]
) -> str | None:
    """Return the containment property holding one child (None when absent)."""
    if actual_parent is not parent or not isinstance(actual_parent, dict):
        return None
    slot = actual_parent.get(prop, _MISSING)
    if slot is target:
        return prop
    if isinstance(slot, list) and any(entry is target for entry in slot):
        return prop
    return None


def _check_scalar_admission(planner: _Planner, type_name: str, prop: str) -> None:
    """Enforce scalar admission with resolved types (``profile-type``)."""
    spec = planner.types.get(type_name)
    if spec is None:
        _refuse("profile-type")
    scalars = spec.get("scalars", ())
    if not isinstance(scalars, (list, tuple)) or prop not in scalars:
        _refuse("profile-type")


def _exec_set(planner: _Planner, step: dict[str, Any], bindings: dict[str, object]) -> None:
    """Execute one set step (records the write with gates)."""
    target = _lookup(step.get("target"), bindings, required=True)
    if not isinstance(target, dict):
        _refuse("profile-type")
    prop = _single_segment(step.get("path"))
    type_name = planner.element_type(target)
    _check_scalar_admission(planner, type_name, prop)
    value = _eval_plan_value(step.get("value"), bindings, planner.context)
    if _is_missing(value) or isinstance(value, (dict, list)):
        _refuse("profile-type")
    planner.authorize(type_name, prop)
    stored = planner.stored(target, prop)
    effective = stored is _MISSING or stored != value
    planner.gate_lane_write(target, prop, effective=effective, removal=False)
    planner.gate_port_fill(target, prop, stored, effective=effective)
    planner.writes.append(
        {
            "op": "set",
            "recipeId": planner.recipe_id,
            "target": _element_ref(target, planner.planned, planner.context),
            "property": prop,
            "value": value,
        }
    )


def _exec_unset(planner: _Planner, step: dict[str, Any], bindings: dict[str, object]) -> None:
    """Execute one unset step (records the write)."""
    target = _lookup(step.get("target"), bindings, required=True)
    if not isinstance(target, dict):
        _refuse("profile-type")
    prop = _single_segment(step.get("path"))
    type_name = planner.element_type(target)
    _check_scalar_admission(planner, type_name, prop)
    planner.authorize(type_name, prop)
    planner.writes.append(
        {
            "op": "unset",
            "recipeId": planner.recipe_id,
            "target": _element_ref(target, planner.planned, planner.context),
            "property": prop,
        }
    )


def _assignref_result(  # noqa: C901, PLR0911 - one branch per assign mode
    stored: object, ids: list[str], mode: str, cardinality: str
) -> object:
    """Compute one assignRef canonical result (``_RefusalError`` on violation)."""
    if mode == "replace":
        if cardinality == "single":
            if len(ids) != 1:
                if ids or (stored is not _MISSING and stored != []):
                    _refuse("profile-type")
                return []
            return ids[0]
        if len(set(ids)) != len(ids):
            _refuse("profile-type")
        return list(ids)
    if mode == "appendUnique":
        if cardinality == "single" and stored is not _MISSING:
            _refuse("profile-type")
        base = stored if isinstance(stored, list) else ([] if stored is _MISSING else [stored])
        known = set(base)
        extra = sorted((item for item in set(ids) if item not in known), key=_utf16)
        return [*base, *extra]
    if mode == "remove":
        if cardinality == "single":
            if stored is _MISSING:
                return _MISSING
            if stored in ids:
                return _MISSING
            return stored
        base = stored if isinstance(stored, list) else ([] if stored is _MISSING else [stored])
        dropped = set(ids)
        return [item for item in base if item not in dropped]
    _refuse("profile-type")


def _exec_assign_ref(planner: _Planner, step: dict[str, Any], bindings: dict[str, object]) -> None:
    """Execute one assignRef step (records the write with gates, §4.2)."""
    raw_target = step.get("target")
    target = _lookup(raw_target, bindings, required=True)
    if not isinstance(target, dict):
        _refuse("profile-type")
    prop = _single_segment(step.get("path"))
    mode = step.get("mode")
    if mode not in ("replace", "appendUnique", "remove"):
        _refuse("profile-type")
    type_name = planner.element_type(target)
    admitted = _reference_members(type_name, planner.types)
    if prop not in admitted:
        _refuse("profile-type")
    raw_values = step.get("values")
    if not isinstance(raw_values, list):
        _refuse("profile-type")
    ids: list[str] = []
    for entry in raw_values:
        if not isinstance(entry, dict):
            _refuse("profile-type")
        if entry.get("op") == "ids":
            ids.extend(_eval_ids(entry.get("select"), bindings, planner.context))
            continue
        value = _eval_plan_value(entry, bindings, planner.context)
        if _is_missing(value) or not isinstance(value, str):
            _refuse("profile-type")
        ids.append(value)
    _check_reference_targets(planner, ids)
    stored = planner.stored(target, prop)
    cardinality = _reference_cardinality(type_name, prop, planner.types, stored)
    planner.authorize(type_name, prop)
    result = _assignref_result(stored, ids, mode, cardinality)
    effective = (result is _MISSING and stored is not _MISSING) or (
        result is not _MISSING and (stored is _MISSING or stored != result)
    )
    planner.gate_lane_write(target, prop, effective=effective, removal=mode == "remove")
    planner.gate_port_fill(target, prop, stored, effective=effective)
    _check_support_handle_assign(planner, raw_target, target, stored, result)
    planner.writes.append(
        {
            "op": "assignRef",
            "recipeId": planner.recipe_id,
            "target": _element_ref(target, planner.planned, planner.context),
            "property": prop,
            "mode": mode,
            "ids": ids,
            "cardinality": cardinality,
            "targetTypes": _target_types(type_name, prop, planner.types),
        }
    )


def _check_reference_targets(planner: _Planner, ids: list[str]) -> None:
    """Validate assignRef target existence (type is apply's check, §4.2)."""
    known = planner.context.by_id
    planned_ids = {entry.planned_id for entry in planner.planned if entry.planned_id}
    for item in ids:
        if known.get(item) is None and item not in planned_ids:
            _refuse("reference-dangling")


def _check_support_handle_assign(
    planner: _Planner,
    raw_target: object,
    target: dict[str, Any],
    stored: object,
    result: object,
) -> None:
    """Enforce the assignRef-to-support-handle rule (§6.3).

    A write on an ensure handle may only fill an absent reference or
    confirm the stored value; any different stored value refuses
    ``support-binding-conflict``.
    """
    if not isinstance(raw_target, str):
        return
    handled = any(
        entry.element is target and entry.ensure_role is not None for entry in planner.planned
    )
    if not handled:
        return
    if stored is _MISSING or stored == result:
        return
    if stored == "" and result is _MISSING:
        return
    _refuse("support-binding-conflict")


def _exec_reparent(planner: _Planner, step: dict[str, Any], bindings: dict[str, object]) -> None:
    """Execute one reparent step (records the write, §4.2/§6.4)."""
    target = _lookup(step.get("target"), bindings, required=True)
    parent = _lookup(step.get("parent"), bindings, required=True)
    if not isinstance(target, dict) or not isinstance(parent, dict):
        _refuse("profile-type")
    prop = _bare_property(step.get("property"))
    position = step.get("position")
    if position not in ("first", "last", "preserve"):
        _refuse("profile-type")
    parent_type = planner.element_type(parent)
    _check_containment_admission(planner, parent_type, prop, planner.element_type(target))
    planner.authorize(parent_type, prop)
    cardinality = _containment_cardinality(parent_type, prop, planner.types)
    if position == "preserve":
        current = planner.context.parents.get(id(target))
        if (
            current is not parent or _child_property(current, parent, prop, target) != prop
        ) and not _planned_location_matches(planner, target, parent, prop):
            _refuse("profile-type")
    planner.writes.append(
        {
            "op": "reparent",
            "recipeId": planner.recipe_id,
            "target": _element_ref(target, planner.planned, planner.context),
            "parent": _element_ref(parent, planner.planned, planner.context),
            "property": prop,
            "position": position,
            "cardinality": cardinality,
        }
    )


def _planned_location_matches(
    planner: _Planner, target: dict[str, Any], parent: dict[str, Any], prop: str
) -> bool:
    """Return whether a planned target already sits at one location."""
    for entry in planner.planned:
        if entry.element is not target:
            continue
        creating = planner.writes[entry.write_index]
        if creating.get("op") != "create" or creating.get("property") != prop:
            return False
        return _resolve_write_ref(planner, creating.get("parent")) is parent
    return False


def _resolve_write_ref(planner: _Planner, ref: object) -> dict[str, Any] | None:
    """Resolve one ``id``/``pointer``/``handle`` reference to a snapshot element."""
    if not isinstance(ref, dict):
        return None
    if isinstance(ref.get("id"), str):
        found = planner.context.by_id.get(ref["id"])
        return found if isinstance(found, dict) else None
    if isinstance(ref.get("pointer"), str):
        return _walk_pointer(planner.snapshot, ref["pointer"])
    if isinstance(ref.get("handle"), int):
        index = ref["handle"]
        if 0 <= index < len(planner.writes):
            for entry in planner.planned:
                if entry.write_index == index:
                    return entry.element
        return None
    return None


def _walk_pointer(tree: dict[str, Any], pointer: str) -> dict[str, Any] | None:
    """Walk one absolute pointer from a tree root (None when unresolvable)."""
    if pointer == "":
        return tree
    current: object = tree
    for raw in pointer[1:].split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            if not part.isdigit():
                return None
            position = int(part)
            current = current[position] if 0 <= position < len(current) else None
        else:
            return None
        if current is None:
            return None
    return current if isinstance(current, dict) else None


def _exec_place(  # noqa: C901 - one branch per placement part
    planner: _Planner, step: dict[str, Any], bindings: dict[str, object]
) -> None:
    """Execute one place step (records the evaluated placement)."""
    target = _lookup(step.get("target"), bindings, required=True)
    owner = _lookup(step.get("owner"), bindings, required=True)
    if not isinstance(target, dict) or not isinstance(owner, dict):
        _refuse("profile-type")
    region = step.get("region")
    if not isinstance(region, str):
        _refuse("profile-type")
    related = _run_select(step.get("related"), bindings, planner.context)
    related_ids: list[str] = []
    for handle in related:
        if handle.element_id is None:
            _refuse("profile-type")
        related_ids.append(handle.element_id)
    related_ids = sorted(set(related_ids), key=_utf16)
    element_id = target.get("id")
    owner_id = owner.get("id")
    if not isinstance(element_id, str) or not isinstance(owner_id, str):
        _refuse("profile-type")
    write: dict[str, Any] = {
        "op": "place",
        "recipeId": planner.recipe_id,
        "elementId": element_id,
        "ownerProcessId": owner_id,
        "regionKey": region,
        "relatedAssociationIds": related_ids,
    }
    anchor_name = step.get("anchor")
    if anchor_name is not None:
        if not isinstance(anchor_name, str) or anchor_name not in bindings:
            _refuse("profile-symbol")
        anchor = bindings[anchor_name]
        if not _is_missing(anchor):
            if not isinstance(anchor, dict):
                _refuse("profile-type")
            anchor_id = anchor.get("id")
            if not isinstance(anchor_id, str):
                _refuse("profile-type")
            write["anchorAssociationId"] = anchor_id
    planner.writes.append(write)


def _closure_ids(target: dict[str, Any], dependents: list[dict[str, Any]]) -> list[str]:
    """Collect the UTF-16 sorted ID-bearing ids of one deletion closure."""
    found: list[str] = []
    stack: list[object] = [target, *dependents]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if not isinstance(current, dict) or id(current) in seen:
            continue
        seen.add(id(current))
        element_id = current.get("id")
        if isinstance(element_id, str) and element_id not in found:
            found.append(element_id)
        for value in current.values():
            if isinstance(value, dict):
                stack.append(value)
            elif isinstance(value, list):
                stack.extend(entry for entry in value if isinstance(entry, dict))
    return sorted(found, key=_utf16)


def _exec_remove(  # noqa: C901 - one branch per removal check
    planner: _Planner,
    step: dict[str, Any],
    bindings: dict[str, object],
    *,
    authority_deletion: bool,
) -> None:
    """Execute one remove step (records the write, §6.4)."""
    if not authority_deletion:
        _refuse("profile-producer")
    target = _lookup(step.get("target"), bindings, required=True)
    if not isinstance(target, dict):
        _refuse("profile-type")
    policy = step.get("policy")
    if policy not in ("refuseIfReferenced", "includeDeclared"):
        _refuse("profile-type")
    dependents = _run_select(step.get("dependents"), bindings, planner.context)
    dependent_elements = [handle.element for handle in dependents]
    delete_ids = _closure_ids(target, dependent_elements)
    doomed = set(delete_ids)
    for element in planner.context.elements:
        if not isinstance(element, dict):
            continue
        element_id = element.get("id")
        if isinstance(element_id, str) and element_id in doomed:
            continue
        type_name = element.get("$type")
        refs = _reference_members(type_name, planner.types) if isinstance(type_name, str) else {}
        for key in refs:
            if _names_id(element.get(key), doomed):
                _refuse("reference-dangling")
    for record in planner.context.envelope["bindings"]:
        if not isinstance(record, dict):
            continue
        if record.get("ownerId") in doomed:
            _refuse("reference-dangling")
    planner.writes.append(
        {
            "op": "remove",
            "recipeId": planner.recipe_id,
            "target": _element_ref(target, planner.planned, planner.context),
            "policy": policy,
            "deleteIds": delete_ids,
        }
    )


def _names_id(value: object, doomed: set[str]) -> bool:
    """Return whether one member value names a doomed id."""
    if isinstance(value, str):
        return value != "" and value in doomed
    if isinstance(value, list):
        return any(isinstance(item, str) and item != "" and item in doomed for item in value)
    return False


def _normalize_authority(authority: object) -> tuple[str, str, bool]:
    """Validate one authority record (invalid invocations refuse)."""
    if isinstance(authority, Mapping):
        keys = set(authority.keys())
        if keys != {"actor", "activation", "deletionIntent"}:
            _refuse("operation-error")
        actor = authority.get("actor")
        activation = authority.get("activation")
        deletion = authority.get("deletionIntent")
    else:
        actor = getattr(authority, "actor", None)
        activation = getattr(authority, "activation", None)
        deletion = getattr(authority, "deletion_intent", None)
    if (
        not isinstance(actor, str)
        or actor not in ("editor", "code")
        or not isinstance(activation, str)
        or activation not in ("edit", "qualification")
        or not isinstance(deletion, bool)
    ):
        _refuse("operation-error")
    return actor, activation, deletion


def _bind_params(  # noqa: C901, PLR0912 - one branch per parameter kind
    planner: _Planner, declared: object, params: Mapping[str, Any]
) -> dict[str, object]:
    """Validate and bind one parameter map in declaration order."""
    if not isinstance(declared, list):
        _refuse("profile-ui-parameters")
    bound: dict[str, object] = {}
    names: set[str] = set()
    for entry in declared:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            _refuse("profile-ui-parameters")
        name = entry["name"]
        kind = entry.get("type")
        required = entry.get("required", False)
        names.add(name)
        if name not in params:
            if required is True:
                _refuse("profile-ui-parameters")
            bound[name] = _MISSING
            continue
        value = params[name]
        if kind == "element":
            if not isinstance(value, str):
                _refuse("profile-type")
            element = planner.context.by_id.get(value)
            if not isinstance(element, dict):
                _refuse("reference-dangling")
            bound[name] = element
        elif kind == "string":
            if not isinstance(value, str):
                _refuse("profile-type")
            bound[name] = value
        elif kind == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                _refuse("profile-type")
            bound[name] = value
        elif kind == "boolean":
            if not isinstance(value, bool):
                _refuse("profile-type")
            bound[name] = value
        elif kind == "array":
            if not isinstance(value, list):
                _refuse("profile-type")
            bound[name] = value
        else:
            _refuse("profile-type")
    for name in params:
        if name not in names:
            _refuse("profile-ui-parameters")
    return bound


def _exec_step(  # noqa: C901, PLR0912 - one branch per step op
    planner: _Planner,
    step: object,
    bindings: dict[str, object],
    *,
    deletion_intent: bool,
) -> None:
    """Execute one recipe step (a reached refuse aborts the plan)."""
    if not isinstance(step, dict):
        _refuse("profile-type")
    op = step.get("op")
    if op == "bind":
        _exec_bind(planner, step, bindings)
    elif op == "create":
        _exec_create(planner, step, bindings)
    elif op == "ensure":
        _exec_ensure(planner, step, bindings)
    elif op == "set":
        _exec_set(planner, step, bindings)
    elif op == "unset":
        _exec_unset(planner, step, bindings)
    elif op == "assignRef":
        _exec_assign_ref(planner, step, bindings)
    elif op == "reparent":
        _exec_reparent(planner, step, bindings)
    elif op == "place":
        _exec_place(planner, step, bindings)
    elif op == "remove":
        _exec_remove(planner, step, bindings, authority_deletion=deletion_intent)
    elif op == "refuse":
        code = step.get("code")
        if not isinstance(code, str):
            _refuse("profile-type")
        _refuse_step(code)
    elif op == "emit":
        _refuse("profile-action-phase")
    else:
        _refuse("profile-type")


def _plan_recipe_impl(  # noqa: C901, PLR0912, PLR0913 - one branch per plan check
    recipe: object,
    read_context: object,
    params: object,
    authority: object,
    *,
    gates: bool,
    shared: _Shared | None = None,
) -> PureResult:
    """Plan one recipe against a lot-3 read context (the shared driver)."""
    try:
        if not isinstance(read_context, ReadContext):
            _refuse("operation-error")
        if (
            read_context.compiled is None
            or not read_context.descriptor_types
            or read_context.producers is None
        ):
            _refuse("operation-error")
        actor, activation, deletion_intent = _normalize_authority(authority)
        if not isinstance(params, Mapping):
            _refuse("operation-error")
        if not isinstance(recipe, dict) or not isinstance(recipe.get("id"), str):
            _refuse("profile-symbol")
        compiled = read_context.compiled
        if compiled is None:
            _refuse("operation-error")
        expected = compiled.recipes.get(recipe["id"])
        if expected is None or jcs(recipe) != jcs(expected):
            _refuse("profile-symbol")
        phase = recipe.get("phase")
        if phase == "export":
            _refuse("profile-action-phase")
        if phase in _CODE_PHASES:
            if actor != "code":
                _refuse("profile-producer")
        elif actor != "editor":
            _refuse("profile-producer")
        planner = _Planner(
            context=read_context,
            recipe_id=recipe["id"],
            phase=str(phase),
            actor=actor,
            activation=activation,
            gates=gates,
            shared=shared if shared is not None else _Shared(),
        )
        bound = _bind_params(planner, recipe.get("parameters", []), params)
        candidates = _run_select(
            recipe.get("select"), {"root": read_context.root, **bound}, planner.context
        )
        for candidate in candidates:
            local: dict[str, object] = {"root": read_context.root, **bound}
            local["self"] = candidate.element
            outcome = _eval_when(planner, recipe.get("when"), local)
            if not outcome:
                continue
            for step in recipe.get("steps", []):
                _exec_step(planner, step, local, deletion_intent=deletion_intent)
    except _RefuseStepError as exc:
        return pure_refused(exc.code)
    except _RefusalError as exc:
        return pure_refused(exc.code)
    return pure_success(
        {
            "planVersion": _PLAN_VERSION,
            "phase": phase,
            "actor": actor,
            "activation": activation,
            "baseRevision": read_context.revision,
            "writes": planner.writes,
        }
    )


def _eval_when(planner: _Planner, node: object, bindings: dict[str, object]) -> bool:
    """Evaluate one recipe ``when`` guard (errors refuse)."""
    if node is None:
        return True
    outcome = evaluate_predicate(node, planner.context, bindings)
    if isinstance(outcome, PureRefused):
        _refuse(outcome.code)
    return bool(outcome.payload)


def plan_recipe(
    recipe: Mapping[str, object],
    read_context: ReadContext,
    params: Mapping[str, object],
    authority: Authority | Mapping[str, object],
) -> PureResult:
    """Plan one explicit recipe command without applying it (§5.3).

    Returns the WritePlan/1 wire value; explicit plans never enforce the
    open technical gates. Inputs are never mutated.
    """
    return _plan_recipe_impl(
        copy.deepcopy(recipe),
        read_context,
        copy.deepcopy(dict(params)) if isinstance(params, Mapping) else params,
        authority,
        gates=False,
    )
