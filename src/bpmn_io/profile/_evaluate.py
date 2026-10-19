"""Predicate and selector evaluation over the native tree (read-only).

Operates on the immutable moddle tree from ``bpmn_io.bpmn_moddle`` with
bounded traversal (explicit stacks, element and depth caps, visited sets for
graph walks). Never mutates native storage.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import TypeGuard

from bpmn_io._js import UNDEFINED
from bpmn_io.profile._results import PureRefused, PureResult, PureSuccess
from bpmn_io.profile._unicode_case import apply_case

__all__ = [
    "ElementHandle",
    "ReadContext",
    "evaluate_predicate",
    "evaluate_value",
    "is_missing",
    "select",
]

_MAX_ELEMENTS = 100000
_MAX_DEPTH = 256
_MISSING = object()

_ECMA_START_WS = frozenset(
    [
        "\t",
        "\n",
        "\x0b",
        "\x0c",
        "\r",
        " ",
        "\u00a0",
        "\u1680",
        "\u2000",
        "\u2001",
        "\u2002",
        "\u2003",
        "\u2004",
        "\u2005",
        "\u2006",
        "\u2007",
        "\u2008",
        "\u2009",
        "\u200a",
        "\u2028",
        "\u2029",
        "\u202f",
        "\u205f",
        "\u3000",
        "\ufeff",
    ]
)


@dataclass(frozen=True)
class ElementHandle:
    """One ordered native handle with its immutable source pointer."""

    element: object
    element_id: str | None
    pointer: str


@dataclass(frozen=True)
class ReadContext:
    """Immutable evaluation context over one native snapshot."""

    root: object
    elements: tuple[object, ...] = ()
    by_id: dict[str, object] = field(default_factory=dict)
    bindings: tuple[dict[str, object], ...] = ()
    stage: str = "post-normalize"
    notions: dict[str, object] = field(default_factory=dict)
    parents: dict[int, object] = field(default_factory=dict)


def _element_id(element: object) -> str | None:
    """Read one element ID without mutating storage."""
    get = getattr(element, "get", None)
    if callable(get):
        try:
            value = get("id")
        except Exception:  # noqa: BLE001 - native getters stay total
            return None

        if value is UNDEFINED or value is None:
            return None
        return str(value) if isinstance(value, str) else None
    if isinstance(element, dict):
        value = element.get("id")
        return value if isinstance(value, str) else None
    return None


def _element_type(element: object) -> str:
    """Read one element qualified type name."""
    type_name = getattr(element, "type_", None)
    if isinstance(type_name, str):
        return type_name
    get = getattr(element, "get", None)
    if callable(get):
        try:
            value = get("$type")
            if isinstance(value, str):
                return value
        except Exception:  # noqa: BLE001, S110 - native getters stay total
            pass
    if isinstance(element, dict):
        value = element.get("$type")
        if isinstance(value, str):
            return value
    return ""


def _read_path(element: object, path: str) -> object:
    """Read one RFC 6901 path from an element (MISSING when absent)."""
    if not path.startswith("/"):
        return _MISSING
    current: object = element
    for raw in path[1:].split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if part not in current:
                return _MISSING
            current = current[part]
        else:
            get = getattr(current, "get", None)
            if not callable(get):
                return _MISSING
            try:
                value = get(part)
            except Exception:  # noqa: BLE001 - native getters stay total
                return _MISSING

            if value is UNDEFINED:
                return _MISSING
            current = value
    return current


def _children_of(  # noqa: C901
    element: object,
) -> list[object]:
    """Collect containment children without mutating storage (bounded)."""
    get = getattr(element, "get", None)
    found: list[object] = []
    if isinstance(element, dict):
        for value in element.values():
            if isinstance(value, dict) and isinstance(value.get("$type"), str):
                found.append(value)
            elif isinstance(value, list):
                for entry in value:
                    if isinstance(entry, dict) and isinstance(entry.get("$type"), str):
                        found.append(entry)  # noqa: PERF401
        return found
    if not callable(get):
        return found

    for attr in ("rootElements", "flowElements", "artifacts", "documentation"):
        try:
            value = get(attr)
        except Exception:  # noqa: BLE001, S112 - native getters stay total
            continue
        if value is UNDEFINED or value is None:
            continue
        if isinstance(value, list):
            found.extend(value)
        elif hasattr(value, "type_"):
            found.append(value)
    return found


def _index_tree(root: object) -> tuple[tuple[object, ...], dict[str, object], dict[int, object]]:
    """Build a bounded containment index with explicit stack traversal.

    ``parents`` maps each visited containment child (by object identity) to
    its immediate containing element, so ``owner`` also resolves over plain
    JSON trees without a native ``parent_`` link.
    """
    elements: list[object] = []
    by_id: dict[str, object] = {}
    parents: dict[int, object] = {}
    stack: list[tuple[object, int]] = [(root, 0)]
    seen: set[int] = set()
    while stack and len(elements) < _MAX_ELEMENTS:
        element, depth = stack.pop()
        if depth > _MAX_DEPTH or id(element) in seen:
            continue
        seen.add(id(element))
        elements.append(element)
        element_id = _element_id(element)
        if element_id is not None and element_id not in by_id:
            by_id[element_id] = element
        children = _children_of(element)
        for child in children:
            parents.setdefault(id(child), element)
        stack.extend((child, depth + 1) for child in reversed(children))
    return tuple(elements), by_id, parents


def make_read_context(
    root: object,
    stage: str = "post-normalize",
    notions: dict[str, object] | None = None,
) -> ReadContext:
    """Build one read-only context over ``root``.

    ``notions`` maps notion IDs to their recognition tables (compiled
    ``{"recognition": ...}`` records or raw recognition ASTs); the table is
    deep-copied so later caller mutations cannot change evaluation.
    """
    elements, by_id, parents = _index_tree(root)
    owned = copy.deepcopy(notions) if notions is not None else {}
    return ReadContext(
        root=root, elements=elements, by_id=by_id, stage=stage, notions=owned, parents=parents
    )


def _children_of_property(element: object, prop: str) -> list[object]:
    """Collect children held under one named containment property."""
    value = _read_property(element, prop)
    if isinstance(value, dict):
        return [value] if isinstance(value.get("$type"), str) else []
    if isinstance(value, list):
        return [
            entry
            for entry in value
            if isinstance(entry, dict) and isinstance(entry.get("$type"), str)
        ]
    return []


def _read_property(element: object, prop: str) -> object:
    """Read one named property from a dict or native element (None when absent)."""
    if isinstance(element, dict):
        return element.get(prop)
    get = getattr(element, "get", None)
    if not callable(get):
        return None
    try:
        return get(prop)
    except Exception:  # noqa: BLE001 - native getters stay total
        return None


def _resolve_single_reference(value: object, read_context: ReadContext) -> list[object]:
    """Resolve one non-list reference value (dangling selects nothing)."""
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str):
            target = read_context.by_id.get(ref)
            return [target] if target is not None else []
        return [value] if isinstance(value.get("$type"), str) else []
    if isinstance(value, str):
        target = read_context.by_id.get(value)
        return [target] if target is not None else []
    if hasattr(value, "type_"):
        return [value]
    return []


def _resolve_reference_value(value: object, read_context: ReadContext) -> list[object]:
    """Resolve one reference value to its target elements (dangling selects nothing)."""
    if value is None or value is _MISSING or value is UNDEFINED:
        return []
    if isinstance(value, list):
        resolved: list[object] = []
        for entry in value:
            resolved.extend(_resolve_reference_value(entry, read_context))
        return resolved
    return _resolve_single_reference(value, read_context)


def _references_target(value: object, base: object, base_id: str | None) -> bool:
    """Return whether a property value points at ``base`` (identity or ID)."""
    if isinstance(value, list):
        return any(_references_target(entry, base, base_id) for entry in value)
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str):
            return base_id is not None and ref == base_id
        return value is base
    if isinstance(value, str):
        return base_id is not None and value == base_id
    return value is not None and value is base


def _eval_value(  # noqa: C901, PLR0912, PLR0911, PLR0915
    node: object, context: ReadContext, bindings: dict[str, object]
) -> object:
    """Evaluate one value AST (MISSING sentinel preserved)."""
    if not isinstance(node, dict):
        raise TypeError("profile-type")  # noqa: EM101
    op = node.get("op")
    if op == "literal":
        return node.get("value")
    if op == "read":
        binding = node.get("binding")
        path = node.get("path")
        if not isinstance(binding, str) or not isinstance(path, str):
            raise TypeError("profile-type")  # noqa: EM101
        target = bindings.get(binding, _MISSING)
        if target is _MISSING:
            return _MISSING
        return _read_path(target, path)
    if op == "id":
        binding = node.get("binding")
        if not isinstance(binding, str):
            raise TypeError("profile-type")  # noqa: EM101
        target = bindings.get(binding, _MISSING)
        if target is _MISSING:
            raise TypeError("profile-type")  # noqa: EM101
        element_id = _element_id(target)
        if element_id is None:
            raise TypeError("profile-type")  # noqa: EM101
        return element_id
    if op == "param":
        name = node.get("name")
        if not isinstance(name, str):
            raise TypeError("profile-type")  # noqa: EM101
        params = bindings.get("params")
        if isinstance(params, dict) and name in params:
            return params[name]
        return _MISSING
    if op == "concat":
        values = node.get("values")
        if not isinstance(values, list) or not values:
            raise TypeError("profile-type")  # noqa: EM101
        parts: list[str] = []
        for entry in values:
            rendered = _eval_value(entry, context, bindings)
            if not isinstance(rendered, str):
                raise TypeError("profile-type")  # noqa: EM101
            parts.append(rendered)
        return "".join(parts)
    if op == "stripPrefix":
        value = _eval_value(node.get("value"), context, bindings)
        prefix = node.get("prefix")
        trim = node.get("trim", "none")
        if not isinstance(value, str) or not isinstance(prefix, str):
            raise TypeError("profile-type")  # noqa: EM101
        text = value
        if trim == "ecma262-2024-start":
            text = text.lstrip("".join(sorted(_ECMA_START_WS)))
        if text.startswith(prefix):
            return text[len(prefix) :]
        return value
    if op == "case":
        value = _eval_value(node.get("value"), context, bindings)
        mode = node.get("mode")
        if value is _MISSING:
            # F3: MISSING yields no label; propagate for the caller to map.
            return _MISSING
        if not isinstance(value, str) or mode not in ("upper", "lower"):
            raise TypeError("profile-type")  # noqa: EM101
        return apply_case(value, str(mode))
    if op == "ids":
        raise ValueError("profile-value-context")  # noqa: EM101
    if op == "outputId":
        raise ValueError("profile-value-context")  # noqa: EM101
    raise ValueError("profile-symbol")  # noqa: EM101


def _eval_predicate(  # noqa: C901, PLR0912, PLR0911, PLR0915
    node: object,
    context: ReadContext,
    bindings: dict[str, object],
    active: frozenset[str] = frozenset(),
) -> bool:
    """Evaluate one predicate AST (errors propagate, never coerce to false)."""
    if not isinstance(node, dict):
        raise TypeError("profile-type")  # noqa: EM101
    op = node.get("op")
    if op == "true":
        return True
    if op == "false":
        return False
    if op == "all":
        args = node.get("args")
        if not isinstance(args, list) or not args:
            raise TypeError("profile-type")  # noqa: EM101
        result = True
        for entry in args:
            result = _eval_predicate(entry, context, bindings, active) and result
        return result
    if op == "any":
        args = node.get("args")
        if not isinstance(args, list) or not args:
            raise TypeError("profile-type")  # noqa: EM101
        result = False
        for entry in args:
            result = _eval_predicate(entry, context, bindings, active) or result
        return result
    if op == "not":
        return not _eval_predicate(node.get("arg"), context, bindings, active)
    if op == "typeIs":
        binding = node.get("binding")
        type_name = node.get("type")
        mode = node.get("mode", "exact")
        if not isinstance(binding, str) or not isinstance(type_name, str):
            raise TypeError("profile-type")  # noqa: EM101
        target = bindings.get(binding, _MISSING)
        if target is _MISSING:
            raise TypeError("profile-type")  # noqa: EM101
        actual = _element_type(target)
        if mode == "exact":
            return actual == type_name
        # Assignable uses native descriptor inheritance (DESIGN §2.2): the
        # element's own registry-backed subtype check decides. Plain-dict
        # trees carry no hierarchy, so they degrade to exact matching.
        instance_of = getattr(target, "instance_of", None)
        if callable(instance_of):
            try:
                return bool(instance_of(type_name))
            except Exception:  # noqa: BLE001 - evaluation stays total
                return False
        return actual == type_name
    if op == "present":
        return _eval_value(node.get("value"), context, bindings) is not _MISSING
    if op == "equal":
        left = _eval_value(node.get("left"), context, bindings)
        right = _eval_value(node.get("right"), context, bindings)
        if left is _MISSING or right is _MISSING:
            return False
        if isinstance(left, bool) or isinstance(right, bool):
            return isinstance(left, bool) and isinstance(right, bool) and left == right
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            left_f = float(left)
            right_f = float(right)
            if math.isnan(left_f) or math.isnan(right_f):
                return False
            return left_f == right_f
        return type(left) is type(right) and left == right
    if op == "textPrefix":
        value = _eval_value(node.get("value"), context, bindings)
        prefix = node.get("prefix")
        trim = node.get("trim", "none")
        if value is _MISSING:
            return False
        if not isinstance(value, str):
            raise TypeError("profile-type")  # noqa: EM101
        if not isinstance(prefix, str) or not prefix:
            raise TypeError("profile-type")  # noqa: EM101
        text = value
        if trim == "ecma262-2024-start":
            text = text.lstrip("".join(sorted(_ECMA_START_WS)))
        return text.startswith(prefix)
    if op == "count":
        # B1: the pinned schema key is `select`; no `selector` alias.
        selector = node.get("select")
        handles = _eval_selector(selector, context, bindings)
        minimum = node.get("min", 0)
        maximum = node.get("max")
        count = len(handles)
        if not isinstance(minimum, int) or isinstance(minimum, bool):
            raise ValueError("profile-bounds")  # noqa: EM101
        if maximum is not None and (not isinstance(maximum, int) or isinstance(maximum, bool)):
            raise ValueError("profile-bounds")  # noqa: EM101
        if count < minimum:
            return False
        return not (maximum is not None and count > maximum)
    if op == "boundRole":
        binding = bindings.get(str(node.get("binding")), _MISSING)
        owner = bindings.get(str(node.get("owner")), _MISSING)
        if binding is _MISSING:
            return False
        role = node.get("role")
        if owner is _MISSING and str(node.get("owner")) == "bindingOwner":
            return _bound_by_role(context, binding, role)
        if owner is _MISSING:
            return False
        for entry in context.bindings:
            if entry.get("ownerId") == _element_id(owner):
                target = entry.get("targetId")
                if target == _element_id(binding) and (role is None or entry.get("role") == role):
                    return True
        return False
    if op == "recognizes":
        return _eval_recognizes(node, context, bindings, active)
    if op == "reachable":
        return _eval_reachable(node, context, bindings)
    raise ValueError("profile-symbol")  # noqa: EM101


def _bound_by_role(context: ReadContext, binding: object, role: object) -> bool:
    """Return whether one element is bound under one role by any owner.

    The notion scope predeclares the ``bindingOwner`` binding but no
    evaluation ever binds it: it reads as the owner recorded on the
    binding itself, so only the (target, role) pair is constrained.
    """
    wanted = _element_id(binding)
    for entry in context.bindings:
        if entry.get("targetId") == wanted and (role is None or entry.get("role") == role):
            return True
    return False


def _eval_recognizes(
    node: dict[str, object],
    context: ReadContext,
    bindings: dict[str, object],
    active: frozenset[str],
) -> bool:
    """Evaluate one ``recognizes`` predicate against the notion table."""
    notion = node.get("notion")
    binding = node.get("binding")
    if not isinstance(notion, str) or not isinstance(binding, str):
        raise TypeError("profile-type")  # noqa: EM101
    if notion not in context.notions:
        raise ValueError("profile-symbol")  # noqa: EM101
    if notion in active:
        raise ValueError("profile-cycle")  # noqa: EM101
    target = bindings.get(binding, _MISSING)
    if target is _MISSING:
        return False
    record = context.notions[notion]
    recognition = record.get("recognition") if isinstance(record, dict) else record
    if recognition is None:
        return False
    local = dict(bindings)
    local["self"] = target
    return _eval_predicate(recognition, context, local, active | {notion})


def _edge_endpoints(element: object, context: ReadContext) -> tuple[list[object], list[object]]:
    """Read one edge's resolved ``sourceRef``/``targetRef`` endpoints."""
    sources = _resolve_reference_value(_read_property(element, "sourceRef"), context)
    targets = _resolve_reference_value(_read_property(element, "targetRef"), context)
    return sources, targets


