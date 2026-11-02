"""Lot-3 plan application (DESIGN §2.4 ``applyPlan`` with §4 entries).

Applies one WritePlan/1 to a staged copy in plan order: reference
resolution, coalescing with conflict detection, tree writes with the
carried facts only, no-op detection, and change entries for complete and
normalize plans. The caller's tree and envelope are never mutated.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from bpmn_io.profile._c14n import jcs
from bpmn_io.profile._cn_context import _utf16, to_wire_envelope
from bpmn_io.profile._cn_normalize import sort_placements
from bpmn_io.profile._cn_plan import _assignref_result, _RefusalError, _refuse, _walk_pointer
from bpmn_io.profile._envelope import check_envelope_integrity, check_envelope_shape, sort_bindings
from bpmn_io.profile._evaluate import _MISSING
from bpmn_io.profile._results import (
    Coordinate,
    PureResult,
    ReportEntry,
    pure_refused,
    pure_success,
    sort_report_entries,
)

__all__ = ["ChangeReport", "apply_plan"]

#: Known plan phases.
_PHASES: Final[frozenset[str]] = frozenset(
    {"create", "edit", "reference", "convert", "migrate", "complete", "normalize", "export"}
)

#: Exact write key sets (``id``/``anchorAssociationId`` optional members noted).
_WRITE_KEYS: Final[dict[str, frozenset[str]]] = {
    "create": frozenset(
        {"op", "recipeId", "type", "parent", "property", "fields", "cardinality", "id"}
    ),
    "ensure": frozenset(
        {
            "op",
            "recipeId",
            "decision",
            "ownerId",
            "role",
            "type",
            "parent",
            "property",
            "id",
            "fields",
            "cardinality",
        }
    ),
    "set": frozenset({"op", "recipeId", "target", "property", "value"}),
    "unset": frozenset({"op", "recipeId", "target", "property"}),
    "assignRef": frozenset(
        {"op", "recipeId", "target", "property", "mode", "ids", "cardinality", "targetTypes"}
    ),
    "reparent": frozenset(
        {"op", "recipeId", "target", "parent", "property", "position", "cardinality"}
    ),
    "remove": frozenset({"op", "recipeId", "target", "policy", "deleteIds"}),
    "place": frozenset(
        {
            "op",
            "recipeId",
            "elementId",
            "ownerProcessId",
            "regionKey",
            "relatedAssociationIds",
            "anchorAssociationId",
        }
    ),
}

#: Required write keys (optional members excluded).
_WRITE_REQUIRED: Final[dict[str, frozenset[str]]] = {
    "create": frozenset({"op", "recipeId", "type", "parent", "property", "fields", "cardinality"}),
    "ensure": frozenset(
        {
            "op",
            "recipeId",
            "decision",
            "ownerId",
            "role",
            "type",
            "parent",
            "property",
            "id",
            "fields",
            "cardinality",
        }
    ),
    "set": frozenset({"op", "recipeId", "target", "property", "value"}),
    "unset": frozenset({"op", "recipeId", "target", "property"}),
    "assignRef": frozenset(
        {"op", "recipeId", "target", "property", "mode", "ids", "cardinality", "targetTypes"}
    ),
    "reparent": frozenset(
        {"op", "recipeId", "target", "parent", "property", "position", "cardinality"}
    ),
    "remove": frozenset({"op", "recipeId", "target", "policy", "deleteIds"}),
    "place": frozenset(
        {"op", "recipeId", "elementId", "ownerProcessId", "regionKey", "relatedAssociationIds"}
    ),
}


@dataclass(frozen=True)
class ChangeReport:
    """One applied plan: staged tree, bindings, entries and placements."""

    tree: dict[str, Any]
    bindings: list[dict[str, Any]]
    entries: list[ReportEntry]
    placements: list[dict[str, Any]]
    created: list[str]
    removed: list[str]

    def to_json(self) -> dict[str, Any]:
        """Return the ``change/1`` wire value with sorted entries."""
        return {
            "reportVersion": "change/1",
            "tree": copy.deepcopy(self.tree),
            "bindings": copy.deepcopy(self.bindings),
            "entries": [entry.to_json() for entry in sort_report_entries(list(self.entries))],
            "placements": copy.deepcopy(self.placements),
            "created": list(self.created),
            "removed": list(self.removed),
        }


@dataclass
class _Applier:
    """Mutable staged application state over one owned tree copy."""

    tree: dict[str, Any]
    bindings: list[dict[str, Any]]
    input_tree: dict[str, Any]
    input_pointers: dict[int, str]
    input_by_id: dict[str, dict[str, Any]]
    allocated_ids: frozenset[str] = frozenset()
    emit_entries: bool = True
    stage: str = ""
    created_objects: dict[int, dict[str, Any]] = field(default_factory=dict)
    removed_ids: set[str] = field(default_factory=set)
    entries: list[ReportEntry] = field(default_factory=list)
    placements: list[dict[str, Any]] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    def by_id(self) -> dict[str, dict[str, Any]]:
        """Index the current staged tree by id (fresh scan)."""
        found: dict[str, dict[str, Any]] = {}
        stack: list[object] = [self.tree]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                element_id = current.get("id")
                if isinstance(element_id, str) and element_id not in found:
                    found[element_id] = current
                stack.extend(current.values())
            elif isinstance(current, list):
                stack.extend(current)
        return found

    def output_pointers(self) -> dict[int, str]:
        """Index the current staged tree pointers (fresh walk)."""
        pointers: dict[int, str] = {}
        stack: list[tuple[dict[str, Any], str]] = [(self.tree, "")]
        seen: set[int] = set()
        while stack:
            node, pointer = stack.pop()
            if id(node) in seen:
                continue
            seen.add(id(node))
            pointers[id(node)] = pointer
            pending: list[tuple[dict[str, Any], str]] = []
            for key in node:
                value = node[key]
                segment = key.replace("~", "~0").replace("/", "~1")
                if isinstance(value, dict):
                    pending.append((value, f"{pointer}/{segment}"))
                elif isinstance(value, list):
                    for position, entry in enumerate(value):
                        if isinstance(entry, dict):
                            pending.append((entry, f"{pointer}/{segment}/{position}"))
            stack.extend(reversed(pending))
        return pointers


def _validate_write(write: object) -> dict[str, Any]:
    """Validate one planned write shape (``operation-error`` when malformed)."""
    if not isinstance(write, dict):
        _refuse("operation-error")
    op = write.get("op")
    if not isinstance(op, str) or op not in _WRITE_KEYS:
        _refuse("operation-error")
    keys = set(write.keys())
    if not _WRITE_REQUIRED[op] <= keys <= _WRITE_KEYS[op]:
        _refuse("operation-error")
    if not isinstance(write.get("recipeId"), str):
        _refuse("operation-error")
    for key in ("target", "parent"):
        if key in write and not _is_ref(write[key]):
            _refuse("operation-error")
    if "ids" in write and (
        not isinstance(write["ids"], list)
        or not all(isinstance(item, str) for item in write["ids"])
    ):
        _refuse("operation-error")
    if "deleteIds" in write and (
        not isinstance(write["deleteIds"], list)
        or not all(isinstance(item, str) for item in write["deleteIds"])
    ):
        _refuse("operation-error")
    if "fields" in write and not isinstance(write["fields"], dict):
        _refuse("operation-error")
    return write


def _is_ref(value: object) -> bool:
    """Return whether one value is a well-formed element reference."""
    if not isinstance(value, dict):
        return False
    if isinstance(value.get("id"), str) and len(value) == 1:
        return True
    if isinstance(value.get("pointer"), str) and len(value) == 1:
        return True
    return isinstance(value.get("handle"), int) and len(value) == 1


def _location_key(ref: object) -> tuple[str, str]:
    """Return the grouping key of one element reference."""
    if not isinstance(ref, dict):
        _refuse("operation-error")
    if isinstance(ref.get("id"), str):
        return ("id", ref["id"])
    if isinstance(ref.get("pointer"), str):
        return ("pointer", ref["pointer"])
    handle = ref.get("handle")
    if not isinstance(handle, int):
        _refuse("operation-error")
    return ("handle", str(handle))


def _coalesce_writes(  # noqa: C901, PLR0912, PLR0915 - one branch per write kind
    writes: list[dict[str, Any]],
) -> tuple[list[tuple[int, dict[str, Any]]], dict[int, int]]:
    """Coalesce one plan's writes in order (conflicts refuse, §5.4).

    Returns the surviving ``(original index, write)`` pairs with a handle
    alias map for identically coalesced creations.
    """
    merged: list[tuple[int, dict[str, Any]]] = []
    by_location: dict[tuple[Any, ...], int] = {}
    creations: dict[str, int] = {}
    removed: set[tuple[str, str]] = set()
    written: set[tuple[str, str]] = set()
    alias: dict[int, int] = {}
    for position, write in enumerate(writes):
        op = write["op"]
        if op in ("create", "ensure"):
            if op == "create" and _location_key(write["parent"]) in removed:
                _refuse("profile-write-conflict")
            _coalesce_creation(position, write, merged, creations, alias)
        elif op in ("set", "unset", "assignRef"):
            target_key = _location_key(write["target"])
            if target_key in removed:
                _refuse("profile-write-conflict")
            written.add(target_key)
            _coalesce_value_write(position, write, merged, by_location)
        elif op == "reparent":
            target_key = _location_key(write["target"])
            if target_key in removed:
                _refuse("profile-write-conflict")
            written.add(target_key)
            key: tuple[Any, ...] = ("reparent", target_key)
            known = by_location.get(key)
            current = (
                _location_key(write["parent"]),
                write["property"],
                write["position"],
            )
            if known is None:
                by_location[key] = len(merged)
                merged.append((position, write))
            elif (
                _location_key(merged[known][1]["parent"]),
                merged[known][1]["property"],
                merged[known][1]["position"],
            ) != current:
                _refuse("profile-write-conflict")
        elif op == "remove":
            target_key = _location_key(write["target"])
            if target_key in written:
                _refuse("profile-write-conflict")
            removed.add(target_key)
            key = ("remove", target_key)
            if key not in by_location:
                by_location[key] = len(merged)
                merged.append((position, write))
        elif op == "place":
            key = ("place", write["elementId"], write["regionKey"])
            known = by_location.get(key)
            current = (
                write["ownerProcessId"],
                tuple(write["relatedAssociationIds"]),
                write.get("anchorAssociationId"),
            )
            if known is None:
                by_location[key] = len(merged)
                merged.append((position, write))
            elif (
                merged[known][1]["ownerProcessId"],
                tuple(merged[known][1]["relatedAssociationIds"]),
                merged[known][1].get("anchorAssociationId"),
            ) != current:
                _refuse("profile-write-conflict")
        else:
            _refuse("operation-error")
    return merged, alias


def _coalesce_creation(
    position: int,
    write: dict[str, Any],
    merged: list[tuple[int, dict[str, Any]]],
    creations: dict[str, int],
    alias: dict[int, int],
) -> None:
    """Coalesce one creation write (identical merges, collisions refuse)."""
    if write["op"] == "ensure" and write.get("decision") == "reuse":
        merged.append((position, write))
        return
    new_id = write.get("id")
    if not isinstance(new_id, str):
        merged.append((position, write))
        return
    key = (
        write["type"],
        _location_key(write["parent"]),
        write["property"],
        jcs(write["fields"]),
        new_id,
    )
    known = creations.get(new_id)
    if known is None:
        creations[new_id] = len(merged)
        merged.append((position, write))
        return
    survivor = merged[known][1]
    if (
        survivor["type"],
        _location_key(survivor["parent"]),
        survivor["property"],
        jcs(survivor["fields"]),
        survivor.get("id"),
    ) != key:
        _refuse("id-collision")
    alias[position] = merged[known][0]


def _coalesce_value_write(
    position: int,
    write: dict[str, Any],
    merged: list[tuple[int, dict[str, Any]]],
    by_location: dict[tuple[Any, ...], int],
) -> None:
    """Coalesce one scalar/reference write on a written location."""
    key = ("value", _location_key(write["target"]), write["property"])
    known = by_location.get(key)
    if known is None:
        by_location[key] = len(merged)
        merged.append((position, dict(write)))
        return
    first = merged[known][1]
    if first["op"] != write["op"]:
        _refuse("profile-write-conflict")
    if write["op"] == "set":
        if first["value"] != write["value"]:
            _refuse("profile-write-conflict")
    elif write["op"] == "unset":
        pass
    elif write["op"] == "assignRef":
        _merge_assign_ref(first, write)
    else:
        _refuse("operation-error")


def _merge_single_assign_ref(first: dict[str, Any], second: dict[str, Any]) -> None:
    """Merge one single-cardinality assignRef write into its survivor.

    Same-mode ``appendUnique``/``remove`` writes union their ids (the sealed
    no-invention witness stores both members as one list); anything else for
    one single (target, property) refuses ``profile-write-conflict``.
    """
    first_mode = first["mode"]
    if first_mode == "replace" or second["mode"] == "replace":
        if first_mode != second["mode"] or first.get("ids") != second.get("ids"):
            _refuse("profile-write-conflict")
        return
    if first_mode == second["mode"] and first_mode in ("appendUnique", "remove"):
        united = sorted(set(first.get("ids", [])) | set(second.get("ids", [])), key=_utf16)
        first["ids"] = united
        return
    _refuse("profile-write-conflict")


def _merge_assign_ref(first: dict[str, Any], second: dict[str, Any]) -> None:
    """Merge one assignRef write into its location survivor (in place)."""
    if first.get("cardinality") == "single" or second.get("cardinality") == "single":
        _merge_single_assign_ref(first, second)
        return

    def _parts(write: dict[str, Any]) -> tuple[set[str], set[str]]:
        mode = write["mode"]
        if mode == "appendUnique":
            return set(write["ids"]), set()
        if mode == "remove":
            return set(), set(write["ids"])
        if mode == "delta":
            return set(write.get("append", [])), set(write.get("remove", []))
        return set(), set()

    first_mode = first["mode"]
    second_mode = second["mode"]
    if first_mode == "replace" or second_mode == "replace":
        if first_mode != second_mode or first["ids"] != second["ids"]:
            _refuse("profile-write-conflict")
        return
    first_append, first_remove = _parts(first)
    second_append, second_remove = _parts(second)
    append = first_append | second_append
    remove = first_remove | second_remove
    if append & remove:
        _refuse("profile-write-conflict")
    first["mode"] = "delta"
    first["append"] = sorted(append, key=_utf16)
    first["remove"] = sorted(remove, key=_utf16)


@dataclass
class _Record:
    """One applied write with its input/output coordinates for entries."""

    write: dict[str, Any]
    out_object: dict[str, Any] | None
    input_target: dict[str, Any] | None
    input_pointer: str | None
    source_id: str | None
    prop: str | None
    before: object = None
    before_present: bool = False
    after: object = None
    after_present: bool = False
    effective: bool = True


def _nearest_input_id(
    input_target: dict[str, Any] | None,
    input_parents: dict[int, dict[str, Any]],
    skip: frozenset[str] = frozenset(),
) -> str | None:
    """Return the input id or nearest ID-bearing ancestor id (else None).

    Ids in ``skip`` (allocated by the run itself) are invisible: source
    coordinates address the phase-start input.
    """
    current = input_target
    seen = 0
    while isinstance(current, dict) and seen < 10000:
        seen += 1
        element_id = current.get("id")
        if isinstance(element_id, str) and element_id not in skip:
            return element_id
        current = input_parents.get(id(current))
    return None


def _input_parents(tree: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Map each input node to its parent (single bounded walk)."""
    parents: dict[int, dict[str, Any]] = {}
    stack: list[dict[str, Any]] = [tree]
    seen: set[int] = set()
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        for value in node.values():
            if isinstance(value, dict):
                parents.setdefault(id(value), node)
                stack.append(value)
            elif isinstance(value, list):
                for entry in value:
                    if isinstance(entry, dict):
                        parents.setdefault(id(entry), node)
                        stack.append(entry)
    return parents


