"""Lot-3 identity allocation (DESIGN §3.2 stable-id/1, spec §6.2).

Allocates deterministic ids to every ID-missing element of an ID-able
type in pre-order (members in UTF-16 key order, arrays by index):
the root without id receives ``stable-id("document-root/1",
"definitions", "root")``; any other ID-missing element receives
``stable-id(ownerId, slot, key)`` with the nearest ancestor id after
allocation, the ``<containing $type>.<property>`` slot and
``JCS([contentSignature, duplicateOrdinal])``. Existing ids never change;
ID-less types are never identified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bpmn_io.profile._c14n import digest, jcs
from bpmn_io.profile._cn_context import _utf16
from bpmn_io.profile._cn_plan import _RefusalError, _refuse
from bpmn_io.profile._stable_id import allocate_stable_id

__all__ = ["Allocation", "allocate_tree_ids"]


@dataclass
class Allocation:
    """One performed identity allocation with its coordinates."""

    element: dict[str, Any]
    pointer: str
    new_id: str
    owner_id: str
    slot: str
    key: str


def _strip_ids(node: object) -> object:
    """Deep copy one subtree with every ``id`` member removed."""
    if isinstance(node, dict):
        return {key: _strip_ids(value) for key, value in node.items() if key != "id"}
    if isinstance(node, list):
        return [_strip_ids(entry) for entry in node]
    return node


def _id_able(type_name: str, types: dict[str, dict[str, Any]]) -> bool:
    """Return whether one descriptor type carries ids."""
    spec = types.get(type_name)
    return spec is not None and spec.get("id") is True


def _is_single(parent_type: str, prop: str, types: dict[str, dict[str, Any]]) -> bool:
    """Return whether one containment property is single-valued."""
    spec = types.get(parent_type)
    if spec is None:
        return False
    single = spec.get("single", ())
    return isinstance(single, (list, tuple)) and prop in single


@dataclass
class _Allocator:
    """Mutable identity-allocation state over one owned tree."""

    types: dict[str, dict[str, Any]]
    pointers: dict[int, str]
    used: set[str] = field(default_factory=set)
    ordinals: dict[tuple[str, str, str], int] = field(default_factory=dict)
    parents: dict[int, dict[str, Any]] = field(default_factory=dict)
    done: list[Allocation] = field(default_factory=list)

    def claim(self, new_id: str) -> None:
        """Claim one allocated id (collisions refuse)."""
        if new_id in self.used:
            _refuse("id-collision")
        self.used.add(new_id)

    def allocate_root(self, node: dict[str, Any]) -> None:
        """Allocate the document root id when missing."""
        new_id = allocate_stable_id("document-root/1", "definitions", "root")
        self.claim(new_id)
        node["id"] = new_id
        self.done.append(
            Allocation(
                element=node,
                pointer=self.pointers.get(id(node), ""),
                new_id=new_id,
                owner_id="document-root/1",
                slot="definitions",
                key="root",
            )
        )

    def allocate_child(self, node: dict[str, Any], parent: dict[str, Any], via: str) -> None:
        """Allocate one ID-missing child with owner, slot and ordinal key."""
        owner_id = _nearest_allocated_id(parent, self.parents)
        parent_type = parent.get("$type")
        slot = f"{parent_type}.{via}"
        signature = digest(_strip_ids(node))
        if isinstance(parent_type, str) and _is_single(parent_type, via, self.types):
            ordinal = 0
        else:
            ordinal_key = (owner_id, slot, signature)
            ordinal = self.ordinals.get(ordinal_key, 0)
            self.ordinals[ordinal_key] = ordinal + 1
        key = jcs([signature, ordinal])
        new_id = allocate_stable_id(owner_id, slot, key)
        self.claim(new_id)
        node["id"] = new_id
        self.done.append(
            Allocation(
                element=node,
                pointer=self.pointers.get(id(node), ""),
                new_id=new_id,
                owner_id=owner_id,
                slot=slot,
                key=key,
            )
        )


def allocate_tree_ids(  # noqa: C901 - one branch per allocation case
    tree: dict[str, Any],
    types: dict[str, dict[str, Any]],
    pointers: dict[int, str],
) -> list[Allocation]:
    """Allocate ids over one snapshot tree in place (``id-collision``).

    ``pointers`` maps the tree objects to their absolute source pointers.
    Returns the allocations in pre-order; any collision refuses with no
    partial allocation visible to the caller (the tree is owned).
    """
    allocator = _Allocator(types=types, pointers=pointers, used=_collect_ids(tree))
    walk: list[tuple[dict[str, Any], dict[str, Any] | None, str | None]] = [(tree, None, None)]
    seen: set[int] = set()
    while walk:
        node, parent, via = walk.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        type_name = node.get("$type")
        if not isinstance(type_name, str):
            _refuse("descriptor-role-unknown")
        if parent is None:
            if node.get("id") is None and _id_able(type_name, types):
                allocator.allocate_root(node)
        elif node.get("id") is None and _id_able(type_name, types):
            if via is None:
                _refuse("operation-error")
            allocator.allocate_child(node, parent, via)
        pending: list[tuple[dict[str, Any], dict[str, Any] | None, str | None]] = []
        for prop in sorted(node.keys(), key=_utf16):
            value = node[prop]
            if isinstance(value, dict):
                allocator.parents.setdefault(id(value), node)
                pending.append((value, node, prop))
            elif isinstance(value, list):
                for entry in value:
                    if isinstance(entry, dict):
                        allocator.parents.setdefault(id(entry), node)
                        pending.append((entry, node, prop))
        walk.extend(reversed(pending))
    return allocator.done


def _collect_ids(tree: dict[str, Any]) -> set[str]:
    """Collect every string id of one tree (single bounded walk)."""
    found: set[str] = set()
    stack: list[object] = [tree]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            element_id = current.get("id")
            if isinstance(element_id, str):
                found.add(element_id)
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return found


def _nearest_allocated_id(parent: dict[str, Any], parents: dict[int, dict[str, Any]]) -> str:
    """Return the nearest ancestor id after allocation.

    Ancestors precede descendants in pre-order, so every ancestor
    already carries its final id (allocated or stored).
    """
    current: dict[str, Any] | None = parent
    seen = 0
    while current is not None and seen < 100000:
        seen += 1
        element_id = current.get("id")
        if isinstance(element_id, str):
            return element_id
        current = parents.get(id(current))
    error = _RefusalError("descriptor-role-unknown")
    raise error