def _reachability_graph(context: ReadContext, wanted: set[str]) -> dict[int, list[int]]:
    """Build the resolved sourceRef to targetRef adjacency over edge elements."""
    adjacency: dict[int, list[int]] = {}
    for element in context.elements:
        if _element_type(element) not in wanted:
            continue
        origins, ends = _edge_endpoints(element, context)
        if not origins or not ends:
            continue
        for origin in origins:
            adjacency.setdefault(id(origin), []).extend(id(end) for end in ends)
    return adjacency


def _bfs_reachable(
    adjacency: dict[int, list[int]],
    starts: set[int],
    wanted_ids: set[int],
    min_hops: int,
    max_hops: int,
) -> bool:
    """Walk breadth-first layers with a visited set (DESIGN §2.2 reachable)."""
    if min_hops == 0 and starts & wanted_ids:
        return True
    visited = set(starts)
    frontier = set(starts)
    for depth in range(1, max_hops + 1):
        reached: set[int] = set()
        for handle_id in frontier:
            for end_id in adjacency.get(handle_id, ()):
                if end_id not in visited:
                    visited.add(end_id)
                    reached.add(end_id)
        if depth >= min_hops and reached & wanted_ids:
            return True
        frontier = reached
        if not frontier:
            return False
    return False


def _eval_reachable(
    node: dict[str, object], context: ReadContext, bindings: dict[str, object]
) -> bool:
    """Decide bounded directed reachability over resolved reference edges."""
    source_ast = node.get("from")
    target_ast = node.get("to")
    edge_types = node.get("edgeTypes")
    min_hops = node.get("minHops", 0)
    max_hops = node.get("maxHops")
    if not isinstance(edge_types, list) or not edge_types:
        raise TypeError("profile-type")  # noqa: EM101
    if not isinstance(min_hops, int) or isinstance(min_hops, bool) or min_hops < 0:
        raise ValueError("profile-bounds")  # noqa: EM101
    if max_hops is None:
        max_hops = len(context.elements)
    if not isinstance(max_hops, int) or isinstance(max_hops, bool) or max_hops < min_hops:
        raise ValueError("profile-bounds")  # noqa: EM101
    wanted = {str(edge) for edge in edge_types if isinstance(edge, str)}
    sources = _eval_selector(source_ast, context, bindings)
    targets = _eval_selector(target_ast, context, bindings)
    if not sources or not targets:
        return False
    wanted_ids = {id(handle.element) for handle in targets}
    starts = {id(handle.element) for handle in sources}
    return _bfs_reachable(
        _reachability_graph(context, wanted), starts, wanted_ids, min_hops, max_hops
    )