def _resolve_staged(
    applier: _Applier, ref: dict[str, Any], alias: dict[int, int]
) -> dict[str, Any] | None:
    """Resolve one reference against the evolving staged tree."""
    if isinstance(ref.get("id"), str):
        return applier.by_id().get(ref["id"])
    if isinstance(ref.get("pointer"), str):
        return _walk_pointer(applier.tree, ref["pointer"])
    handle = ref.get("handle")
    if isinstance(handle, int):
        return applier.created_objects.get(alias.get(handle, handle))
    return None


def _input_side(
    applier: _Applier,
    ref: dict[str, Any],
    input_parents: dict[int, dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Resolve one reference against the immutable input snapshot."""
    if isinstance(ref.get("id"), str):
        target = applier.input_by_id.get(ref["id"])
        if target is None:
            return None, None, None
        pointer = applier.input_pointers.get(id(target))
        return target, pointer, _nearest_input_id(target, input_parents, applier.allocated_ids)
    if isinstance(ref.get("pointer"), str):
        target = _walk_pointer(applier.input_tree, ref["pointer"])
        if target is None:
            return None, None, None
        return (
            target,
            ref["pointer"],
            _nearest_input_id(target, input_parents, applier.allocated_ids),
        )
    return None, None, None


def _detach(container: dict[str, Any], prop: str, target: dict[str, Any]) -> bool:
    """Detach one child from its container (True when removed)."""
    slot = container.get(prop, _MISSING)
    if slot is target:
        del container[prop]
        return True
    if isinstance(slot, list):
        for position, entry in enumerate(slot):
            if entry is target:
                del slot[position]
                return True
    return False


def _apply_create(
    applier: _Applier,
    write: dict[str, Any],
    position: int,
    alias: dict[int, int],
    input_parents: dict[int, dict[str, Any]],
) -> _Record:
    """Apply one create/ensure-create write with carried facts."""
    del input_parents
    parent = _resolve_staged(applier, write["parent"], alias)
    if parent is None:
        _refuse("operation-error")
    new_id = write.get("id")
    if isinstance(new_id, str) and new_id in applier.by_id():
        _refuse("id-collision")
    element: dict[str, Any] = {"$type": write["type"]}
    if isinstance(new_id, str):
        element["id"] = new_id
    element.update(copy.deepcopy(write["fields"]))
    prop = write["property"]
    cardinality = write["cardinality"]
    slot = parent.get(prop, _MISSING)
    if cardinality == "single":
        if slot is not _MISSING:
            _refuse("profile-type")
        parent[prop] = element
    elif slot is _MISSING:
        parent[prop] = [element]
    elif isinstance(slot, list):
        slot.append(element)
    else:
        _refuse("profile-type")
    applier.created_objects[position] = element
    if isinstance(new_id, str):
        applier.created.append(new_id)
    return _Record(
        write=write,
        out_object=element,
        input_target=None,
        input_pointer=None,
        source_id=None,
        prop=prop,
        before=None,
        before_present=False,
        after=copy.deepcopy(element),
        after_present=True,
        effective=True,
    )


def _apply_set(
    applier: _Applier,
    write: dict[str, Any],
    alias: dict[int, int],
    input_parents: dict[int, dict[str, Any]],
) -> _Record:
    """Apply one set/unset write."""
    target = _resolve_staged(applier, write["target"], alias)
    if target is None:
        if _gone(applier, write["target"]):
            _refuse("profile-write-conflict")
        _refuse("operation-error")
    prop = write["property"]
    input_target, input_pointer, source_id = _input_side(applier, write["target"], input_parents)
    stored = input_target.get(prop, _MISSING) if input_target is not None else _MISSING
    if write["op"] == "set":
        value = copy.deepcopy(write["value"])
        target[prop] = value
        effective = stored is _MISSING or stored != value
        return _Record(
            write=write,
            out_object=target,
            input_target=input_target,
            input_pointer=input_pointer,
            source_id=source_id,
            prop=prop,
            before=None if stored is _MISSING else copy.deepcopy(stored),
            before_present=stored is not _MISSING,
            after=value,
            after_present=True,
            effective=effective,
        )
    effective = stored is not _MISSING
    if prop in target:
        del target[prop]
    return _Record(
        write=write,
        out_object=target,
        input_target=input_target,
        input_pointer=input_pointer,
        source_id=source_id,
        prop=prop,
        before=None if stored is _MISSING else copy.deepcopy(stored),
        before_present=stored is not _MISSING,
        after=None,
        after_present=False,
        effective=effective,
    )


def _gone(applier: _Applier, ref: dict[str, Any]) -> bool:
    """Return whether one reference names a removed element."""
    return isinstance(ref.get("id"), str) and ref["id"] in applier.removed_ids


def _apply_assign_ref(  # noqa: C901, PLR0912 - one branch per assign mode
    applier: _Applier,
    write: dict[str, Any],
    alias: dict[int, int],
    input_parents: dict[int, dict[str, Any]],
) -> _Record:
    """Apply one assignRef write with the carried facts (§4.2)."""
    target = _resolve_staged(applier, write["target"], alias)
    if target is None:
        if _gone(applier, write["target"]):
            _refuse("profile-write-conflict")
        _refuse("operation-error")
    prop = write["property"]
    cardinality = write["cardinality"]
    admitted = tuple(write.get("targetTypes", ()))
    mode = write["mode"]
    known = applier.by_id()
    result: object = None
    if mode == "delta":
        if cardinality == "single":
            _refuse("operation-error")
        for item in [*write.get("append", []), *write.get("remove", [])]:
            if item not in known:
                _refuse("reference-dangling")
            item_type = known[item].get("$type")
            if not isinstance(item_type, str) or item_type not in admitted:
                _refuse("profile-type")
        stored_now = target.get(prop, _MISSING)
        base = (
            list(stored_now)
            if isinstance(stored_now, list)
            else ([] if stored_now is _MISSING else [stored_now])
        )
        remove = set(write.get("remove", []))
        append = [item for item in write.get("append", []) if item not in base]
        merged_now: list[str] = [item for item in base if item not in remove]
        result = [*merged_now, *sorted(append, key=_utf16)]
    else:
        ids = list(write["ids"]) if isinstance(write.get("ids"), list) else []
        for item in ids:
            if item not in known:
                _refuse("reference-dangling")
            item_type = known[item].get("$type")
            if not isinstance(item_type, str) or item_type not in admitted:
                _refuse("profile-type")
        result = _assignref_result(target.get(prop, _MISSING), ids, mode, cardinality)
    input_target, input_pointer, source_id = _input_side(applier, write["target"], input_parents)
    stored = input_target.get(prop, _MISSING) if input_target is not None else _MISSING
    if result is _MISSING:
        effective = stored is not _MISSING
        if prop in target:
            del target[prop]
        return _Record(
            write=write,
            out_object=target,
            input_target=input_target,
            input_pointer=input_pointer,
            source_id=source_id,
            prop=prop,
            before=None if stored is _MISSING else copy.deepcopy(stored),
            before_present=stored is not _MISSING,
            after=None,
            after_present=False,
            effective=effective,
        )
    value = copy.deepcopy(result)
    target[prop] = value
    effective = stored is _MISSING or stored != value
    return _Record(
        write=write,
        out_object=target,
        input_target=input_target,
        input_pointer=input_pointer,
        source_id=source_id,
        prop=prop,
        before=None if stored is _MISSING else copy.deepcopy(stored),
        before_present=stored is not _MISSING,
        after=value,
        after_present=True,
        effective=effective,
    )


def _apply_reparent(  # noqa: C901 - one branch per reparent position
    applier: _Applier,
    write: dict[str, Any],
    alias: dict[int, int],
    input_parents: dict[int, dict[str, Any]],
) -> _Record:
    """Apply one reparent write with the carried facts."""
    target = _resolve_staged(applier, write["target"], alias)
    parent = _resolve_staged(applier, write["parent"], alias)
    if target is None or parent is None:
        _refuse("operation-error")
    prop = write["property"]
    position = write["position"]
    cardinality = write["cardinality"]
    input_target, input_pointer, source_id = _input_side(applier, write["target"], input_parents)
    before_parent = _nearest_input_id(
        input_parents.get(id(input_target)) if input_target is not None else None,
        input_parents,
        applier.allocated_ids,
    )
    current_parents = _input_parents(applier.tree)
    current = current_parents.get(id(target))
    prior = _child_index(current, target)
    prior_prop = _via_prop(current, target)
    if current is not None:
        for key in list(current.keys()):
            if _detach(current, key, target):
                break
    slot = parent.get(prop, _MISSING)
    if cardinality == "single":
        if slot is not _MISSING:
            _refuse("profile-type")
        parent[prop] = target
        index = 0
    else:
        if slot is _MISSING:
            parent[prop] = []
            slot = parent[prop]
        if not isinstance(slot, list):
            _refuse("profile-type")
        if position == "first":
            slot.insert(0, target)
            index = 0
        elif position == "preserve":
            index = min(len(slot), prior)
            slot.insert(index, target)
        else:
            slot.append(target)
            index = len(slot) - 1
    effective = current is not parent or prior_prop != prop or prior != index
    after_parent = parent.get("id") if isinstance(parent.get("id"), str) else None
    return _Record(
        write=write,
        out_object=target,
        input_target=input_target,
        input_pointer=input_pointer,
        source_id=source_id,
        prop=prop,
        before=before_parent,
        before_present=before_parent is not None,
        after=after_parent,
        after_present=after_parent is not None,
        effective=effective,
    )


def _child_index(current: dict[str, Any] | None, target: dict[str, Any]) -> int:
    """Return the pre-detach index of one child (-1 when unknown)."""
    if current is None:
        return -1
    for value in current.values():
        if isinstance(value, list):
            for position, entry in enumerate(value):
                if entry is target:
                    return position
    return -1


def _via_prop(current: dict[str, Any] | None, target: dict[str, Any]) -> str | None:
    """Return the containment property holding one child (None when unknown)."""
    if current is None:
        return None
    for key, value in current.items():
        if value is target:
            return key
        if isinstance(value, list) and any(entry is target for entry in value):
            return key
    return None


def _apply_remove(  # noqa: C901 - one branch per removal case
    applier: _Applier,
    write: dict[str, Any],
    alias: dict[int, int],
    input_parents: dict[int, dict[str, Any]],
) -> _Record:
    """Apply one remove write (detaches the closure, cleans bindings)."""
    target = _resolve_staged(applier, write["target"], alias)
    input_target, input_pointer, source_id = _input_side(applier, write["target"], input_parents)
    before = copy.deepcopy(input_target) if input_target is not None else None
    if target is not None and id(target) != id(applier.tree):
        current_parents = _input_parents(applier.tree)
        current = current_parents.get(id(target))
        if current is not None:
            for key in list(current.keys()):
                if _detach(current, key, target):
                    break
    for gone in write["deleteIds"]:
        applier.removed_ids.add(gone)
        if gone not in applier.removed:
            applier.removed.append(gone)
        doomed = applier.by_id().get(gone)
        if doomed is not None and id(doomed) != id(applier.tree):
            doomed_parents = _input_parents(applier.tree)
            container = doomed_parents.get(id(doomed))
            if container is not None:
                for key in list(container.keys()):
                    if _detach(container, key, doomed):
                        break
    return _Record(
        write=write,
        out_object=None,
        input_target=input_target,
        input_pointer=input_pointer,
        source_id=source_id,
        prop=None,
        before=before,
        before_present=before is not None,
        after=None,
        after_present=False,
        effective=True,
    )


def _apply_place(
    applier: _Applier,
    write: dict[str, Any],
) -> None:
    """Collect one place write as a sorted placement record."""
    placement = {
        "elementId": write["elementId"],
        "ownerProcessId": write["ownerProcessId"],
        "regionKey": write["regionKey"],
        "relatedAssociationIds": list(write["relatedAssociationIds"]),
    }
    if write.get("anchorAssociationId") is not None:
        placement["anchorAssociationId"] = write["anchorAssociationId"]
    applier.placements.append(placement)


def _apply_ensure(
    applier: _Applier,
    write: dict[str, Any],
    position: int,
    alias: dict[int, int],
    input_parents: dict[int, dict[str, Any]],
) -> _Record | None:
    """Apply one ensure write (creation plus binding, or reuse)."""
    if write.get("decision") == "reuse":
        record = {
            "ownerId": write["ownerId"],
            "role": write["role"],
            "targetId": write["id"],
        }
        if not any(
            isinstance(entry, dict)
            and entry.get("ownerId") == record["ownerId"]
            and entry.get("role") == record["role"]
            for entry in applier.bindings
        ):
            applier.bindings.append(record)
        return None
    record_created = _apply_create(applier, write, position, alias, input_parents)
    if not any(
        isinstance(entry, dict)
        and entry.get("ownerId") == write["ownerId"]
        and entry.get("role") == write["role"]
        for entry in applier.bindings
    ):
        applier.bindings.append(
            {"ownerId": write["ownerId"], "role": write["role"], "targetId": write["id"]}
        )
    return record_created


def _apply_core(  # noqa: C901, PLR0912, PLR0913 - one branch per applied op
    writes: list[dict[str, Any]],
    *,
    phase: str,
    staged_tree: dict[str, Any],
    staged_bindings: list[dict[str, Any]],
    input_tree: dict[str, Any],
    emit_entries: bool,
    allocated_ids: frozenset[str] = frozenset(),
) -> ChangeReport:
    """Apply validated writes to staged copies (refusals raise)."""
    validated = [_validate_write(write) for write in writes]
    merged, alias = _coalesce_writes(validated)
    input_pointers = _walk_input_pointers(input_tree)
    input_parents = _input_parents(input_tree)
    input_by_id: dict[str, dict[str, Any]] = {}
    stack: list[object] = [input_tree]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            element_id = current.get("id")
            if isinstance(element_id, str) and element_id not in input_by_id:
                input_by_id[element_id] = current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    applier = _Applier(
        tree=staged_tree,
        bindings=staged_bindings,
        input_tree=input_tree,
        input_pointers=input_pointers,
        input_by_id=input_by_id,
        allocated_ids=allocated_ids,
        emit_entries=emit_entries,
        stage=phase,
    )
    records: list[_Record] = []
    for position, write in merged:
        op = write["op"]
        if op == "create":
            records.append(_apply_create(applier, write, position, alias, input_parents))
        elif op == "ensure":
            record = _apply_ensure(applier, write, position, alias, input_parents)
            if record is not None:
                records.append(record)
        elif op in {"set", "unset"}:
            records.append(_apply_set(applier, write, alias, input_parents))
        elif op == "assignRef":
            records.append(_apply_assign_ref(applier, write, alias, input_parents))
        elif op == "reparent":
            records.append(_apply_reparent(applier, write, alias, input_parents))
        elif op == "remove":
            records.append(_apply_remove(applier, write, alias, input_parents))
        elif op == "place":
            _apply_place(applier, write)
        else:
            _refuse("operation-error")
    doomed = set(applier.removed_ids)
    applier.bindings = [
        entry
        for entry in applier.bindings
        if not (isinstance(entry, dict) and entry.get("targetId") in doomed)
    ]
    applier.removed = sorted(applier.removed, key=_utf16)
    entries: list[ReportEntry] = []
    if emit_entries:
        output_pointers = applier.output_pointers()
        output_parents = _input_parents(applier.tree)
        for record in records:
            entry = _record_entry(record, phase, output_pointers, output_parents)
            if entry is not None:
                entries.append(entry)
    return ChangeReport(
        tree=applier.tree,
        bindings=sort_bindings(applier.bindings),
        entries=entries,
        placements=sort_placements(applier.placements),
        created=list(applier.created),
        removed=list(applier.removed),
    )


_ACTION_WORDS: Final[dict[str, str]] = {
    "set": "set",
    "unset": "unset",
    "assignRef": "assignRef",
    "create": "create",
    "ensure": "ensure",
    "reparent": "reparent",
    "remove": "remove",
}


def _escape_pointer_segment(segment: str) -> str:
    """Escape one RFC 6901 pointer segment."""
    return segment.replace("~", "~0").replace("/", "~1")


def _record_entry(
    record: _Record,
    stage: str,
    output_pointers: dict[int, str],
    output_parents: dict[int, dict[str, Any]],
) -> ReportEntry | None:
    """Build one change entry for an effective write (None when silent)."""
    if not record.effective:
        return None
    write = record.write
    op = write["op"]
    action = _ACTION_WORDS.get(op)
    if action is None:
        return None
    code = f"{stage}/{action}"
    if record.input_target is None:
        source = Coordinate(domain="none", pointer=None, target_id=None, provenance="generated")
    else:
        pointer = record.input_pointer or ""
        if record.prop is not None:
            pointer = f"{pointer}/{_escape_pointer_segment(record.prop)}"
        source = Coordinate(
            domain="tree", pointer=pointer, target_id=record.source_id, provenance="exact"
        )
    if record.out_object is None:
        result = Coordinate(domain="none", pointer=None, target_id=None, provenance="unavailable")
    else:
        pointer = output_pointers.get(id(record.out_object), "")
        if record.prop is not None and op not in ("create", "ensure"):
            pointer = f"{pointer}/{_escape_pointer_segment(record.prop)}"
        result_target = _nearest_input_id(record.out_object, output_parents)
        result = Coordinate(
            domain="tree",
            pointer=pointer,
            target_id=result_target,
            provenance="generated" if result_target != record.source_id else "exact",
        )
    if op in ("create", "ensure") and record.after_present and record.out_object is not None:
        after: object = copy.deepcopy(record.out_object)
    elif record.after_present:
        after = copy.deepcopy(record.after)
    else:
        after = None
    return ReportEntry(
        rule_id=write["recipeId"],
        code=code,
        message_key=code.replace("/", ".", 1),
        severity="info",
        classification="repairable",
        source=source,
        result=result,
        stage=stage,
        disposition="corrected",
        before_present=record.before_present,
        after_present=record.after_present,
        before=copy.deepcopy(record.before),
        after=after,
        property=record.prop,
    )


def apply_plan(
    plan: Mapping[str, object],
    staged_tree: Mapping[str, object],
    staged_envelope: Mapping[str, object],
) -> PureResult:
    """Apply one WritePlan/1 to staged copies (§5.4).

    Returns the ChangeReport/1 wire value; inputs are never mutated.
    """
    try:
        if not isinstance(plan, Mapping):
            _refuse("operation-error")
        owned_plan: dict[str, Any] = copy.deepcopy(dict(plan))
        if (
            owned_plan.get("planVersion") != "1"
            or not isinstance(owned_plan.get("phase"), str)
            or owned_plan.get("phase") not in _PHASES
            or owned_plan.get("actor") not in ("editor", "code")
            or owned_plan.get("activation") not in ("edit", "qualification")
            or not isinstance(owned_plan.get("baseRevision"), str)
            or not isinstance(owned_plan.get("writes"), list)
        ):
            _refuse("operation-error")
        wire_envelope = to_wire_envelope(staged_envelope)
        if not isinstance(staged_tree, Mapping) or not isinstance(wire_envelope, Mapping):
            _refuse("operation-error")
        owned_tree: dict[str, Any] = copy.deepcopy(dict(staged_tree))
        owned_envelope: dict[str, Any] = copy.deepcopy(dict(wire_envelope))
        failed = check_envelope_shape(owned_envelope)
        if failed is not None:
            _refuse(failed)
        failed = check_envelope_integrity(owned_envelope)
        if failed is not None:
            _refuse(failed)
        if jcs(owned_tree) != jcs(owned_envelope["tree"]):
            _refuse("input-conflict")
        if owned_plan["baseRevision"] != owned_envelope["semanticRevision"]:
            _refuse("operation-error")
        owned_envelope["tree"] = owned_tree
        report = _apply_core(
            owned_plan["writes"],
            phase=owned_plan["phase"],
            staged_tree=owned_tree,
            staged_bindings=list(owned_envelope["bindings"]),
            input_tree=copy.deepcopy(owned_tree),
            emit_entries=owned_plan["phase"] in ("complete", "normalize"),
        )
    except _RefusalError as exc:
        return pure_refused(exc.code)
    return pure_success(report.to_json())


def _walk_input_pointers(tree: dict[str, Any]) -> dict[int, str]:
    """Index one input tree's absolute pointers (single bounded walk)."""
    pointers: dict[int, str] = {}
    stack: list[tuple[dict[str, Any], str]] = [(tree, "")]
    seen: set[int] = set()
    while stack:
        node, pointer = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        pointers[id(node)] = pointer
        pending: list[tuple[dict[str, Any], str]] = []
        for key in node:
            value = node[key]
            segment = key.replace("~", "~0").replace("/", "~1")
            if isinstance(value, dict):
                pending.append((value, f"{pointer}/{segment}"))
            elif isinstance(value, list):
                for position, entry in enumerate(value):
                    if isinstance(entry, dict):
                        pending.append((entry, f"{pointer}/{segment}/{position}"))
        stack.extend(reversed(pending))
    return pointers
