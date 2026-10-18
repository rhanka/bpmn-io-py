"""Predicate and selector evaluation over the native tree (read-only).

Operates on the immutable moddle tree from ``bpmn_io.bpmn_moddle`` with
bounded traversal (explicit stacks, element and depth caps, visited sets for
graph walks). Never mutates native storage.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from bpmn_io._js import UNDEFINED
from bpmn_io.profile._results import PureRefused, PureResult, PureSuccess
from bpmn_io.profile._unicode_case import apply_case

__all__ = ["ElementHandle", "ReadContext", "evaluate_predicate", "select"]

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


def _index_tree(root: object) -> tuple[tuple[object, ...], dict[str, object]]:
    """Build a bounded containment index with explicit stack traversal."""
    elements: list[object] = []
    by_id: dict[str, object] = {}
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
        stack.extend((child, depth + 1) for child in reversed(_children_of(element)))
    return tuple(elements), by_id


def make_read_context(root: object, stage: str = "post-normalize") -> ReadContext:
    """Build one read-only context over ``root``."""
    elements, by_id = _index_tree(root)
    return ReadContext(root=root, elements=elements, by_id=by_id, stage=stage)


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
        if not isinstance(value, str) or mode not in ("upper", "lower"):
            raise TypeError("profile-type")  # noqa: EM101
        return apply_case(value, str(mode))
    if op == "ids":
        raise ValueError("profile-value-context")  # noqa: EM101
    if op == "outputId":
        raise ValueError("profile-value-context")  # noqa: EM101
    raise ValueError("profile-symbol")  # noqa: EM101


def _eval_predicate(  # noqa: C901, PLR0912, PLR0911, PLR0915
    node: object, context: ReadContext, bindings: dict[str, object]
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
            result = _eval_predicate(entry, context, bindings) and result
        return result
    if op == "any":
        args = node.get("args")
        if not isinstance(args, list) or not args:
            raise TypeError("profile-type")  # noqa: EM101
        result = False
        for entry in args:
            result = _eval_predicate(entry, context, bindings) or result
        return result
    if op == "not":
        return not _eval_predicate(node.get("arg"), context, bindings)
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
        # Assignable uses prefix closure (descriptor subtypes share prefixes).
        return actual == type_name or actual.startswith(type_name.rsplit(":", 1)[0] + ":")
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
        selector = node.get("selector")
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
        if binding is _MISSING or owner is _MISSING:
            return False
        for entry in context.bindings:
            if entry.get("ownerId") == _element_id(owner):
                target = entry.get("targetId")
                if target == _element_id(binding):
                    return True
        return False
    if op == "recognizes":
        return False
    if op == "reachable":
        return False
    raise ValueError("profile-symbol")  # noqa: EM101


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
        for entry in base:
            if via == "owner":
                parent = getattr(entry, "parent_", None)
                if parent is not None:
                    candidates.append(parent)
            else:
                stack: list[tuple[object, int]] = [(entry, 0)]
                seen: set[int] = {id(entry)}
                while stack and len(candidates) < _MAX_ELEMENTS:
                    current, depth = stack.pop()
                    if depth > _MAX_DEPTH:
                        continue
                    children = _children_of(current)
                    if (via == "children" and depth == 0) or (via == "descendants" and depth >= 0):
                        candidates.extend(children)
                    for child in reversed(children):
                        if id(child) not in seen:
                            seen.add(id(child))
                            stack.append((child, depth + 1))
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