def _eval_selector(  # noqa: C901, PLR0912, PLR0915
    node: object, context: ReadContext, bindings: dict[str, object]
) -> list[ElementHandle]:
    """Evaluate one selector AST to ordered unique handles."""
    if not isinstance(node, dict):
        raise TypeError("profile-type")  # noqa: EM101
    from_name = node.get("from")
    via = node.get("via")
    if not isinstance(from_name, str) or not isinstance(via, str):
        raise TypeError("profile-type")  # noqa: EM101
    if from_name not in bindings and from_name != "root":
        raise ValueError("profile-symbol")  # noqa: EM101
    if from_name == "root":
        base: list[object] = [context.root]
    else:
        base_value = bindings.get(from_name, _MISSING)
        if base_value is _MISSING:
            raise TypeError("profile-type")  # noqa: EM101
        base = [base_value]
    candidates: list[object] = []
    if via == "self":
        candidates = list(base)
    elif via == "root":
        candidates = [context.root]
    elif via == "all":
        candidates = list(context.elements)
    elif via in ("children", "descendants", "owner"):
        prop = node.get("property")
        # Lot 3 (seal fix) + lot 4 union: `scoped` drives the depth-0
        # property scoping in the generic walk below; the dedicated
        # `children`-with-property branch above keeps lot-4 behavior.
        scoped = prop if isinstance(prop, str) and prop else None
        for entry in base:
            if via == "owner":
                parent = getattr(entry, "parent_", None)
                if parent is None and isinstance(entry, dict):
                    parent = context.parents.get(id(entry))
                if parent is not None:
                    candidates.append(parent)
            elif via == "children" and isinstance(prop, str):
                # Lot 4: a children traversal names its containment
                # property; unfiltered collection stays for property-less
                # (legacy) selectors only.
                candidates.extend(_children_of_property(entry, prop))
            else:
                stack: list[tuple[object, int]] = [(entry, 0)]
                seen: set[int] = {id(entry)}
                while stack and len(candidates) < _MAX_ELEMENTS:
                    current, depth = stack.pop()
                    if depth > _MAX_DEPTH:
                        continue
                    if depth == 0 and scoped is not None:
                        children = _children_of_property(current, scoped)
                    else:
                        children = _children_of(current)
                    if (via == "children" and depth == 0) or (via == "descendants" and depth >= 0):
                        candidates.extend(children)
                    for child in reversed(children):
                        if id(child) not in seen:
                            seen.add(id(child))
                            stack.append((child, depth + 1))
    elif via in ("reference", "inverseReference"):
        prop = node.get("property")
        if not isinstance(prop, str) or not prop:
            raise ValueError("profile-selector-property")  # noqa: EM101
        if via == "reference":
            for entry in base:
                value = _read_property(entry, prop)
                target = _resolve_occurrence_reference(value, bindings)
                if target is not None:
                    candidates.append(target)
                else:
                    candidates.extend(_resolve_reference_value(value, context))
        else:
            for entry in base:
                entry_id = _element_id(entry)
                for element in context.elements:
                    if _references_target(_read_property(element, prop), entry, entry_id):
                        candidates.append(element)
    elif via in ("pages", "occurrences", "semantic"):
        # Lot 4 (DESIGN §2.2 render contexts): `pages` and `occurrences`
        # traverse the RenderData/1 carried by the `render` binding;
        # `semantic` resolves one occurrence to its native element.
        candidates = _render_candidates(via, base, context)
    else:
        candidates = list(base)
    where = node.get("where")
    order = node.get("order", "id")
    handles: list[ElementHandle] = []
    seen_handles: set[int] = set()
    for element in candidates:
        if id(element) in seen_handles:
            continue
        element_id = _element_id(element)
        local = dict(bindings)
        local["self"] = element
        if where is not None and not _eval_predicate(where, context, local):
            continue
        seen_handles.add(id(element))
        pointer = f"#/{element_id}" if element_id else "#/anonymous"
        handles.append(ElementHandle(element=element, element_id=element_id, pointer=pointer))
    if order == "id":

        def _sort_key(handle: ElementHandle) -> tuple[int, bytes, str]:
            if handle.element_id is None:
                return (1, b"", handle.pointer)
            return (0, handle.element_id.encode("utf-16-be"), handle.pointer)

        handles.sort(key=_sort_key)
    return handles


