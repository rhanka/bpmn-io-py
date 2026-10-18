# DESIGN R3.3 §6.4: immutable input index and source-pointer construction.
"""Element index and RFC 6901 source pointers for the lint bridge.

The index maps every ID-bearing element of the immutable input tree to its
absolute source pointer. Pointers build segment by segment: ``~`` escapes
to ``~0`` first, then ``/`` to ``~1``; integer segments use decimal form
without locale. ``[]`` points at the node itself. An unresolvable ID or an
unsupported path form yields ``(None, "unavailable")``; the adapter never
fabricates the root pointer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bpmn_io.moddle.base import ModdleElement

__all__ = ["build_id_index", "escape_segment", "resolve_pointer", "walk_tree"]

#: Primitive property types whose values are never walked (mirrors the
#: literal ``traverse`` port: containment only, same visited set).
_SIMPLE_TYPES = frozenset({"String", "Boolean", "Integer", "Real"})


def escape_segment(segment: str) -> str:
    """Escape one pointer segment (``~`` to ``~0`` first, then ``/`` to ``~1``)."""
    return segment.replace("~", "~0").replace("/", "~1")


def walk_tree(root: ModdleElement) -> list[tuple[ModdleElement, str]]:
    """Walk ``root`` depth-first, returning ``(node, pointer)`` pairs.

    Uses an explicit stack (bounded: no recursion, no allocation before
    visiting) and skips generic subtrees exactly like the literal
    ``traverse`` port. The input tree is only read, never mutated.
    """
    pairs: list[tuple[ModdleElement, str]] = []
    stack: list[tuple[ModdleElement, str]] = [(root, "")]
    while stack:
        node, pointer = stack.pop()
        pairs.append((node, pointer))
        stack.extend(_child_pointers(node, pointer))
    return pairs


def build_id_index(root: ModdleElement) -> dict[str, str]:
    """Index ID-bearing elements of ``root`` by absolute source pointer.

    On duplicate IDs the first visit wins.
    """
    index: dict[str, str] = {}
    for node, pointer in walk_tree(root):
        node_id = node.get("id")
        if isinstance(node_id, str) and node_id and node_id not in index:
            index[node_id] = pointer
    return index


def _child_pointers(node: ModdleElement, pointer: str) -> list[tuple[ModdleElement, str]]:
    """List ``(child, pointer)`` pairs of the containment children of ``node``."""
    descriptor = node.descriptor_
    if getattr(descriptor, "is_generic", False):
        return []
    pairs: list[tuple[ModdleElement, str]] = []
    for prop in descriptor.properties:
        if prop.is_attr or prop.is_reference or prop.type in _SIMPLE_TYPES:
            continue
        if prop.name not in vars(node):
            continue
        value = vars(node)[prop.name]
        segment = escape_segment(prop.name)
        if prop.is_many:
            for position, child in enumerate(value):
                pairs.append((child, f"{pointer}/{segment}/{position}"))
        else:
            pairs.append((value, f"{pointer}/{segment}"))
    pairs.reverse()
    return pairs


def _valid_segments(path: Any) -> list[str | int] | None:  # noqa: ANN401
    """Validate an upstream path value into segments, or ``None`` when unsupported."""
    if not isinstance(path, list):
        return None
    segments: list[str | int] = []
    for segment in path:
        if isinstance(segment, bool):
            return None
        if isinstance(segment, int):
            if segment < 0:
                return None
            segments.append(segment)
        elif isinstance(segment, str):
            segments.append(segment)
        else:
            return None
    return segments


def resolve_pointer(
    index: dict[str, str],
    reported_id: Any,  # noqa: ANN401 - upstream report content
    path: Any,  # noqa: ANN401 - upstream report content
) -> tuple[str | None, str]:
    """Resolve ``(reported_id, path)`` to ``(pointer, provenance)``.

    The upstream path is either one property-name string or an array of
    string/integer segments: the reported ID resolves in the immutable
    input index and the escaped segments append to its absolute source
    pointer (``[]`` points at the node itself). A verbatim absolute
    pointer (a string starting with ``/``) passes through only as supplied
    by generic producers — with no reported ID, or with a reported ID the
    index knows; a pointer for an unknown ID is refused, never exact.
    Anything else yields ``(None, "unavailable")``; the adapter never
    fabricates the root pointer.
    """
    has_id = isinstance(reported_id, str) and reported_id != ""
    base = index.get(reported_id) if has_id else None
    if isinstance(path, str):
        if path.startswith("/"):
            # Generic absolute pointer: exact unless it names an unknown ID.
            resolved = path if base is not None or not has_id else None
        elif has_id and base is not None and path:
            resolved = f"{base}/{escape_segment(path)}"
        else:
            resolved = None
    else:
        segments = _valid_segments(path)
        if segments is None or base is None:
            resolved = None
        else:
            resolved = base
            for segment in segments:
                text = str(segment) if isinstance(segment, int) else escape_segment(segment)
                resolved += f"/{text}"
    if resolved is None:
        return None, "unavailable"
    return resolved, "exact"
