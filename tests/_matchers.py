"""Ported test matchers (moddle-xml/bpmn-moddle ``expect.js`` + ``matchers.js``).

``json_equal`` is the transposed ``jsonEqual`` assertion: it compares the canonical JSON
projections of two values, keeping insertion order and excluding moddle-internal members
(``$parent``/``$model``/``$descriptor``).

Moddle elements take part through the ``to_canonical_dict`` protocol (implemented on the
model base class in Lot 4): it must return plain JSON-like data with the internal members
already excluded. Traversal is iterative, so deeply nested models never hit the recursion
limit. Inputs must be finite trees; reference cycles raise ``ValueError``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bpmn_io._js import UNDEFINED, json_stringify

if TYPE_CHECKING:
    from collections.abc import Hashable, Iterator

__all__ = ["json_equal", "to_canonical"]

#: JSON-like accumulator: sequence or string-keyed mapping under construction.
_Acc = list[Any] | dict[Any, Any]

#: Walker frame: (pair iterator, accumulator, (parent, key) slot or None, source id).
_Frame = tuple[Any, Any, Any, int]


def _resolve_node(value: object) -> object:
    """Dereference one node through the ``to_canonical_dict`` protocol, if present."""
    node = value
    seen: set[int] = set()
    while True:
        if (
            node is None
            or isinstance(node, (bool, int, float, str, list, tuple, dict))
            or node is UNDEFINED
        ):
            return node
        convert = getattr(node, "to_canonical_dict", None)
        if not callable(convert):
            msg = f"to_canonical() supports JSON-like values, got {type(node).__name__}"
            raise TypeError(msg)
        if id(node) in seen:
            msg = "to_canonical() encountered a reference cycle"
            raise ValueError(msg)
        seen.add(id(node))
        node = convert()


def _pairs(node: dict[Any, Any] | list[Any] | tuple[Any, ...]) -> Iterator[tuple[Any, Any]]:
    """Yield ``(key, value)`` pairs with ``None`` keys for sequence items."""
    if isinstance(node, dict):
        yield from node.items()
    else:
        for item in node:
            yield None, item


def _attach(acc: _Acc, key: Hashable | None, value: object) -> None:
    """Append ``value`` to a list accumulator or set it under a dict key."""
    if isinstance(acc, list):
        acc.append(value)
    else:
        acc[key] = value


def _push_child(
    stack: list[_Frame],
    active: set[int],
    child: dict[Any, Any] | list[Any] | tuple[Any, ...],
    acc: _Acc,
    key: Hashable | None,
) -> None:
    """Push a container frame for ``child``; cycles raise ``ValueError``."""
    if id(child) in active:
        msg = "to_canonical() encountered a reference cycle"
        raise ValueError(msg)
    active.add(id(child))
    stack.append((_pairs(child), {} if isinstance(child, dict) else [], (acc, key), id(child)))


def to_canonical(value: object) -> object:
    """Project ``value`` to plain JSON-like data, keeping insertion order.

    Moddle elements resolve through ``to_canonical_dict``; ``UNDEFINED`` passes through
    (``json_stringify`` maps it to ``null`` in arrays and skips it in objects).
    """
    node = _resolve_node(value)
    if not isinstance(node, (dict, list, tuple)):
        return node
    root: _Acc = {} if isinstance(node, dict) else []
    stack: list[_Frame] = [(_pairs(node), root, None, id(node))]
    active = {id(node)}
    while stack:
        it, acc, slot, source_id = stack[-1]
        try:
            key, raw = next(it)
        except StopIteration:
            active.discard(source_id)
            stack.pop()
            if slot is not None:
                _attach(slot[0], slot[1], acc)
            continue
        child = _resolve_node(raw)
        if isinstance(child, (dict, list, tuple)):
            _push_child(stack, active, child, acc, key)
        else:
            _attach(acc, key, child)
    return root


def json_equal(actual: object, expected: object) -> bool:
    """Transposed ``jsonEqual``: true when both canonical projections stringify equal."""
    return json_stringify(to_canonical(actual)) == json_stringify(to_canonical(expected))