def _is_occurrence_handle(value: object) -> TypeGuard[dict[str, object]]:
    """Return whether one value is an R occurrence (pageId + occurrenceKey)."""
    return (
        isinstance(value, dict)
        and isinstance(value.get("pageId"), str)
        and isinstance(value.get("occurrenceKey"), str)
    )


def _render_candidates(  # noqa: C901 - three render branches share one via dispatch
    via: str, base: list[object], context: ReadContext
) -> list[object]:
    """Traverse one render selector branch (lot 4, DESIGN §2.2)."""
    if via in ("pages", "occurrences"):
        render = base[0] if len(base) == 1 else None
        if not isinstance(render, dict):
            raise ValueError("profile-value-context")  # noqa: EM101
        if via == "pages":
            pages = render.get("pages")
            if not isinstance(pages, list):
                raise ValueError("profile-value-context")  # noqa: EM101
            return [page for page in pages if isinstance(page, dict)]
        records = render.get("occurrences")
        if not isinstance(records, list):
            raise ValueError("profile-value-context")  # noqa: EM101
        order_of: dict[str, int] = {}
        for page in render.get("pages", []):
            if isinstance(page, dict) and isinstance(page.get("pageId"), str):
                order_of[str(page.get("pageId"))] = (
                    int(page["order"]) if type(page.get("order")) is int else 0
                )
        matched: list[dict[str, object]] = [
            record for record in records if _is_occurrence_handle(record)
        ]
        matched.sort(
            key=lambda record: (
                str(order_of.get(str(record.get("pageId")), 0)).encode("utf-16-be"),
                str(record.get("occurrenceKey")).encode("utf-16-be"),
            )
        )
        return list(matched)
    resolved: list[object] = []
    for entry in base:
        if not _is_occurrence_handle(entry):
            raise ValueError("profile-value-context")  # noqa: EM101
        semantic_id = entry.get("semanticId")
        if not isinstance(semantic_id, str):
            continue
        element = context.by_id.get(semantic_id)
        if element is not None:
            resolved.append(element)
    return resolved


def _resolve_occurrence_reference(value: object, bindings: dict[str, object]) -> object | None:
    """Resolve one ``{pageId, occurrenceKey}`` endpoint against the R.

    Returns the occurrence record, or ``None`` when the value is not an
    occurrence endpoint (the legacy native path then applies).
    """
    if not _is_occurrence_handle(value):
        return None
    render = bindings.get("render")
    records = render.get("occurrences") if isinstance(render, dict) else None
    if not isinstance(records, list):
        return None
    for record in records:
        if (
            _is_occurrence_handle(record)
            and record.get("pageId") == value.get("pageId")
            and record.get("occurrenceKey") == value.get("occurrenceKey")
        ):
            return record
    return None


def is_missing(value: object) -> bool:
    """Return whether one evaluated value is the MISSING sentinel (lot 4)."""
    return value is _MISSING


def evaluate_value(
    ast: object, read_context: ReadContext, bindings: dict[str, object]
) -> PureResult:
    """Evaluate one value AST, preserving MISSING (lot 4 export/render use)."""
    try:
        return PureSuccess(payload=_eval_value(ast, read_context, bindings))
    except (ValueError, TypeError) as exc:
        code = str(exc.args[0]) if exc.args else "profile-type"
        return PureRefused(code=code)
    except Exception:  # noqa: BLE001 - evaluation stays total
        return PureRefused(code="profile-type")


def evaluate_predicate(
    ast: object, read_context: ReadContext, bindings: dict[str, object]
) -> PureResult:
    """Evaluate one predicate AST to a Boolean (read-only, bounded)."""
    try:
        return PureSuccess(payload=_eval_predicate(ast, read_context, bindings))
    except (ValueError, TypeError) as exc:
        code = str(exc.args[0]) if exc.args else "profile-type"
        return PureRefused(code=code)
    except Exception:  # noqa: BLE001 - evaluation stays total
        return PureRefused(code="profile-type")


def select(selector: object, read_context: ReadContext, bindings: dict[str, object]) -> PureResult:
    """Evaluate one selector AST to ordered element handles."""
    try:
        handles = _eval_selector(selector, read_context, bindings)
    except (ValueError, TypeError) as exc:
        code = str(exc.args[0]) if exc.args else "profile-type"
        return PureRefused(code=code)
    except Exception:  # noqa: BLE001 - selection stays total
        return PureRefused(code="profile-type")
    return PureSuccess(payload=handles)
